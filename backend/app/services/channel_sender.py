"""Channel sender abstraction for sending messages through different channels."""

import logging
import uuid
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any, Optional
from app.models.message import MessageChannel
from app.utils.datetime_utils import to_utc_iso_string, utc_now

if TYPE_CHECKING:
    from app.services.instagram_service import InstagramService
    from app.services.telegram_service import TelegramService
    from app.services.twilio_service import TwilioWhatsAppService
    from app.services.whatsapp_service import WhatsAppService

logger = logging.getLogger(__name__)


class ChannelSender(ABC):
    """Abstract base class for channel senders."""

    @abstractmethod
    async def send_message(
        self,
        conversation_id: str,
        message_text: str,
        media_url: Optional[str] = None,
        media_type: Optional[str] = None,
        **kwargs,
    ) -> None:
        """Send message (text and/or media) through the channel."""
        pass


class WebChatSender(ChannelSender):
    """Sender for web chat channel (WebSocket)."""

    def __init__(self, dynamodb: Any):
        """Initialize web chat sender."""
        self.dynamodb = dynamodb

    async def send_message(
        self,
        conversation_id: str,
        message_text: str,
        media_url: Optional[str] = None,
        media_type: Optional[str] = None,
        message_id: Optional[str] = None,
        **kwargs,
    ) -> None:
        """Push message to the active WebSocket connection for this conversation.

        If the user is not currently connected (browser closed, reconnect pending)
        the message is already persisted in the DB — the client will pick it up
        on the next poll/reconnect.  Not having an active socket is not an error.
        """
        from app.api.websocket import connection_manager

        payload: dict = {
            "type": "message",
            "message_id": message_id or str(uuid.uuid4()),
            "role": "agent",
            "content": message_text,
            "timestamp": to_utc_iso_string(utc_now()),
        }
        if media_url:
            payload["media_url"] = media_url
            payload["media_type"] = media_type

        delivered = await connection_manager.send_message(conversation_id, payload)
        if delivered:
            logger.info(
                "WebChatSender: WS push delivered for conversation %s", conversation_id
            )
        else:
            logger.info(
                "WebChatSender: no active WS for conversation %s "
                "(message persisted in DB; client will receive on reconnect)",
                conversation_id,
            )


class InstagramSender(ChannelSender):
    """Sender for Instagram channel."""

    def __init__(
        self,
        instagram_service: "InstagramService",
        dynamodb: Any,
    ):
        """Initialize Instagram sender."""
        self.instagram_service = instagram_service
        self.dynamodb = dynamodb

    async def send_message(
        self,
        conversation_id: str,
        message_text: str,
        binding_id: Optional[str] = None,
        external_user_id: Optional[str] = None,
        media_url: Optional[str] = None,
        media_type: Optional[str] = None,
        **kwargs,
    ) -> None:
        """Send message (text and/or media) via Instagram Graph API."""
        if not binding_id or not external_user_id:
            # Try to get from conversation
            conversation = await self.dynamodb.get_conversation(conversation_id)
            if not conversation:
                raise ValueError(f"Conversation {conversation_id} not found")

            # Handle both enum and string channel (from DynamoDB)
            from app.utils.enum_helpers import get_enum_value
            conversation_channel = get_enum_value(conversation.channel)
            if conversation_channel != MessageChannel.INSTAGRAM.value:
                raise ValueError(
                    f"Conversation {conversation_id} is not an Instagram conversation"
                )

            # Find binding by agent_id
            from app.services.channel_binding_service import ChannelBindingService
            from app.storage.resolver import get_secrets_manager

            secrets_manager = get_secrets_manager()
            binding_service = ChannelBindingService(self.dynamodb, secrets_manager)

            bindings = await binding_service.get_bindings_by_agent(
                agent_id=conversation.agent_id,
                channel_type=MessageChannel.INSTAGRAM.value,
                active_only=True,
            )

            if not bindings:
                raise ValueError(
                    f"No active Instagram binding found for agent {conversation.agent_id}"
                )

            binding_id = bindings[0].binding_id
            external_user_id = conversation.external_user_id

        if not external_user_id:
            raise ValueError("external_user_id is required for Instagram messages")

        # Send message via Instagram service
        await self.instagram_service.send_message(
            binding_id=binding_id,
            recipient_id=external_user_id,
            message_text=message_text,
            media_url=media_url,
            media_type=media_type,
        )

        # Note: Agent message is already saved in AgentService.process_message
        # before calling ChannelSender.send_message, so we don't save it again here


