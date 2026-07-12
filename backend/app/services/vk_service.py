"""VK (ВКонтакте) service — Callback API integration.

Handles incoming Callback API events (message_new, message_allow, message_event,
confirmation), sends messages through VK API with full media support, inline
keyboards, bot commands dispatch, and payment guard integration.

Binding fields:
    channel_account_id  — VK Group ID (numeric string)
    access_token        — Community token (via Secrets Manager)
    metadata.confirmation_code  — Confirmation string from VK Callback API settings
    metadata.webhook_secret     — Optional secret key for request verification
"""

from __future__ import annotations

import asyncio
import json
import logging
import random
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

import httpx

from app.config import Settings, get_settings
from app.models.channel_binding import ChannelType
from app.models.conversation import Conversation, ConversationStatus, MarketingStatus
from app.models.message import Message, MessageChannel, MessageRole
from app.services.channel_binding_service import ChannelBindingService
from app.utils.datetime_utils import utc_now
from app.utils.enum_helpers import get_enum_value

logger = logging.getLogger(__name__)

VK_API_BASE = "https://api.vk.com/method/"
VK_API_VERSION = "5.199"
VK_MSG_NS = uuid.UUID("7ba7b810-9dad-11d1-80b4-00c04fd430c8")

# VK message text limit
VK_MESSAGE_MAX_LENGTH = 4096


def _vk_random_id() -> int:
    """Return a unique random_id for VK messages.send (required to prevent duplicates)."""
    return random.randint(1, 2_147_483_647)


def _truncate_vk_text(text: str, max_len: int = VK_MESSAGE_MAX_LENGTH) -> str:
    if len(text) <= max_len:
        return text
    suffix = "\n…"
    take = max_len - len(suffix)
    return text[:take] + suffix if take > 64 else text[:max_len]


def _build_vk_inline_keyboard(quick_replies: list[str]) -> Optional[dict]:
    """Build VK inline keyboard from quick_reply labels."""
    if not quick_replies:
        return None
    rows = [quick_replies[i:i + 2] for i in range(0, len(quick_replies), 2)]
    buttons = []
    for row in rows:
        buttons.append([
            {
                "action": {
                    "type": "callback",
                    "label": label[:40],
                    "payload": json.dumps({"cmd": "reply", "text": label}, ensure_ascii=False)[:255],
                },
                "color": "secondary",
            }
            for label in row
        ])
    return {"one_time": False, "inline": True, "buttons": buttons}


def _build_vk_payment_keyboard(pay_buttons: list[dict]) -> Optional[dict]:
    """Build VK keyboard with openlink (URL) buttons for payment plans."""
    if not pay_buttons:
        return None
    buttons = []
    for btn in pay_buttons:
        if btn.get("url"):
            buttons.append([{
                "action": {
                    "type": "open_link",
                    "label": btn["name"][:40],
                    "link": btn["url"],
                },
            }])
        else:
            buttons.append([{
                "action": {
                    "type": "text",
                    "label": btn["name"][:40],
                    "payload": json.dumps({"cmd": "pay", "plan_id": btn["plan_id"]}, ensure_ascii=False)[:255],
                },
                "color": "primary",
            }])
    return {"one_time": True, "inline": True, "buttons": buttons}


