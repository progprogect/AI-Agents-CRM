"""Max messenger service — Bot API integration.

Handles incoming webhook events (message_created, message_callback, bot_started),
sends messages with full media support, inline keyboards, bot commands,
payment guard, and webhook subscription management.

API docs: https://dev.max.ru/docs-api
Base URL: https://platform-api.max.ru
Auth: Authorization: {token}  (no Bearer prefix)

Binding fields:
    channel_account_id  — Bot username or numeric ID
    access_token        — Bot token (via Secrets Manager)
    metadata.webhook_secret  — Shared secret for X-Max-Bot-Api-Secret header verification
"""

from __future__ import annotations

import asyncio
import json
import logging
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

MAX_API_BASE = "https://platform-api.max.ru"
MAX_MSG_NS = uuid.UUID("8ba7b810-9dad-11d1-80b4-00c04fd430c8")

# Max text limit: 4000 chars
MAX_MESSAGE_MAX_LENGTH = 4000

# Retry POST /messages when video/audio is still processing on MAX servers
_MAX_ATTACHMENT_NOT_READY_RETRIES = 5
_MAX_ATTACHMENT_NOT_READY_DELAYS = (2, 4, 8, 16)

# Bot commands registered on Max
MAX_BOT_COMMANDS = [
    {"name": "restart", "description": "Начать новый чат"},
    {"name": "questionnaire", "description": "Моя анкета"},
    {"name": "paysupport", "description": "Вопросы по оплате"},
    {"name": "feedback", "description": "Обратная связь"},
    {"name": "supportproject", "description": "Поддержать проект"},
]


def _is_max_attachment_not_ready_response(status_code: int, response_text: str) -> bool:
    """True when MAX has not finished processing an uploaded media attachment."""
    if status_code in (200, 201):
        return False
    try:
        data = json.loads(response_text)
    except (json.JSONDecodeError, TypeError):
        return False
    return data.get("code") == "attachment.not.ready"


def _truncate_max_text(text: str, max_len: int = MAX_MESSAGE_MAX_LENGTH) -> str:
    if len(text) <= max_len:
        return text
    suffix = "\n…"
    take = max_len - len(suffix)
    return text[:take] + suffix if take > 64 else text[:max_len]


def _build_max_inline_keyboard(
    quick_replies: list[str],
    conversation_id: Optional[str] = None,
) -> Optional[dict]:
    """Build Max inline_keyboard attachment from quick_reply labels."""
    if not quick_replies:
        return None
    rows = [quick_replies[i:i + 2] for i in range(0, len(quick_replies), 2)]
    conv_hint = (conversation_id or "")[:8] or None
    buttons = []
    for row in rows:
        buttons.append([
            {
                "type": "callback",
                "text": label[:40],
                "payload": json.dumps(
                    {
                        "cmd": "reply",
                        "text": label,
                        **({"conv": conv_hint} if conv_hint else {}),
                    },
                    ensure_ascii=False,
                )[:1024],
            }
            for label in row
        ])
    return {"type": "inline_keyboard", "payload": {"buttons": buttons}}


def _build_max_payment_keyboard(pay_buttons: list[dict]) -> Optional[dict]:
    """Build Max inline_keyboard with link buttons for payment plans."""
    if not pay_buttons:
        return None
    buttons = []
    for btn in pay_buttons:
        if btn.get("url"):
            buttons.append([{
                "type": "link",
                "text": btn["name"][:40],
                "url": btn["url"],
            }])
        else:
            buttons.append([{
                "type": "callback",
                "text": btn["name"][:40],
                "payload": json.dumps({"cmd": "pay", "plan_id": btn["plan_id"]}, ensure_ascii=False)[:1024],
            }])
    return {"type": "inline_keyboard", "payload": {"buttons": buttons}}


