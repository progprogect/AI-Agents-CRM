"""Twilio WhatsApp service — send, receive, and verify credentials."""

import base64
import hashlib
import hmac
import logging
import uuid
from typing import Any, Optional

import httpx

from app.models.conversation import Conversation, ConversationStatus, MarketingStatus
from app.models.message import Message, MessageChannel, MessageRole
from app.utils.datetime_utils import utc_now

logger = logging.getLogger(__name__)

TWILIO_API_BASE = "https://api.twilio.com/2010-04-01"


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

        if not raw_from.startswith("whatsapp:") or not body:
            logger.debug("Twilio webhook: skipping non-text or missing fields")
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

        await self._process_message(
            sender_phone=sender_phone,
            to_number=to_number,
            body=body,
            message_sid=message_sid,
            binding=binding,
            binding_service=binding_service,
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
            metadata={"twilio_message_sid": message_sid},
        )
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
            from app.services.agent_service import create_agent_service
            from app.services.channel_sender import WhatsAppSender

            agent_data = await self.dynamodb.get_agent(binding.agent_id)
            if not agent_data or "config" not in agent_data:
                logger.error(f"Agent {binding.agent_id} not found or has no config")
                return

            agent_config = AgentConfig.from_dict(agent_data["config"])

            history_messages = await self.dynamodb.list_messages(
                conversation_id=conversation_id, limit=50, reverse=True
            )
            conversation_history = [
                {"role": get_enum_value(m.role), "content": m.content}
                for m in reversed(history_messages)
            ]
            if conversation_history and (
                conversation_history[-1].get("role", "").lower() == "user"
                and conversation_history[-1].get("content", "").strip() == body.strip()
            ):
                conversation_history = conversation_history[:-1]

            wa_sender = WhatsAppSender(None, self.dynamodb, twilio_service=self)
            agent_service = create_agent_service(agent_config, self.dynamodb, wa_sender)
            await agent_service.process_message(
                user_message=body,
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
    ) -> dict[str, Any]:
        """Send a WhatsApp text message via Twilio Programmable Messaging API."""
        url = f"{TWILIO_API_BASE}/Accounts/{account_sid}/Messages.json"

        # Normalise to whatsapp:+E164 format regardless of how numbers are stored
        def _wa(num: str) -> str:
            num = num.replace("whatsapp:", "").lstrip("+")
            return f"whatsapp:+{num}"

        from_addr = _wa(from_number)
        to_addr = _wa(to)

        data = {
            "From": from_addr,
            "To": to_addr,
            "Body": text,
        }

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                url,
                data=data,
                auth=(account_sid, auth_token),
            )

        if not response.is_success:
            logger.error(
                f"Twilio send_message failed: {response.status_code} {response.text}"
            )
        else:
            logger.info(f"Twilio WhatsApp message sent to {to}")

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