class VKService:
    """Service for VK (ВКонтакте) Callback API integration."""

    def __init__(
        self,
        channel_binding_service: ChannelBindingService,
        db: Any,
        settings: Optional[Settings] = None,
    ):
        self.channel_binding_service = channel_binding_service
        self.db = db
        self.settings = settings or get_settings()

    # -------------------------------------------------------------------------
    # Inbound webhook handler
    # -------------------------------------------------------------------------

    async def handle_webhook_event(
        self, payload: dict[str, Any], binding_id: str
    ) -> str:
        """Handle incoming VK Callback API event.

        Returns the required response string:
          - confirmation_code string for 'confirmation' type
          - 'ok' for all other events
        """
        try:
            binding = await self.channel_binding_service.get_binding(binding_id)
            if not binding or not binding.is_active:
                logger.warning("VK binding %s not found or inactive", binding_id)
                return "ok"
            if binding.channel_type not in (ChannelType.VK, ChannelType.VK.value):
                logger.warning("VK binding %s has wrong channel type: %s", binding_id, binding.channel_type)
                return "ok"

            event_type = payload.get("type", "")

            # ── Confirmation handshake ───────────────────────────────────────
            if event_type == "confirmation":
                confirmation_code = (binding.metadata or {}).get("confirmation_code", "")
                if not confirmation_code:
                    logger.error("VK binding %s: confirmation_code not set in metadata", binding_id)
                    return "ok"
                return confirmation_code

            # ── Optional secret verification ────────────────────────────────
            expected_secret = (binding.metadata or {}).get("webhook_secret", "")
            if expected_secret:
                received_secret = payload.get("secret", "")
                if received_secret != expected_secret:
                    logger.warning("VK binding %s: secret mismatch", binding_id)
                    return "ok"

            # ── Permission to receive messages (user pressed "Start") ────────
            if event_type == "message_allow":
                user_id = payload.get("object", {}).get("user_id")
                if user_id:
                    access_token = await self.channel_binding_service.get_access_token(binding_id)
                    from app.services.bot_commands_service import dispatch_command_generic
                    await dispatch_command_generic(
                        command="/restart",
                        chat_id=str(user_id),
                        binding=binding,
                        send_fn=self._make_command_send_fn(access_token, int(user_id), binding),
                        db=self.db,
                    )
                return "ok"

            # ── Inline callback (button press) ───────────────────────────────
            if event_type == "message_event":
                await self._handle_message_event(payload, binding, binding_id)
                return "ok"

            # ── Incoming message ─────────────────────────────────────────────
            if event_type == "message_new":
                await self._handle_message_new(payload, binding, binding_id)

        except Exception as exc:
            logger.exception("VKService.handle_webhook_event error for binding %s: %s", binding_id, exc)

        return "ok"

    async def _handle_message_event(
        self, payload: dict[str, Any], binding: Any, binding_id: str
    ) -> None:
        """Handle message_event (inline callback button press)."""
        obj = payload.get("object", {})
        event_id = obj.get("event_id")
        user_id = obj.get("user_id")
        peer_id = obj.get("peer_id")
        vk_payload = obj.get("payload", {})

        if not event_id or not user_id or not peer_id:
            return

        # Always answer the callback to remove "loading" state
        try:
            access_token = await self.channel_binding_service.get_access_token(binding_id)
            await self._answer_callback(access_token, event_id, int(user_id), int(peer_id))
        except Exception as exc:
            logger.warning("VK sendMessageEventAnswer failed: %s", exc)

        # Process the callback payload as a command/action
        if isinstance(vk_payload, str):
            try:
                vk_payload = json.loads(vk_payload)
            except (json.JSONDecodeError, ValueError):
                vk_payload = {}

        cmd = vk_payload.get("cmd", "")
        if cmd == "restart":
            try:
                access_token = await self.channel_binding_service.get_access_token(binding_id)
                from app.services.bot_commands_service import dispatch_command_generic
                await dispatch_command_generic(
                    command="/restart",
                    chat_id=str(peer_id),
                    binding=binding,
                    send_fn=self._make_command_send_fn(access_token, int(peer_id), binding),
                    db=self.db,
                )
            except Exception as exc:
                logger.warning("VK callback /restart failed: %s", exc)
        elif cmd == "reply":
            # Treat button text as a new user message
            reply_text = vk_payload.get("text", "")
            if reply_text:
                synthetic_payload = {
                    "type": "message_new",
                    "object": {
                        "message": {
                            "from_id": user_id,
                            "peer_id": peer_id,
                            "text": reply_text,
                            "id": 0,
                            "date": 0,
                            "attachments": [],
                        },
                        "client_info": {},
                    },
                }
                await self._handle_message_new(synthetic_payload, binding, binding_id)

    async def _answer_callback(
        self, access_token: str, event_id: str, user_id: int, peer_id: int
    ) -> None:
        """Call messages.sendMessageEventAnswer to acknowledge the callback press."""
        async with httpx.AsyncClient(timeout=10.0) as client:
            await client.post(
                f"{VK_API_BASE}messages.sendMessageEventAnswer",
                params={
                    "event_id": event_id,
                    "user_id": user_id,
                    "peer_id": peer_id,
                    "event_data": json.dumps({"type": "show_snackbar", "text": "✓"}, ensure_ascii=False),
                    "access_token": access_token,
                    "v": VK_API_VERSION,
                },
            )

    async def _handle_message_new(
        self, payload: dict[str, Any], binding: Any, binding_id: str
    ) -> None:
        """Handle message_new event — full inbound pipeline."""
        obj = payload.get("object", {})
        message_data = obj.get("message", {})

        from_id = message_data.get("from_id")
        peer_id = message_data.get("peer_id")
        message_id = message_data.get("id")
        raw_text = message_data.get("text", "") or ""
        attachments = message_data.get("attachments", []) or []
        date_ts = message_data.get("date", 0)

        # Ignore messages from other bots/communities (negative from_id)
        if not from_id or int(from_id) < 0:
            return
        if not peer_id:
            return

        peer_id_str = str(peer_id)
        from_id_str = str(from_id)

        message_text = raw_text.strip()
        media_url: Optional[str] = None
        media_type: Optional[str] = None
        is_voice = False
        access_token: Optional[str] = None

        # ── Process attachments ──────────────────────────────────────────────
        for att in attachments:
            att_type = att.get("type", "")

            if att_type == "photo":
                photo = att.get("photo", {})
                sizes = photo.get("orig_photo") and [photo["orig_photo"]] or photo.get("sizes", [])
                if sizes:
                    best = max(sizes, key=lambda s: s.get("width", 0) * s.get("height", 0))
                    media_url = best.get("url")
                    media_type = "image"

            elif att_type == "audio_message":
                audio_msg = att.get("audio_message", {})
                is_voice = True
                media_type = "audio"
                # Use VK-provided transcript if ready
                transcript_state = audio_msg.get("transcript_state", "")
                transcript = audio_msg.get("transcript", "")
                if transcript_state == "done" and transcript:
                    message_text = transcript
                    logger.info("VK: using VK transcript for voice (peer=%s)", peer_id_str)
                else:
                    # Download OGG and pass to STT
                    audio_url = audio_msg.get("link_ogg") or audio_msg.get("link_mp3")
                    if audio_url:
                        media_url = audio_url
                        try:
                            from app.services.stt_service import transcribe_from_url
                            transcript = await transcribe_from_url(audio_url, language="ru")
                            if transcript:
                                message_text = transcript
                                logger.info(
                                    "VK STT transcribed voice (peer=%s): %d chars",
                                    peer_id_str, len(transcript),
                                )
                        except Exception as exc:
                            logger.warning("VK STT failed (peer=%s): %s", peer_id_str, exc)

            elif att_type == "doc":
                doc = att.get("doc", {})
                doc_url = doc.get("url")
                if doc_url:
                    media_url = doc_url
                    media_type = "document"

            elif att_type == "video":
                # VK does not expose direct video URLs via Callback API
                video = att.get("video", {})
                image_sizes = video.get("image", [])
                if image_sizes:
                    best_img = max(image_sizes, key=lambda s: s.get("width", 0))
                    media_url = best_img.get("url")
                    media_type = "image"
                    if not message_text:
                        message_text = "[Видеосообщение]"

            elif att_type == "sticker":
                # Ignore stickers — no meaningful text
                pass

            if media_url:
                break  # use first recognised attachment

        # Skip if completely empty
        if not message_text.strip() and not media_url:
            logger.debug("VK empty message for peer=%s, skipping", peer_id_str)
            return

        # Parse timestamp
        message_timestamp = utc_now()
        if date_ts:
            try:
                message_timestamp = datetime.fromtimestamp(int(date_ts), tz=timezone.utc)
            except (ValueError, TypeError):
                pass

        # ── Bot commands ─────────────────────────────────────────────────────
        if message_text.startswith("/"):
            try:
                if access_token is None:
                    access_token = await self.channel_binding_service.get_access_token(binding_id)
                from app.services.bot_commands_service import dispatch_command_generic
                handled = await dispatch_command_generic(
                    command=message_text,
                    chat_id=peer_id_str,
                    binding=binding,
                    send_fn=self._make_command_send_fn(access_token, int(peer_id_str), binding),
                    db=self.db,
                )
                if handled:
                    return
            except Exception as exc:
                logger.warning("VK bot command dispatch failed: %s", exc)

        # ── Find or create conversation ──────────────────────────────────────
        # Resolve user info from VK API
        user_name: Optional[str] = None
        user_username: Optional[str] = None
        try:
            if access_token is None:
                access_token = await self.channel_binding_service.get_access_token(binding_id)
            user_info = await self._get_user_info(access_token, int(from_id_str))
            if user_info:
                user_name = f"{user_info.get('first_name', '')} {user_info.get('last_name', '')}".strip() or None
                user_username = user_info.get("screen_name")
        except Exception as exc:
            logger.debug("VK: could not resolve user info for from_id=%s: %s", from_id_str, exc)

        conversation = await self._find_or_create_conversation(
            agent_id=binding.agent_id,
            external_user_id=peer_id_str,
            external_user_name=user_name,
            external_user_username=user_username,
        )

        # ── Persist user message ─────────────────────────────────────────────
        msg_metadata: dict[str, Any] = {}
        if media_url:
            msg_metadata["media_url"] = media_url
        if media_type:
            msg_metadata["media_type"] = media_type

        dedup_id = (
            str(uuid.uuid5(VK_MSG_NS, f"{binding_id}:{peer_id_str}:{message_id}"))
            if message_id
            else str(uuid.uuid4())
        )
        user_message = Message(
            message_id=dedup_id,
            conversation_id=conversation.conversation_id,
            agent_id=binding.agent_id,
            role=MessageRole.USER,
            content=message_text,
            channel=MessageChannel.VK,
            external_message_id=str(message_id) if message_id else None,
            external_user_id=peer_id_str,
            timestamp=message_timestamp,
            metadata=msg_metadata,
            media_url=media_url,
            media_type=media_type,
        )
        inserted = await self.db.try_create_message(user_message)
        if not inserted:
            logger.info("Duplicate VK message peer=%s msg_id=%s — skipping", peer_id_str, message_id)
            return

        # ── Skip agent if human is handling ─────────────────────────────────
        status_value = get_enum_value(conversation.status)
        if status_value in (ConversationStatus.NEEDS_HUMAN.value, ConversationStatus.HUMAN_ACTIVE.value):
            return

        # Skip agent if no text/image for processing
        vision_url = media_url if media_type == "image" else None
        if not message_text.strip() and not vision_url:
            logger.debug("VK: no text/image for agent (peer=%s), skipping", peer_id_str)
            return

        try:
            from app.services.agent_reply_coordinator import cancel_timer_trigger
            await cancel_timer_trigger(conversation.conversation_id)
        except Exception:
            pass

        # ── Payment guard ────────────────────────────────────────────────────
        try:
            from app.models.payment import get_payment_settings
            from app.services.payment.guard import GuardResult, check as payment_check
            pay_settings = await get_payment_settings(binding.binding_id)
            if pay_settings and pay_settings.enabled:
                if access_token is None:
                    access_token = await self.channel_binding_service.get_access_token(binding_id)

                from app.services.payment.guard import check_feature as feat_check
                if is_voice and pay_settings.feature_gates.voice:
                    feat_result = await feat_check(
                        binding_id=binding.binding_id,
                        external_user_id=peer_id_str,
                        feature="voice",
                        settings=pay_settings,
                    )
                    if feat_result != GuardResult.ALLOW:
                        paywall_msg = pay_settings.paywall_messages.voice
                        await self._send_paywall(
                            binding.binding_id, access_token, int(peer_id_str), paywall_msg, pay_settings
                        )
                        return

                if media_type == "image" and pay_settings.feature_gates.images:
                    feat_result = await feat_check(
                        binding_id=binding.binding_id,
                        external_user_id=peer_id_str,
                        feature="images",
                        settings=pay_settings,
                    )
                    if feat_result != GuardResult.ALLOW:
                        paywall_msg = pay_settings.paywall_messages.images
                        await self._send_paywall(
                            binding.binding_id, access_token, int(peer_id_str), paywall_msg, pay_settings
                        )
                        return

                if pay_settings.free_message_limit_enabled:
                    guard_result = await payment_check(
                        binding_id=binding.binding_id,
                        external_user_id=peer_id_str,
                        settings=pay_settings,
                    )
                else:
                    guard_result = GuardResult.ALLOW

                if guard_result == GuardResult.BLOCK_SEND_INVOICE:
                    await self._send_paywall(
                        binding.binding_id, access_token, int(peer_id_str),
                        pay_settings.paywall_messages.limit_reached, pay_settings,
                    )
                    return
        except Exception as exc:
            logger.warning("VK payment guard error: %s", exc)

        # ── Invoke agent ─────────────────────────────────────────────────────
        try:
            from app.models.agent_config import AgentConfig
            from app.services.agent_service import create_agent_service
            from app.services.channel_sender import VkSender
            from app.services.conversation_service import build_conversation_history_for_agent

            agent_data = await self.db.get_agent(binding.agent_id)
            if not agent_data:
                logger.error("VK: agent %s not found", binding.agent_id)
                return

            agent_config = AgentConfig.from_dict(agent_data["config"])
            conversation_history = await build_conversation_history_for_agent(
                self.db,
                conversation.conversation_id,
                message_text,
                agent_context_reset_at=conversation.agent_context_reset_at,
            )

            vk_sender = VkSender(self, self.db)
            agent_service = create_agent_service(agent_config, self.db, vk_sender)
            await agent_service.process_message(
                user_message=message_text,
                conversation_id=conversation.conversation_id,
                conversation_history=conversation_history,
                user_media_url=vision_url,
            )
        except Exception as exc:
            logger.exception("VK agent processing error (peer=%s): %s", peer_id_str, exc)

    # -------------------------------------------------------------------------
    # Outbound — send message
    # -------------------------------------------------------------------------

    def _make_command_send_fn(self, access_token: str, peer_id: int, binding: Any):
        """Factory for send_fn used by dispatch_command_generic (supports media)."""
        group_id = int(binding.channel_account_id) if binding.channel_account_id else None

        async def send_fn(text, *, media_url=None, media_type=None):
            await self._send_message_raw(
                access_token,
                peer_id,
                text,
                media_url=media_url,
                media_type=media_type,
                group_id=group_id,
            )

        return send_fn

    async def send_message(
        self,
        binding_id: str,
        peer_id: str,
        message_text: str,
        media_url: Optional[str] = None,
        media_type: Optional[str] = None,
        keyboard: Optional[dict] = None,
    ) -> None:
        """Send a message to a VK user/chat via messages.send."""
        access_token = await self.channel_binding_service.get_access_token(binding_id)
        binding = await self.channel_binding_service.get_binding(binding_id)
        group_id = (
            int(binding.channel_account_id)
            if binding and binding.channel_account_id
            else None
        )
        text = _truncate_vk_text(message_text or "")
        await self._send_message_raw(
            access_token=access_token,
            peer_id=int(peer_id),
            text=text,
            media_url=media_url,
            media_type=media_type,
            keyboard=keyboard,
            group_id=group_id,
        )

    async def _send_message_raw(
        self,
        access_token: str,
        peer_id: int,
        text: str,
        media_url: Optional[str] = None,
        media_type: Optional[str] = None,
        keyboard: Optional[dict] = None,
        group_id: Optional[int] = None,
        append_url_on_upload_failure: bool = True,
    ) -> None:
        """Low-level send via VK messages.send.

        Handles media upload → attach. Falls back to URL in text on failure
        (except intro video: empty text + media_type=video).
        """
        attachment: Optional[str] = None

        if append_url_on_upload_failure and not text and media_type == "video":
            append_url_on_upload_failure = False

        if media_url and media_type:
            try:
                attachment = await self._upload_and_get_attachment(
                    access_token, peer_id, media_url, media_type, group_id=group_id
                )
            except Exception as exc:
                if append_url_on_upload_failure:
                    logger.warning(
                        "VK media upload failed (peer=%s type=%s): %s — sending URL in text",
                        peer_id, media_type, exc,
                    )
                    if text:
                        text = f"{text}\n{media_url}"
                    else:
                        text = media_url
                else:
                    logger.warning(
                        "VK media upload failed (peer=%s type=%s): %s — skipping attachment",
                        peer_id, media_type, exc,
                    )

        if not text and not attachment:
            return

        params: dict[str, Any] = {
            "peer_id": peer_id,
            "random_id": _vk_random_id(),
            "access_token": access_token,
            "v": VK_API_VERSION,
        }
        if text:
            params["message"] = text
        if attachment:
            params["attachment"] = attachment
        if keyboard:
            params["keyboard"] = json.dumps(keyboard, ensure_ascii=False)

        max_attempts = 3 if attachment else 1
        async with httpx.AsyncClient(timeout=30.0) as client:
            for attempt in range(max_attempts):
                resp = await client.post(f"{VK_API_BASE}messages.send", params=params)
                data = resp.json()
                if "error" not in data:
                    logger.info("VK: sent message to peer=%s", peer_id)
                    return
                logger.error(
                    "VK messages.send error (peer=%s attempt=%s): %s",
                    peer_id, attempt + 1, data["error"],
                )
                if attempt < max_attempts - 1:
                    await asyncio.sleep(1)

    # -------------------------------------------------------------------------
    # Media upload helpers
    # -------------------------------------------------------------------------

    async def _upload_and_get_attachment(
        self,
        access_token: str,
        peer_id: int,
        media_url: str,
        media_type: str,
        group_id: Optional[int] = None,
    ) -> str:
        """Upload media to VK and return an attachment string like photo123_456.

        For images: photos.getMessagesUploadServer → upload → photos.saveMessagesPhoto
        For video: video.save → upload → video{owner_id}_{video_id}
        For audio/documents: docs.getMessagesUploadServer → upload → docs.save
        """
        async with httpx.AsyncClient(timeout=60.0) as client:
            if media_type == "image":
                return await self._upload_photo(client, access_token, peer_id, media_url)
            if media_type == "video":
                return await self._upload_video(client, access_token, media_url, group_id)
            doc_type = "audio_message" if media_type == "audio" else "doc"
            return await self._upload_doc(client, access_token, peer_id, media_url, doc_type)

    async def _upload_photo(
        self, client: httpx.AsyncClient, access_token: str, peer_id: int, image_url: str
    ) -> str:
        # Step 1: get upload server
        r1 = await client.get(
            f"{VK_API_BASE}photos.getMessagesUploadServer",
            params={"peer_id": peer_id, "access_token": access_token, "v": VK_API_VERSION},
        )
        upload_url = r1.json()["response"]["upload_url"]

        # Step 2: download source image and upload to VK
        img_resp = await client.get(image_url)
        img_resp.raise_for_status()
        r2 = await client.post(upload_url, files={"photo": ("photo.jpg", img_resp.content, "image/jpeg")})
        upload_data = r2.json()

        # Step 3: save
        r3 = await client.get(
            f"{VK_API_BASE}photos.saveMessagesPhoto",
            params={
                "photo": upload_data.get("photo", ""),
                "server": upload_data.get("server", ""),
                "hash": upload_data.get("hash", ""),
                "access_token": access_token,
                "v": VK_API_VERSION,
            },
        )
        saved = r3.json()["response"][0]
        return f"photo{saved['owner_id']}_{saved['id']}"

    async def _upload_video(
        self,
        client: httpx.AsyncClient,
        access_token: str,
        media_url: str,
        group_id: Optional[int],
    ) -> str:
        """Upload MP4 via video.save and return attachment string video{owner}_{id}."""
        if not group_id:
            raise ValueError("group_id required for VK video upload")

        r1 = await client.get(
            f"{VK_API_BASE}video.save",
            params={
                "group_id": group_id,
                "is_private": 1,
                "wallpost": 0,
                "name": "intro",
                "access_token": access_token,
                "v": VK_API_VERSION,
            },
        )
        save_data = r1.json()
        if "error" in save_data:
            raise RuntimeError(f"video.save failed: {save_data['error']}")

        save_resp = save_data["response"]
        upload_url = save_resp["upload_url"]
        owner_id = save_resp["owner_id"]
        video_id = save_resp["video_id"]

        video_resp = await client.get(media_url)
        video_resp.raise_for_status()
        r2 = await client.post(
            upload_url,
            files={"video_file": ("intro.mp4", video_resp.content, "video/mp4")},
        )
        r2.raise_for_status()

        return f"video{owner_id}_{video_id}"

    async def _upload_doc(
        self, client: httpx.AsyncClient, access_token: str, peer_id: int, doc_url: str, doc_type: str
    ) -> str:
        # Step 1: get upload server
        r1 = await client.get(
            f"{VK_API_BASE}docs.getMessagesUploadServer",
            params={
                "peer_id": peer_id,
                "type": doc_type,
                "access_token": access_token,
                "v": VK_API_VERSION,
            },
        )
        upload_url = r1.json()["response"]["upload_url"]

        # Step 2: download and upload
        doc_resp = await client.get(doc_url)
        doc_resp.raise_for_status()
        filename = "audio.ogg" if doc_type == "audio_message" else "doc.bin"
        content_type = "audio/ogg" if doc_type == "audio_message" else "application/octet-stream"
        r2 = await client.post(upload_url, files={"file": (filename, doc_resp.content, content_type)})
        upload_data = r2.json()

        # Step 3: save
        r3 = await client.post(
            f"{VK_API_BASE}docs.save",
            params={
                "file": upload_data.get("file", ""),
                "access_token": access_token,
                "v": VK_API_VERSION,
            },
        )
        saved_data = r3.json().get("response", {})
        if doc_type == "audio_message":
            doc = saved_data.get("audio_message", saved_data.get("doc", {}))
        else:
            doc = saved_data.get("doc", {})
        return f"doc{doc.get('owner_id', '')}_{doc.get('id', '')}"

    # -------------------------------------------------------------------------
    # Payment helper
    # -------------------------------------------------------------------------

    async def _send_paywall(
        self,
        binding_id: str,
        access_token: str,
        peer_id: int,
        paywall_message: str,
        pay_settings: Any,
    ) -> None:
        """Send paywall message with payment link buttons (EXTERNAL_LINK only)."""
        try:
            from app.models.payment import PaymentProvider, list_payment_plans
            from app.services.payment.factory import get_payment_provider

            if pay_settings.provider == PaymentProvider.EXTERNAL_LINK:
                provider = get_payment_provider(pay_settings)
                plans = await list_payment_plans(binding_id, active_only=True)
                if plans:
                    text, pay_buttons = await provider.get_payment_message(plans, pay_settings)
                    keyboard = _build_vk_payment_keyboard(pay_buttons)
                    combined = f"{paywall_message}\n\n{text}" if text and text != paywall_message else paywall_message
                    await self._send_message_raw(
                        access_token=access_token,
                        peer_id=peer_id,
                        text=combined,
                        keyboard=keyboard,
                    )
                    return
        except Exception as exc:
            logger.warning("VK _send_paywall error: %s", exc)

        await self._send_message_raw(access_token=access_token, peer_id=peer_id, text=paywall_message)

    # -------------------------------------------------------------------------
    # User info helper
    # -------------------------------------------------------------------------

    async def _get_user_info(self, access_token: str, user_id: int) -> Optional[dict]:
        """Fetch VK user info for conversation metadata."""
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(
                    f"{VK_API_BASE}users.get",
                    params={
                        "user_ids": user_id,
                        "fields": "screen_name",
                        "access_token": access_token,
                        "v": VK_API_VERSION,
                    },
                )
                items = resp.json().get("response", [])
                return items[0] if items else None
        except Exception:
            return None

    # -------------------------------------------------------------------------
    # Conversation management
    # -------------------------------------------------------------------------

    async def _find_or_create_conversation(
        self,
        agent_id: str,
        external_user_id: str,
        external_user_name: Optional[str] = None,
        external_user_username: Optional[str] = None,
    ) -> Conversation:
        """Find existing VK conversation or create a new one."""
        try:
            all_conversations = await self.db.list_conversations(agent_id=agent_id, limit=200)
            for conv in all_conversations:
                if (
                    get_enum_value(conv.channel) == MessageChannel.VK.value
                    and conv.external_user_id == external_user_id
                ):
                    updates: dict[str, Any] = {}
                    if external_user_name and not conv.external_user_name:
                        updates["external_user_name"] = external_user_name
                    if external_user_username and not conv.external_user_username:
                        updates["external_user_username"] = external_user_username
                    if updates:
                        await self.db.update_conversation(conv.conversation_id, **updates)
                        conv.external_user_name = external_user_name or conv.external_user_name
                        conv.external_user_username = external_user_username or conv.external_user_username
                    return conv
        except Exception as exc:
            logger.warning("Error searching for existing VK conversation: %s", exc)

        conversation_id = str(uuid.uuid4())
        conversation = Conversation(
            conversation_id=conversation_id,
            agent_id=agent_id,
            channel=MessageChannel.VK,
            external_user_id=external_user_id,
            external_user_name=external_user_name,
            external_user_username=external_user_username,
            status=ConversationStatus.AI_ACTIVE,
            marketing_status=MarketingStatus.NEW,
            created_at=utc_now(),
            updated_at=utc_now(),
        )
        await self.db.create_conversation(conversation)
        return conversation

    # -------------------------------------------------------------------------
    # Verification
    # -------------------------------------------------------------------------

    async def verify_group_token(self, access_token: str, group_id: str) -> bool:
        """Verify VK community token via groups.getById."""
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(
                    f"{VK_API_BASE}groups.getById",
                    params={
                        "group_id": group_id,
                        "access_token": access_token,
                        "v": VK_API_VERSION,
                    },
                )
                data = resp.json()
                if "error" in data:
                    logger.warning("VK groups.getById error: %s", data["error"])
                    return False
                groups = data.get("response", {}).get("groups", [])
                if groups:
                    group = groups[0]
                    logger.info(
                        "VK group verified: %s (id=%s)",
                        group.get("name", "?"),
                        group.get("id", "?"),
                    )
                    return True
                return False
        except Exception as exc:
            logger.error("VK verify_group_token error: %s", exc, exc_info=True)
            return False
