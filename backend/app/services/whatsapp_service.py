"""WhatsApp Cloud API service for handling messages."""

import logging
import uuid
from typing import Any

import httpx

from app.config import Settings
from app.models.conversation import Conversation, ConversationStatus, MarketingStatus
from app.models.message import Message, MessageChannel, MessageRole
from app.services.channel_binding_service import ChannelBindingService
from app.utils.datetime_utils import utc_now

logger = logging.getLogger(__name__)

GRAPH_API_BASE = "https://graph.facebook.com/v18.0"


class WhatsAppService:
    """Service for WhatsApp Cloud API messaging integration."""

    def __init__(
        self,
        channel_binding_service: ChannelBindingService,
        dynamodb: Any,
        settings: Settings,
    ):
        self.channel_binding_service = channel_binding_service
        self.dynamodb = dynamodb
        self.settings = settings

    async def handle_webhook_event(self, payload: dict[str, Any]) -> None:
        """
        Route incoming WhatsApp webhook event to the correct agent.

        Payload structure (WhatsApp Cloud API):
        {
          "object": "whatsapp_business_account",
          "entry": [{
            "id": "<WABA_ID>",
            "changes": [{
              "value": {
                "messaging_product": "whatsapp",
                "metadata": {"phone_number_id": "<ID>", "display_phone_number": "+1..."},
                "messages": [{"from": "...", "id": "...", "text": {"body": "..."}, "type": "text"}]
              },
              "field": "messages"
            }]
          }]
        }
        """
        if payload.get("object") != "whatsapp_business_account":
            logger.debug("Ignoring non-whatsapp_business_account webhook payload")
            return

        for entry in payload.get("entry", []):
            for change in entry.get("changes", []):
                if change.get("field") != "messages":
                    continue
                value = change.get("value", {})
                phone_number_id = value.get("metadata", {}).get("phone_number_id")
                messages = value.get("messages", [])

                if not phone_number_id or not messages:
                    continue

                # Find binding by phone_number_id (stored as channel_account_id)
                binding = await self.channel_binding_service.get_binding_by_account_id(
                    channel_type="whatsapp", account_id=phone_number_id
                )
                if not binding:
                    logger.warning(
                        f"No WhatsApp binding found for phone_number_id={phone_number_id}"
                    )
                    continue

                for msg in messages:
                    await self._process_message(msg, binding)

    async def _process_message(
        self,
        msg: dict[str, Any],
        binding: Any,
    ) -> None:
        """Process a single incoming WhatsApp message."""
        msg_type = msg.get("type")
        sender_phone = msg.get("from")
        wa_message_id = msg.get("id")

        if msg_type != "text":
            logger.info(f"Ignoring non-text WhatsApp message type: {msg_type}")
            return

        text_body = msg.get("text", {}).get("body", "").strip()
        if not text_body:
            return

        logger.info(
            f"WhatsApp message from {sender_phone} via binding {binding.binding_id}: "
            f"{text_body[:80]}"
        )

        # Get or create conversation
        conversation_id = f"wa_{binding.binding_id}_{sender_phone}"
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

        # Save incoming message
        message = Message(
            conversation_id=conversation_id,
            message_id=wa_message_id or str(uuid.uuid4()),
            agent_id=binding.agent_id,
            role=MessageRole.USER,
            content=text_body,
            channel=MessageChannel.WHATSAPP,
            external_message_id=wa_message_id,
            external_user_id=sender_phone,
            timestamp=utc_now(),
            metadata={"whatsapp_message_id": wa_message_id},
        )
        await self.dynamodb.create_message(message)

        # Skip if conversation is handled by a human operator
        from app.utils.enum_helpers import get_enum_value
        if get_enum_value(conversation.status) in (
            ConversationStatus.NEEDS_HUMAN.value,
            ConversationStatus.HUMAN_ACTIVE.value,
        ):
            logger.info(
                f"Conversation {conversation_id} handled by human — skipping AI"
            )
            return

        # Process through agent and send reply
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
            # Exclude the just-saved user message from history
            if conversation_history and (
                conversation_history[-1].get("role", "").lower() == "user"
                and conversation_history[-1].get("content", "").strip() == text_body.strip()
            ):
                conversation_history = conversation_history[:-1]

            wa_sender = WhatsAppSender(self, self.dynamodb, twilio_service=None)
            agent_service = create_agent_service(agent_config, self.dynamodb, wa_sender)
            await agent_service.process_message(
                user_message=text_body,
                conversation_id=conversation_id,
                conversation_history=conversation_history,
            )
        except Exception as exc:
            logger.error(f"WhatsApp AI response error: {exc}", exc_info=True)

    async def send_message(
        self,
        phone_number_id: str,
        access_token: str,
        to: str,
        text: str,
    ) -> dict[str, Any]:
        """Send a WhatsApp text message via Cloud API."""
        url = f"{GRAPH_API_BASE}/{phone_number_id}/messages"
        payload = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": to,
            "type": "text",
            "text": {"preview_url": False, "body": text},
        }
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
        }
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(url, json=payload, headers=headers)
            if not response.is_success:
                logger.error(
                    f"WhatsApp send_message failed: {response.status_code} {response.text}"
                )
            else:
                logger.info(f"WhatsApp message sent to {to}")
            return response.json() if response.content else {}
