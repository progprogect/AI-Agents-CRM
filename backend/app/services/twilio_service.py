"""Twilio WhatsApp service — send, receive, and verify credentials."""

import base64
import hashlib
import hmac
import logging
import uuid
from typing import Any, Optional

import httpx

from app.config import get_settings
from app.models.conversation import Conversation, ConversationStatus, MarketingStatus
from app.models.message import Message, MessageChannel, MessageRole
from app.utils.datetime_utils import utc_now

logger = logging.getLogger(__name__)

TWILIO_API_BASE = "https://api.twilio.com/2010-04-01"
_TWILIO_LOG_BODY_MAX = 2000
_TWILIO_LOG_URL_MAX = 200


def _twilio_media_url_for_log(url: str | None) -> str:
    if not url:
        return ""
    u = url.strip()
    if len(u) > _TWILIO_LOG_URL_MAX:
        return f"{u[:_TWILIO_LOG_URL_MAX]}…(len={len(u)})"
    return u


class TwilioWhatsAppService:
    """Service for Twilio WhatsApp messaging integration.

    Credentials stored in ChannelBinding:
      channel_account_id  → WhatsApp-enabled Twilio number, e.g. "+14155238886"
      access_token        → Twilio Auth Token (via SecretsManager)
      metadata.provider   → "twilio"
      metadata.account_sid → Twilio Account SID (ACxxx...)
    """

    def __init__(self, dynamodb: Any) -> None:
        self.dynamodb = dynamodb

    # ── Signature validation ──────────────────────────────────────────────────

    def validate_signature(
        self,
        auth_token: str,
        url: str,
        params: dict[str, str],
        signature: str,
    ) -> bool:
        """Validate X-Twilio-Signature header (HMAC-SHA1).

        Twilio computes: HMAC-SHA1(auth_token, url + sorted_params_concat)
        """
        s = url + "".join(f"{k}{params[k]}" for k in sorted(params))
        expected = base64.b64encode(
            hmac.new(auth_token.encode(), s.encode(), hashlib.sha1).digest()
        ).decode()
        return hmac.compare_digest(expected, signature)

    # ── Incoming webhook ──────────────────────────────────────────────────────

    async def handle_webhook(
        self,
        form_data: dict[str, str],
        binding_service: Any,
    ) -> None:
        """Process an incoming Twilio WhatsApp message.

        form_data keys (Twilio sends application/x-www-form-urlencoded):
          From        whatsapp:+375255092206
          To          whatsapp:+14155238886
          Body        message text
          MessageSid  SM...
          AccountSid  AC...
          NumMedia    0
        """
        raw_from = form_data.get("From", "")
        raw_to = form_data.get("To", "")
        body = form_data.get("Body", "").strip()
        message_sid = form_data.get("MessageSid", "")

        num_media = int(form_data.get("NumMedia", "0") or "0")
        media_url_0 = form_data.get("MediaUrl0")
        media_content_type = form_data.get("MediaContentType0", "")

        # Skip if no text and no media
        if not raw_from.startswith("whatsapp:") or (not body and num_media == 0):
            logger.debug("Twilio webhook: skipping — no content")
            return

        # Normalize: strip whatsapp: prefix and leading + for consistent IDs
        sender_phone = raw_from.replace("whatsapp:", "").lstrip("+")
        to_number = raw_to.replace("whatsapp:", "")

        logger.info(
            f"Twilio WhatsApp message from={sender_phone} to={to_number}: {body[:80]!r}"
        )

        # Find binding by from_number stored in metadata
        binding = await self._find_binding_by_to_number(binding_service, to_number)
        if not binding:
            logger.warning(
                f"No Twilio WhatsApp binding found for to_number={to_number}"
            )
            return

        # Resolve media info from Twilio form data
        media_url: str | None = None
        media_type: str | None = None
        if num_media > 0 and media_url_0:
            media_url = media_url_0
            if media_content_type.startswith("image/"):
                media_type = "image"
            elif media_content_type.startswith("video/"):
                media_type = "video"
            elif media_content_type.startswith("audio/"):
                media_type = "audio"
            else:
                media_type = "document"

        await self._process_message(
            sender_phone=sender_phone,
            to_number=to_number,
            body=body,
            message_sid=message_sid,
            binding=binding,
            binding_service=binding_service,
            media_url=media_url,
            media_type=media_type,
            media_content_type=media_content_type,
        )

    async def _find_binding_by_to_number(
        self, binding_service: Any, to_number: str
    ) -> Optional[Any]:
        """Find a Twilio binding by to_number.

        For Twilio bindings channel_account_id stores the from_number (the
        WhatsApp-enabled Twilio phone number). We try multiple normalizations
        because users may save the number with or without the leading '+'.
        """
        # Normalise: try both "+number" and "number" (without +)
        candidates = []
        stripped = to_number.lstrip("+")
        if to_number.startswith("+"):
            candidates = [to_number, stripped]   # try with + first
        else:
            candidates = [f"+{to_number}", to_number]  # try with + first

        for candidate in candidates:
            binding = await binding_service.get_binding_by_account_id(
                channel_type="whatsapp", account_id=candidate
            )
            if binding and (binding.metadata or {}).get("provider") == "twilio" and binding.is_active:
                logger.info(
                    f"Found Twilio binding {binding.binding_id} for to_number={candidate}"
                )
                return binding

        logger.warning(
            f"No active Twilio binding found for to_number={to_number} "
            f"(tried: {candidates})"
        )
        return None

    async def _process_message(
        self,
        sender_phone: str,
        to_number: str,
        body: str,
        message_sid: str,
        binding: Any,
        binding_service: Any,
        media_url: str | None = None,
        media_type: str | None = None,
        media_content_type: str = "",
    ) -> None:
        """Create/update conversation and call the agent."""
        conversation_id = f"twilio_wa_{binding.binding_id}_{sender_phone}"
        conversation = await self.dynamodb.get_conversation(conversation_id)

        if not conversation:
            conversation = Conversation(
                conversation_id=conversation_id,
                agent_id=binding.agent_id,
                channel=MessageChannel.WHATSAPP,
                external_conversation_id=sender_phone,
                external_user_id=sender_phone,
                status=ConversationStatus.AI_ACTIVE,
                marketing_status=MarketingStatus.NEW,
                created_at=utc_now(),
                updated_at=utc_now(),
            )
            await self.dynamodb.create_conversation(conversation)

        final_media_url = media_url
        agent_user_message = body
        msg_metadata: dict = {"twilio_message_sid": message_sid}
        agent_row: dict | None = None

        if media_type == "image" and media_url:
            account_sid = (binding.metadata or {}).get("account_sid", "") or ""
            if account_sid:
                try:
                    auth_token = await binding_service.get_access_token(binding.binding_id)
                    agent_row = await self.dynamodb.get_agent(binding.agent_id)
                    if agent_row and agent_row.get("config"):
                        from app.services.inbound_media_pipeline import (
                            compose_user_message_for_agent,
                            prepare_inbound_image_for_chat,
                        )

                        prepared = await prepare_inbound_image_for_chat(
                            download_url=media_url,
                            http_basic_auth=(account_sid, auth_token),
                            content_type_hint=media_content_type or "image/jpeg",
                            agent_id=binding.agent_id,
                            agent_config=agent_row["config"],
                        )
                        if prepared:
                            final_media_url = prepared.public_url
                            msg_metadata["inbound_media_source"] = "twilio_cloudinary"
                            msg_metadata["image_context"] = prepared.summary
                            agent_user_message = compose_user_message_for_agent(
                                body, prepared.summary
                            )
                except Exception as exc:
                    logger.warning(
                        "Twilio inbound image pipeline skipped: %s",
                        exc,
                        exc_info=True,
                    )

        if final_media_url:
            msg_metadata["media_url"] = final_media_url
        if media_type:
            msg_metadata["media_type"] = media_type

        message = Message(
            conversation_id=conversation_id,
            message_id=message_sid or str(uuid.uuid4()),
            agent_id=binding.agent_id,
            role=MessageRole.USER,
            content=body,
            channel=MessageChannel.WHATSAPP,
            external_message_id=message_sid,
            external_user_id=sender_phone,
            timestamp=utc_now(),
            metadata=msg_metadata,
            media_url=final_media_url,
            media_type=media_type,
        )
        try_create = getattr(self.dynamodb, "try_create_message", None)
        if callable(try_create):
            inserted = await try_create(message)
            if not inserted:
                logger.info(
                    "Twilio webhook duplicate MessageSid=%s for %s — skipping (already processed)",
                    message_sid,
                    conversation_id,
                )
                return
        else:
            await self.dynamodb.create_message(message)

        # Skip AI if human is handling
        from app.utils.enum_helpers import get_enum_value

        if get_enum_value(conversation.status) in (
            ConversationStatus.NEEDS_HUMAN.value,
            ConversationStatus.HUMAN_ACTIVE.value,
        ):
            logger.info(
                f"Conversation {conversation_id} handled by human — skipping AI"
            )
            return

        try:
            from app.models.agent_config import AgentConfig
            from app.services.agent_service import (
                create_agent_service,
                organization_id_from_agent_row,
            )
            from app.services.channel_sender import WhatsAppSender
            from app.services.conversation_service import build_conversation_history_for_agent

            agent_data = agent_row or await self.dynamodb.get_agent(binding.agent_id)
            if not agent_data or "config" not in agent_data:
                logger.error(f"Agent {binding.agent_id} not found or has no config")
                return

            agent_config = AgentConfig.from_dict(agent_data["config"])

            conversation_history = await build_conversation_history_for_agent(
                self.dynamodb,
                conversation_id,
                body,
                agent_context_reset_at=conversation.agent_context_reset_at,
            )

            wa_sender = WhatsAppSender(None, self.dynamodb, twilio_service=self)
            agent_service = create_agent_service(
                agent_config,
                self.dynamodb,
                wa_sender,
                organization_id=organization_id_from_agent_row(agent_data),
            )

            settings = get_settings()
            if settings.agent_reply_debounce_seconds > 0:
                from app.services.agent_reply_coordinator import notify_user_message_saved
                from app.storage.redis import get_redis_client

                redis_client = get_redis_client()
                if await redis_client.ping():
                    mod_early = await agent_service.run_pre_moderation_guard(
                        agent_user_message, conversation_id
                    )
                    if mod_early and mod_early.get("escalate"):
                        return
                    notify_result = await notify_user_message_saved(
                        conversation_id,
                        agent_user_message=agent_user_message,
                        last_user_plain_content=body.strip(),
                    )
                    if notify_result == "scheduled":
                        return

            await agent_service.process_message(
                user_message=agent_user_message,
                conversation_id=conversation_id,
                conversation_history=conversation_history,
            )
        except Exception as exc:
            logger.error(f"Twilio WhatsApp AI response error: {exc}", exc_info=True)

    # ── Outgoing message ──────────────────────────────────────────────────────

    async def send_message(
        self,
        account_sid: str,
        auth_token: str,
        from_number: str,
        to: str,
        text: str,
        media_url: str | None = None,
        media_type: str | None = None,
    ) -> dict[str, Any]:
        """Send a WhatsApp text and/or media message via Twilio Programmable Messaging API."""
        url = f"{TWILIO_API_BASE}/Accounts/{account_sid}/Messages.json"

        def _wa(num: str) -> str:
            num = num.replace("whatsapp:", "").lstrip("+")
            return f"whatsapp:+{num}"

        from_addr = _wa(from_number)
        to_addr = _wa(to)

        data: dict[str, str] = {"From": from_addr, "To": to_addr}
        if text:
            data["Body"] = text
        if media_url:
            data["MediaUrl"] = media_url

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(url, data=data, auth=(account_sid, auth_token))
        except httpx.RequestError as exc:
            logger.error(
                "Twilio WhatsApp send request failed (network): account_sid=%s from=%s to=%s "
                "has_media=%s media_type=%s body_len=%s media_url=%s error=%s",
                account_sid,
                from_addr,
                to_addr,
                bool(media_url),
                media_type or "",
                len(text or ""),
                _twilio_media_url_for_log(media_url),
                exc,
                exc_info=True,
            )
            return {}

        if not response.is_success:
            body = (response.text or "")[:_TWILIO_LOG_BODY_MAX]
            logger.error(
                "Twilio WhatsApp send rejected: status=%s account_sid=%s from=%s to=%s "
                "has_media=%s media_type=%s body_len=%s media_url=%s response=%s",
                response.status_code,
                account_sid,
                from_addr,
                to_addr,
                bool(media_url),
                media_type or "",
                len(text or ""),
                _twilio_media_url_for_log(media_url),
                body,
            )
        else:
            label = f"{media_type} + text" if (media_url and text) else ("media" if media_url else "text")
            logger.info(
                "Twilio WhatsApp sent: kind=%s to=%s body_len=%s has_media=%s",
                label,
                to,
                len(text or ""),
                bool(media_url),
            )

        return response.json() if response.content else {}

    # ── Credentials verification ──────────────────────────────────────────────

    async def verify_credentials(self, account_sid: str, auth_token: str) -> bool:
        """Verify Twilio Account SID + Auth Token by calling the Accounts API."""
        url = f"{TWILIO_API_BASE}/Accounts/{account_sid}.json"
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.get(url, auth=(account_sid, auth_token))

        if response.is_success:
            logger.info(f"Twilio credentials verified for account {account_sid}")
            return True

        logger.warning(
            f"Twilio credentials invalid for account {account_sid}: "
            f"{response.status_code} {response.text}"
        )
        return False