class MaxService:
    """Service for Max messenger Bot API integration."""

    def __init__(
        self,
        channel_binding_service: ChannelBindingService,
        db: Any,
        settings: Optional[Settings] = None,
    ):
        self.channel_binding_service = channel_binding_service
        self.db = db
        self.settings = settings or get_settings()

    def _auth_headers(self, token: str) -> dict:
        """Max requires 'Authorization: {token}' WITHOUT 'Bearer' prefix."""
        return {"Authorization": token, "Content-Type": "application/json"}

    # -------------------------------------------------------------------------
    # Inbound webhook handler
    # -------------------------------------------------------------------------

    async def handle_webhook_event(
        self,
        payload: dict[str, Any],
        binding_id: str,
        received_secret: Optional[str] = None,
    ) -> None:
        """Handle incoming Max webhook event."""
        try:
            binding = await self.channel_binding_service.get_binding(binding_id)
            if not binding or not binding.is_active:
                logger.warning("Max binding %s not found or inactive", binding_id)
                return
            if binding.channel_type not in (ChannelType.MAX, ChannelType.MAX.value):
                return

            # Verify webhook secret if configured
            expected_secret = (binding.metadata or {}).get("webhook_secret", "")
            if expected_secret and received_secret != expected_secret:
                logger.warning("Max binding %s: X-Max-Bot-Api-Secret mismatch", binding_id)
                return

            update_type = payload.get("update_type", "")

            if update_type == "message_callback":
                await self._handle_message_callback(payload, binding, binding_id)
            elif update_type == "bot_started":
                await self._handle_bot_started(payload, binding, binding_id)
            elif update_type == "message_created":
                await self._handle_message_created(payload, binding, binding_id)
            else:
                logger.debug("Max binding %s: unhandled update_type=%s", binding_id, update_type)

        except Exception as exc:
            logger.exception("MaxService.handle_webhook_event error for binding %s: %s", binding_id, exc)

    async def _handle_bot_started(
        self, payload: dict[str, Any], binding: Any, binding_id: str
    ) -> None:
        """Handle bot_started — user pressed Start button."""
        user = payload.get("user", {})
        chat_id = str(user.get("user_id", ""))
        if not chat_id:
            return

        try:
            access_token = await self.channel_binding_service.get_access_token(binding_id)
            from app.services.bot_commands_service import dispatch_command_generic
            await dispatch_command_generic(
                command="/restart",
                chat_id=chat_id,
                binding=binding,
                send_fn=lambda text, *, media_url=None, media_type=None: self._send_message_raw(
                    access_token,
                    int(chat_id),
                    text,
                    media_url=media_url,
                    media_type=media_type,
                ),
                db=self.db,
            )
        except Exception as exc:
            logger.warning("Max bot_started dispatch error (chat=%s): %s", chat_id, exc)

    async def _handle_message_callback(
        self, payload: dict[str, Any], binding: Any, binding_id: str
    ) -> None:
        """Handle message_callback (inline button press)."""
        callback = payload.get("callback", {})
        callback_id = callback.get("callback_id")
        cb_payload_raw = callback.get("payload", "")
        user = callback.get("user", {})
        chat_id_raw = user.get("user_id")

        if not callback_id or not chat_id_raw:
            return

        chat_id = str(chat_id_raw)

        access_token: Optional[str] = None
        # Always answer callback
        try:
            access_token = await self.channel_binding_service.get_access_token(binding_id)
            await self._answer_callback(access_token, callback_id)
        except Exception as exc:
            logger.warning("Max POST /answers failed: %s", exc)

        # Parse payload
        try:
            cb_payload = json.loads(cb_payload_raw) if cb_payload_raw else {}
        except (json.JSONDecodeError, ValueError):
            cb_payload = {}

        cmd = cb_payload.get("cmd", "")
        if cmd == "restart":
            try:
                token = access_token or await self.channel_binding_service.get_access_token(binding_id)
                from app.services.bot_commands_service import dispatch_command_generic
                await dispatch_command_generic(
                    command="/restart",
                    chat_id=chat_id,
                    binding=binding,
                    send_fn=lambda text, *, media_url=None, media_type=None, _token=token: self._send_message_raw(
                        _token,
                        int(chat_id),
                        text,
                        media_url=media_url,
                        media_type=media_type,
                    ),
                    db=self.db,
                )
            except Exception as exc:
                logger.warning("Max callback /restart failed: %s", exc)
        elif cmd == "reply":
            reply_text = cb_payload.get("text", "")
            if not reply_text:
                return
            conv_hint = (cb_payload.get("conv") or "").strip()
            if conv_hint:
                active = await self._get_active_conversation(binding.agent_id, chat_id)
                if not active or active.conversation_id[:8] != conv_hint:
                    try:
                        if access_token is None:
                            access_token = await self.channel_binding_service.get_access_token(binding_id)
                        await self._send_text(
                            access_token,
                            int(chat_id),
                            "Сессия устарела, нажмите /restart",
                        )
                    except Exception as exc:
                        logger.warning("Max stale-session reply failed: %s", exc)
                    return
            synthetic = {
                "update_type": "message_created",
                "message": {
                    "recipient": {"chat_id": chat_id_raw, "chat_type": "dialog", "user_id": chat_id_raw},
                    "body": {"mid": "", "seq": 0, "text": reply_text},
                    "sender": {"user_id": chat_id_raw, "is_bot": False},
                    "timestamp": 0,
                },
            }
            await self._handle_message_created(synthetic, binding, binding_id)

    async def _answer_callback(self, access_token: str, callback_id: str) -> None:
        """POST /answers to acknowledge callback press."""
        async with httpx.AsyncClient(timeout=10.0) as client:
            await client.post(
                f"{MAX_API_BASE}/answers",
                params={"callback_id": callback_id},
                headers=self._auth_headers(access_token),
                json={"notification": "✓"},
            )

    async def _handle_message_created(
        self, payload: dict[str, Any], binding: Any, binding_id: str
    ) -> None:
        """Handle message_created event — full inbound pipeline."""
        message_data = payload.get("message", {})
        sender = message_data.get("sender", {})
        recipient = message_data.get("recipient", {})
        body = message_data.get("body", {})

        sender_user_id = sender.get("user_id")
        is_bot = sender.get("is_bot", False)
        chat_id_raw = recipient.get("chat_id") or recipient.get("user_id")

        if is_bot:
            return
        if not sender_user_id or not chat_id_raw:
            return

        chat_id = str(chat_id_raw)
        msg_id = body.get("mid", "")
        raw_text = (body.get("text") or "").strip()
        attachments = body.get("attachments", []) or []
        ts_ms = message_data.get("timestamp", 0)

        message_text = raw_text
        media_url: Optional[str] = None
        media_type: Optional[str] = None
        is_voice = False
        access_token: Optional[str] = None

        # ── Process attachments ──────────────────────────────────────────────
        for att in attachments:
            att_type = att.get("type", "")
            att_payload = att.get("payload", {})

            if att_type == "image":
                url = att_payload.get("url")
                if url:
                    media_url = url
                    media_type = "image"

            elif att_type == "video":
                url = att_payload.get("url")
                if url:
                    media_url = url
                    media_type = "video"

            elif att_type == "audio":
                url = att_payload.get("url")
                if url:
                    is_voice = True
                    media_url = url
                    media_type = "audio"
                    # Transcribe audio via STT
                    try:
                        from app.services.stt_service import transcribe_from_url
                        transcript = await transcribe_from_url(url, language="ru")
                        if transcript:
                            message_text = transcript
                            logger.info(
                                "Max STT transcribed audio (chat=%s): %d chars",
                                chat_id, len(transcript),
                            )
                    except Exception as exc:
                        logger.warning("Max STT failed (chat=%s): %s", chat_id, exc)

            elif att_type == "file":
                url = att_payload.get("url")
                if url:
                    media_url = url
                    media_type = "document"

            elif att_type == "inline_keyboard":
                continue

            if media_url:
                break

        # Skip if completely empty
        if not message_text.strip() and not media_url:
            logger.debug("Max empty message for chat=%s, skipping", chat_id)
            return

        # Parse timestamp
        message_timestamp = utc_now()
        if ts_ms:
            try:
                message_timestamp = datetime.fromtimestamp(ts_ms / 1000.0, tz=timezone.utc)
            except (ValueError, TypeError):
                pass

        # Extract user info
        user_name = sender.get("name") or (
            f"{sender.get('first_name', '')} {sender.get('last_name', '')}".strip() or None
        )
        user_username = sender.get("username")

        # ── Bot commands ─────────────────────────────────────────────────────
        if message_text.startswith("/"):
            try:
                if access_token is None:
                    access_token = await self.channel_binding_service.get_access_token(binding_id)
                from app.services.bot_commands_service import dispatch_command_generic
                handled = await dispatch_command_generic(
                    command=message_text,
                    chat_id=chat_id,
                    binding=binding,
                    send_fn=lambda text, *, media_url=None, media_type=None: self._send_message_raw(
                        access_token,
                        int(chat_id),
                        text,
                        media_url=media_url,
                        media_type=media_type,
                    ),
                    db=self.db,
                )
                if handled:
                    return
            except Exception as exc:
                logger.warning("Max bot command dispatch failed: %s", exc)

        # ── Find or create conversation ──────────────────────────────────────
        conversation = await self._find_or_create_conversation(
            agent_id=binding.agent_id,
            external_user_id=chat_id,
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
            str(uuid.uuid5(MAX_MSG_NS, f"{binding_id}:{chat_id}:{msg_id}"))
            if msg_id
            else str(uuid.uuid4())
        )
        user_message = Message(
            message_id=dedup_id,
            conversation_id=conversation.conversation_id,
            agent_id=binding.agent_id,
            role=MessageRole.USER,
            content=message_text,
            channel=MessageChannel.MAX,
            external_message_id=msg_id or None,
            external_user_id=chat_id,
            timestamp=message_timestamp,
            metadata=msg_metadata,
            media_url=media_url,
            media_type=media_type,
        )
        inserted = await self.db.try_create_message(user_message)
        if not inserted:
            logger.info("Duplicate Max message chat=%s mid=%s — skipping", chat_id, msg_id)
            return

        # ── Skip agent if human is handling ─────────────────────────────────
        status_value = get_enum_value(conversation.status)
        if status_value in (ConversationStatus.NEEDS_HUMAN.value, ConversationStatus.HUMAN_ACTIVE.value):
            return

        vision_url = media_url if media_type == "image" else None
        if not message_text.strip() and not vision_url:
            logger.debug("Max: no text/image for agent (chat=%s), skipping", chat_id)
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
                        external_user_id=chat_id,
                        feature="voice",
                        settings=pay_settings,
                    )
                    if feat_result != GuardResult.ALLOW:
                        await self._send_paywall(
                            binding.binding_id, access_token, int(chat_id),
                            pay_settings.paywall_messages.voice, pay_settings,
                        )
                        return

                if media_type == "image" and pay_settings.feature_gates.images:
                    feat_result = await feat_check(
                        binding_id=binding.binding_id,
                        external_user_id=chat_id,
                        feature="images",
                        settings=pay_settings,
                    )
                    if feat_result != GuardResult.ALLOW:
                        await self._send_paywall(
                            binding.binding_id, access_token, int(chat_id),
                            pay_settings.paywall_messages.images, pay_settings,
                        )
                        return

                if pay_settings.free_message_limit_enabled:
                    guard_result = await payment_check(
                        binding_id=binding.binding_id,
                        external_user_id=chat_id,
                        settings=pay_settings,
                    )
                else:
                    guard_result = GuardResult.ALLOW

                if guard_result == GuardResult.BLOCK_SEND_INVOICE:
                    await self._send_paywall(
                        binding.binding_id, access_token, int(chat_id),
                        pay_settings.paywall_messages.limit_reached, pay_settings,
                    )
                    return
        except Exception as exc:
            logger.warning("Max payment guard error: %s", exc)

        # ── Invoke agent ─────────────────────────────────────────────────────
        try:
            from app.models.agent_config import AgentConfig
            from app.services.agent_service import create_agent_service
            from app.services.channel_sender import MaxSender
            from app.services.conversation_service import build_conversation_history_for_agent

            agent_data = await self.db.get_agent(binding.agent_id)
            if not agent_data:
                logger.error("Max: agent %s not found", binding.agent_id)
                return

            agent_config = AgentConfig.from_dict(agent_data["config"])
            conversation_history = await build_conversation_history_for_agent(
                self.db,
                conversation.conversation_id,
                message_text,
                agent_context_reset_at=conversation.agent_context_reset_at,
            )

            max_sender = MaxSender(self, self.db)
            agent_service = create_agent_service(agent_config, self.db, max_sender)
            await agent_service.process_message(
                user_message=message_text,
                conversation_id=conversation.conversation_id,
                conversation_history=conversation_history,
                user_media_url=vision_url,
            )
        except Exception as exc:
            logger.exception("Max agent processing error (chat=%s): %s", chat_id, exc)

    # -------------------------------------------------------------------------
    # Outbound — send message
    # -------------------------------------------------------------------------

    async def send_message(
        self,
        binding_id: str,
        chat_id: str,
        message_text: str,
        media_url: Optional[str] = None,
        media_type: Optional[str] = None,
        keyboard: Optional[dict] = None,
    ) -> None:
        """Send a message to a Max user via POST /messages."""
        access_token = await self.channel_binding_service.get_access_token(binding_id)
        await self._send_message_raw(
            access_token=access_token,
            chat_id=int(chat_id),
            text=message_text,
            media_url=media_url,
            media_type=media_type,
            keyboard=keyboard,
        )

    async def _send_text(self, access_token: str, chat_id: int, text: str) -> None:
        """Send a plain text message (used by command handlers)."""
        await self._send_message_raw(access_token=access_token, chat_id=chat_id, text=text)

    async def _send_message_raw(
        self,
        access_token: str,
        chat_id: int,
        text: str,
        media_url: Optional[str] = None,
        media_type: Optional[str] = None,
        keyboard: Optional[dict] = None,
    ) -> None:
        """Low-level Max message send.

        Handles:
          - Image: sent as URL attachment directly (no upload needed)
          - Audio/video/file: upload via /uploads then attach by token
          - Text: up to 4000 chars
        """
        body: dict[str, Any] = {}
        if text:
            body["text"] = _truncate_max_text(text)

        attachments = []

        if media_url and media_type:
            try:
                att = await self._build_media_attachment(access_token, media_url, media_type)
                if att:
                    attachments.append(att)
            except Exception as exc:
                logger.warning(
                    "Max media attachment failed (chat=%s type=%s): %s — appending URL to text",
                    chat_id, media_type, exc,
                )
                body["text"] = (body.get("text", "") + f"\n{media_url}").strip()

        if keyboard:
            attachments.append(keyboard)

        if attachments:
            body["attachments"] = attachments

        if not body.get("text") and not attachments:
            logger.debug("Max: nothing to send to chat=%s", chat_id)
            return

        async with httpx.AsyncClient(timeout=30.0) as client:
            for attempt in range(_MAX_ATTACHMENT_NOT_READY_RETRIES):
                resp = await client.post(
                    f"{MAX_API_BASE}/messages",
                    params={"chat_id": chat_id},
                    headers=self._auth_headers(access_token),
                    json=body,
                )
                if resp.status_code in (200, 201):
                    logger.info("Max: sent message to chat=%s", chat_id)
                    return
                if (
                    _is_max_attachment_not_ready_response(resp.status_code, resp.text)
                    and attempt < _MAX_ATTACHMENT_NOT_READY_RETRIES - 1
                ):
                    delay = _MAX_ATTACHMENT_NOT_READY_DELAYS[
                        min(attempt, len(_MAX_ATTACHMENT_NOT_READY_DELAYS) - 1)
                    ]
                    logger.info(
                        "Max attachment not ready (chat=%s), retry %d/%d in %ds",
                        chat_id,
                        attempt + 1,
                        _MAX_ATTACHMENT_NOT_READY_RETRIES,
                        delay,
                    )
                    await asyncio.sleep(delay)
                    continue
                logger.error("Max /messages error (chat=%s): %s", chat_id, resp.text)
                return

    # -------------------------------------------------------------------------
    # Media upload helpers
    # -------------------------------------------------------------------------

    async def _build_media_attachment(
        self, access_token: str, media_url: str, media_type: str
    ) -> Optional[dict]:
        """Build a Max attachment object for the given media.

        Images are sent via URL directly. Audio/video/file require upload.
        """
        if media_type == "image":
            return {"type": "image", "payload": {"url": media_url}}

        # For audio, video, file — upload to Max
        upload_type_map = {
            "audio": "audio",
            "video": "video",
            "document": "file",
        }
        max_upload_type = upload_type_map.get(media_type, "file")
        token = await self._upload_media(access_token, media_url, max_upload_type)
        if token:
            return {"type": media_type if media_type != "document" else "file", "payload": {"token": token}}
        return None

    async def _upload_media(
        self, access_token: str, media_url: str, upload_type: str, retries: int = 3
    ) -> Optional[str]:
        """Upload media to Max /uploads endpoint and return attachment token."""
        async with httpx.AsyncClient(timeout=60.0) as client:
            # Step 1: get upload URL (MAX API requires POST, not GET)
            r1 = await client.post(
                f"{MAX_API_BASE}/uploads",
                params={"type": upload_type},
                headers=self._auth_headers(access_token),
            )
            if r1.status_code != 200:
                raise ValueError(f"Max /uploads POST failed: {r1.text}")
            upload_url = r1.json().get("url")
            token = r1.json().get("token")  # for audio/video, token comes from upload server

            # Step 2: download source and upload via multipart
            src = await client.get(media_url)
            src.raise_for_status()
            r2 = await client.post(upload_url, files={"data": ("media", src.content, "application/octet-stream")})
            if r2.status_code not in (200, 201):
                raise ValueError(f"Max upload POST failed: {r2.text}")

            upload_result: dict[str, Any] = {}
            if r2.text.strip():
                try:
                    parsed = r2.json()
                    if isinstance(parsed, dict):
                        upload_result = parsed
                except json.JSONDecodeError:
                    logger.debug(
                        "Max upload response is not JSON (status=%s, len=%d)",
                        r2.status_code,
                        len(r2.content),
                    )

            final_token = upload_result.get("token") or token
            if not final_token:
                raise ValueError("Max upload succeeded but no attachment token received")
            return final_token

    # -------------------------------------------------------------------------
    # Payment helper
    # -------------------------------------------------------------------------

    async def _send_paywall(
        self,
        binding_id: str,
        access_token: str,
        chat_id: int,
        paywall_message: str,
        pay_settings: Any,
    ) -> None:
        """Send paywall message with payment link buttons."""
        try:
            from app.models.payment import PaymentProvider, list_payment_plans
            from app.services.payment.factory import get_payment_provider

            if pay_settings.provider == PaymentProvider.EXTERNAL_LINK:
                provider = get_payment_provider(pay_settings)
                plans = await list_payment_plans(binding_id, active_only=True)
                if plans:
                    text, pay_buttons = await provider.get_payment_message(plans, pay_settings)
                    keyboard = _build_max_payment_keyboard(pay_buttons)
                    combined = f"{paywall_message}\n\n{text}" if text and text != paywall_message else paywall_message
                    await self._send_message_raw(
                        access_token=access_token,
                        chat_id=chat_id,
                        text=combined,
                        keyboard=keyboard,
                    )
                    return
        except Exception as exc:
            logger.warning("Max _send_paywall error: %s", exc)

        await self._send_message_raw(access_token=access_token, chat_id=chat_id, text=paywall_message)

    # -------------------------------------------------------------------------
    # Conversation management
    # -------------------------------------------------------------------------

    async def _get_active_conversation(
        self,
        agent_id: str,
        external_user_id: str,
    ) -> Optional[Conversation]:
        """Return the active Max conversation for a user, if any."""
        try:
            all_conversations = await self.db.list_conversations(
                agent_id=agent_id,
                status=ConversationStatus.AI_ACTIVE,
                limit=200,
            )
            for conv in all_conversations or []:
                if (
                    get_enum_value(conv.channel) == MessageChannel.MAX.value
                    and conv.external_user_id == external_user_id
                ):
                    return conv
        except Exception as exc:
            logger.warning(
                "Error finding active Max conversation for user %s: %s",
                external_user_id,
                exc,
            )
        return None

    async def _find_or_create_conversation(
        self,
        agent_id: str,
        external_user_id: str,
        external_user_name: Optional[str] = None,
        external_user_username: Optional[str] = None,
    ) -> Conversation:
        """Find existing Max conversation or create a new one."""
        try:
            all_conversations = await self.db.list_conversations(agent_id=agent_id, limit=200)
            for conv in all_conversations:
                if (
                    get_enum_value(conv.channel) == MessageChannel.MAX.value
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
            logger.warning("Error searching for existing Max conversation: %s", exc)

        conversation_id = str(uuid.uuid4())
        conversation = Conversation(
            conversation_id=conversation_id,
            agent_id=agent_id,
            channel=MessageChannel.MAX,
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
    # Webhook management
    # -------------------------------------------------------------------------

    async def register_webhook(
        self, access_token: str, webhook_url: str, webhook_secret: str
    ) -> bool:
        """Register webhook subscription via POST /subscriptions."""
        body: dict[str, Any] = {
            "url": webhook_url,
            "update_types": [
                "message_created",
                "message_callback",
                "bot_started",
            ],
        }
        if webhook_secret:
            body["secret"] = webhook_secret

        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.post(
                    f"{MAX_API_BASE}/subscriptions",
                    headers=self._auth_headers(access_token),
                    json=body,
                )
                if resp.status_code in (200, 201):
                    logger.info("Max webhook registered: %s", webhook_url)
                    return True
                logger.warning("Max webhook registration failed (%s): %s", resp.status_code, resp.text)
                return False
        except Exception as exc:
            logger.error("Max register_webhook error: %s", exc, exc_info=True)
            return False

    async def unregister_webhook(self, access_token: str, webhook_url: str) -> None:
        """Remove a webhook subscription."""
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.delete(
                    f"{MAX_API_BASE}/subscriptions",
                    headers=self._auth_headers(access_token),
                    params={"url": webhook_url},
                )
                if resp.status_code not in (200, 204):
                    logger.warning("Max unregister_webhook failed: %s", resp.text)
        except Exception as exc:
            logger.warning("Max unregister_webhook error: %s", exc)

    async def set_bot_commands(self, access_token: str) -> None:
        """Register bot commands list on Max (shows in the commands menu)."""
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.patch(
                    f"{MAX_API_BASE}/me",
                    headers=self._auth_headers(access_token),
                    json={"commands": MAX_BOT_COMMANDS},
                )
                if resp.status_code in (200, 201):
                    logger.info("Max bot commands registered: %d commands", len(MAX_BOT_COMMANDS))
                else:
                    logger.warning("Max set_bot_commands failed (%s): %s", resp.status_code, resp.text)
        except Exception as exc:
            logger.warning("Max set_bot_commands error: %s", exc)

    # -------------------------------------------------------------------------
    # Verification
    # -------------------------------------------------------------------------

    async def verify_bot_token(self, access_token: str) -> Optional[dict]:
        """Verify Max bot token via GET /me. Returns bot info dict or None."""
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(
                    f"{MAX_API_BASE}/me",
                    headers=self._auth_headers(access_token),
                )
                if resp.status_code == 200:
                    data = resp.json()
                    logger.info(
                        "Max bot verified: @%s (user_id=%s)",
                        data.get("username", "?"),
                        data.get("user_id", "?"),
                    )
                    return data
                logger.warning("Max GET /me returned %s: %s", resp.status_code, resp.text)
                return None
        except Exception as exc:
            logger.error("Max verify_bot_token error: %s", exc, exc_info=True)
            return None