class TelegramSender(ChannelSender):
    """Sender for Telegram channel."""

    def __init__(
        self,
        telegram_service: "TelegramService",
        dynamodb: Any,
    ):
        """Initialize Telegram sender."""
        self.telegram_service = telegram_service
        self.dynamodb = dynamodb

    async def send_message(
        self,
        conversation_id: str,
        message_text: str,
        binding_id: Optional[str] = None,
        external_user_id: Optional[str] = None,
        media_url: Optional[str] = None,
        media_type: Optional[str] = None,
        **kwargs,
    ) -> None:
        """Send message (text and/or media) via Telegram Bot API."""
        if not binding_id or not external_user_id:
            # Try to get from conversation
            conversation = await self.dynamodb.get_conversation(conversation_id)
            if not conversation:
                raise ValueError(f"Conversation {conversation_id} not found")

            # Handle both enum and string channel (from DynamoDB)
            from app.utils.enum_helpers import get_enum_value
            conversation_channel = get_enum_value(conversation.channel)
            if conversation_channel != MessageChannel.TELEGRAM.value:
                raise ValueError(
                    f"Conversation {conversation_id} is not a Telegram conversation"
                )

            # Find binding by agent_id
            from app.services.channel_binding_service import ChannelBindingService
            from app.storage.resolver import get_secrets_manager

            secrets_manager = get_secrets_manager()
            binding_service = ChannelBindingService(self.dynamodb, secrets_manager)

            bindings = await binding_service.get_bindings_by_agent(
                agent_id=conversation.agent_id,
                channel_type=MessageChannel.TELEGRAM.value,
                active_only=True,
            )

            if not bindings:
                raise ValueError(
                    f"No active Telegram binding found for agent {conversation.agent_id}"
                )

            binding_id = bindings[0].binding_id
            external_user_id = conversation.external_user_id

        if not external_user_id:
            raise ValueError("external_user_id (chat_id) is required for Telegram messages")

        # Send message via Telegram service
        await self.telegram_service.send_message(
            binding_id=binding_id,
            chat_id=external_user_id,
            message_text=message_text,
            media_url=media_url,
            media_type=media_type,
        )

        # Note: Agent message is already saved in AgentService.process_message
        # before calling ChannelSender.send_message, so we don't save it again here


class WhatsAppSender(ChannelSender):
    """Sender for WhatsApp channel — supports both Meta Cloud API and Twilio providers."""

    def __init__(
        self,
        whatsapp_service: Optional["WhatsAppService"],
        dynamodb: Any,
        twilio_service: Optional["TwilioWhatsAppService"] = None,
    ):
        self.whatsapp_service = whatsapp_service
        self.twilio_service = twilio_service
        self.dynamodb = dynamodb

    async def send_message(
        self,
        conversation_id: str,
        message_text: str,
        binding_id: Optional[str] = None,
        external_user_id: Optional[str] = None,
        media_url: Optional[str] = None,
        media_type: Optional[str] = None,
        **kwargs,
    ) -> None:
        """Send message (text and/or media) via the appropriate WhatsApp provider."""
        from app.services.channel_binding_service import ChannelBindingService
        from app.storage.resolver import get_secrets_manager

        secrets_manager = get_secrets_manager()
        binding_service = ChannelBindingService(self.dynamodb, secrets_manager)

        if not external_user_id or not binding_id:
            conversation = await self.dynamodb.get_conversation(conversation_id)
            if not conversation:
                raise ValueError(f"Conversation {conversation_id} not found")
            external_user_id = external_user_id or conversation.external_user_id

            if not binding_id:
                bindings = await binding_service.get_bindings_by_agent(
                    agent_id=conversation.agent_id,
                    channel_type="whatsapp",
                    active_only=True,
                )
                if not bindings:
                    raise ValueError(
                        f"No active WhatsApp binding for agent {conversation.agent_id}"
                    )
                binding_id = bindings[0].binding_id

        if not external_user_id:
            raise ValueError("external_user_id (recipient phone) is required for WhatsApp")

        binding = await binding_service.get_binding(binding_id)
        if not binding:
            raise ValueError(f"WhatsApp binding {binding_id} not found")

        access_token = await binding_service.get_access_token(binding_id)
        provider = (binding.metadata or {}).get("provider", "meta")

        logger.info(
            "WhatsApp outbound: conversation_id=%s binding_id=%s provider=%s to=%s "
            "has_media=%s media_type=%s text_chars=%s",
            conversation_id,
            binding_id,
            provider,
            external_user_id,
            bool(media_url),
            media_type or "",
            len(message_text or ""),
        )

        if provider == "twilio":
            from app.services.twilio_service import TwilioWhatsAppService

            twilio_svc = self.twilio_service or TwilioWhatsAppService(self.dynamodb)
            # For Twilio bindings:
            #   channel_account_id = from_number (WhatsApp-enabled Twilio number)
            #   metadata.account_sid = Twilio Account SID
            from_number = binding.channel_account_id
            account_sid = (binding.metadata or {}).get("account_sid", "")
            if not account_sid:
                raise ValueError(
                    f"Twilio binding {binding_id} is missing metadata.account_sid"
                )
            try:
                await twilio_svc.send_message(
                    account_sid=account_sid,
                    auth_token=access_token,
                    from_number=from_number,
                    to=external_user_id,
                    text=message_text,
                    media_url=media_url,
                    media_type=media_type,
                )
            except Exception:
                logger.error(
                    "WhatsAppSender Twilio send raised: conversation_id=%s binding_id=%s to=%s",
                    conversation_id,
                    binding_id,
                    external_user_id,
                    exc_info=True,
                )
                raise
        else:
            # Default: Meta Cloud API
            if not self.whatsapp_service:
                from app.services.whatsapp_service import WhatsAppService
                from app.services.channel_binding_service import ChannelBindingService
                from app.config import get_settings
                from app.storage.resolver import get_secrets_manager as _gsm

                _sm = _gsm()
                _bs = ChannelBindingService(self.dynamodb, _sm)
                self.whatsapp_service = WhatsAppService(_bs, self.dynamodb, get_settings())

            try:
                await self.whatsapp_service.send_message(
                    phone_number_id=binding.channel_account_id,
                    access_token=access_token,
                    to=external_user_id,
                    text=message_text,
                    media_url=media_url,
                    media_type=media_type,
                )
            except Exception:
                logger.error(
                    "WhatsAppSender Meta Cloud API send raised: conversation_id=%s "
                    "binding_id=%s phone_number_id=%s to=%s",
                    conversation_id,
                    binding_id,
                    binding.channel_account_id,
                    external_user_id,
                    exc_info=True,
                )
                raise


def get_channel_sender(
    channel: MessageChannel,
    dynamodb: Any,
    instagram_service: Optional["InstagramService"] = None,
    telegram_service: Optional["TelegramService"] = None,
    whatsapp_service: Optional["WhatsAppService"] = None,
    twilio_service: Optional["TwilioWhatsAppService"] = None,
) -> ChannelSender:
    """Get appropriate channel sender for the given channel."""
    if channel == MessageChannel.WEB_CHAT:
        return WebChatSender(dynamodb)
    elif channel == MessageChannel.INSTAGRAM:
        if not instagram_service:
            raise ValueError("InstagramService is required for Instagram channel")
        return InstagramSender(instagram_service, dynamodb)
    elif channel == MessageChannel.TELEGRAM:
        if not telegram_service:
            raise ValueError("TelegramService is required for Telegram channel")
        return TelegramSender(telegram_service, dynamodb)
    elif channel == MessageChannel.WHATSAPP:
        return WhatsAppSender(whatsapp_service, dynamodb, twilio_service=twilio_service)
    else:
        raise ValueError(f"Unsupported channel: {channel}")

