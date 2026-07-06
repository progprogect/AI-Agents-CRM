"""Channel sender abstraction for sending messages through different channels."""

import logging
import uuid
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any, Optional
from app.models.message import MessageChannel
from app.utils.datetime_utils import to_utc_iso_string, utc_now

if TYPE_CHECKING:
    from app.services.instagram_service import InstagramService
    from app.services.max_service import MaxService
    from app.services.telegram_service import TelegramService
    from app.services.twilio_service import TwilioWhatsAppService
    from app.services.vk_service import VKService
    from app.services.whatsapp_service import WhatsAppService

logger = logging.getLogger(__name__)


def _build_reply_markup(quick_replies: list[str]) -> dict:
    """Build a Telegram ReplyKeyboardMarkup or remove-keyboard dict.

    Buttons are grouped into rows of two. An empty list produces
    ``remove_keyboard: true`` to dismiss any previously shown keyboard.
    """
    if quick_replies:
        rows = [quick_replies[i:i + 2] for i in range(0, len(quick_replies), 2)]
        return {
            "keyboard": [[{"text": btn} for btn in row] for row in rows],
            "one_time_keyboard": True,
            "resize_keyboard": True,
        }
    return {"remove_keyboard": True}


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

    def __init__(self, db: Any):
        """Initialize web chat sender."""
        self.db = db

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
        db: Any,
    ):
        """Initialize Instagram sender."""
        self.instagram_service = instagram_service
        self.db = db

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
            conversation = await self.db.get_conversation(conversation_id)
            if not conversation:
                raise ValueError(f"Conversation {conversation_id} not found")

            # Handle both enum and string channel (from the database)
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
            binding_service = ChannelBindingService(self.db, secrets_manager)

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
        db: Any,
    ):
        """Initialize Telegram sender."""
        self.telegram_service = telegram_service
        self.db = db

    async def send_message(
        self,
        conversation_id: str,
        message_text: str,
        binding_id: Optional[str] = None,
        external_user_id: Optional[str] = None,
        media_url: Optional[str] = None,
        media_type: Optional[str] = None,
        quick_replies: Optional[list[str]] = None,
        **kwargs,
    ) -> None:
        """Send message (text and/or media) via Telegram Bot API."""
        if not binding_id or not external_user_id:
            # Try to get from conversation
            conversation = await self.db.get_conversation(conversation_id)
            if not conversation:
                raise ValueError(f"Conversation {conversation_id} not found")

            # Handle both enum and string channel (from the database)
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
            binding_service = ChannelBindingService(self.db, secrets_manager)

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

        # Build reply_markup only when quick_replies was explicitly provided.
        # None → no keyboard change (e.g. timer messages).
        # []  → remove any existing keyboard.
        # [...] → show the keyboard.
        reply_markup = _build_reply_markup(quick_replies) if quick_replies is not None else None

        # Send message via Telegram service
        await self.telegram_service.send_message(
            binding_id=binding_id,
            chat_id=external_user_id,
            message_text=message_text,
            media_url=media_url,
            media_type=media_type,
            reply_markup=reply_markup,
        )

        # Note: Agent message is already saved in AgentService.process_message
        # before calling ChannelSender.send_message, so we don't save it again here


class WhatsAppSender(ChannelSender):
    """Sender for WhatsApp channel — supports both Meta Cloud API and Twilio providers."""

    def __init__(
        self,
        whatsapp_service: Optional["WhatsAppService"],
        db: Any,
        twilio_service: Optional["TwilioWhatsAppService"] = None,
    ):
        self.whatsapp_service = whatsapp_service
        self.twilio_service = twilio_service
        self.db = db

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
        binding_service = ChannelBindingService(self.db, secrets_manager)

        if not external_user_id or not binding_id:
            conversation = await self.db.get_conversation(conversation_id)
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

            twilio_svc = self.twilio_service or TwilioWhatsAppService(self.db)
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
                _bs = ChannelBindingService(self.db, _sm)
                self.whatsapp_service = WhatsAppService(_bs, self.db, get_settings())

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


class VkSender(ChannelSender):
    """Sender for VK (ВКонтакте) channel."""

    def __init__(self, vk_service: "VKService", db: Any):
        self.vk_service = vk_service
        self.db = db

    async def send_message(
        self,
        conversation_id: str,
        message_text: str,
        binding_id: Optional[str] = None,
        external_user_id: Optional[str] = None,
        media_url: Optional[str] = None,
        media_type: Optional[str] = None,
        quick_replies: Optional[list[str]] = None,
        **kwargs,
    ) -> None:
        """Send message via VK messages.send with optional inline keyboard."""
        if not binding_id or not external_user_id:
            conversation = await self.db.get_conversation(conversation_id)
            if not conversation:
                raise ValueError(f"Conversation {conversation_id} not found")

            from app.utils.enum_helpers import get_enum_value
            if get_enum_value(conversation.channel) != MessageChannel.VK.value:
                raise ValueError(f"Conversation {conversation_id} is not a VK conversation")

            from app.services.channel_binding_service import ChannelBindingService
            from app.storage.resolver import get_secrets_manager
            binding_service = ChannelBindingService(self.db, get_secrets_manager())
            bindings = await binding_service.get_bindings_by_agent(
                agent_id=conversation.agent_id,
                channel_type=MessageChannel.VK.value,
                active_only=True,
            )
            if not bindings:
                raise ValueError(f"No active VK binding for agent {conversation.agent_id}")
            binding_id = bindings[0].binding_id
            external_user_id = conversation.external_user_id

        if not external_user_id:
            raise ValueError("external_user_id (peer_id) is required for VK messages")

        from app.services.vk_service import _build_vk_inline_keyboard
        keyboard = _build_vk_inline_keyboard(quick_replies) if quick_replies else None

        await self.vk_service.send_message(
            binding_id=binding_id,
            peer_id=external_user_id,
            message_text=message_text,
            media_url=media_url,
            media_type=media_type,
            keyboard=keyboard,
        )


class MaxSender(ChannelSender):
    """Sender for Max messenger channel."""

    def __init__(self, max_service: "MaxService", db: Any):
        self.max_service = max_service
        self.db = db

    async def send_message(
        self,
        conversation_id: str,
        message_text: str,
        binding_id: Optional[str] = None,
        external_user_id: Optional[str] = None,
        media_url: Optional[str] = None,
        media_type: Optional[str] = None,
        quick_replies: Optional[list[str]] = None,
        **kwargs,
    ) -> None:
        """Send message via Max POST /messages with optional inline keyboard."""
        if not binding_id or not external_user_id:
            conversation = await self.db.get_conversation(conversation_id)
            if not conversation:
                raise ValueError(f"Conversation {conversation_id} not found")

            from app.utils.enum_helpers import get_enum_value
            if get_enum_value(conversation.channel) != MessageChannel.MAX.value:
                raise ValueError(f"Conversation {conversation_id} is not a Max conversation")

            from app.services.channel_binding_service import ChannelBindingService
            from app.storage.resolver import get_secrets_manager
            binding_service = ChannelBindingService(self.db, get_secrets_manager())
            bindings = await binding_service.get_bindings_by_agent(
                agent_id=conversation.agent_id,
                channel_type=MessageChannel.MAX.value,
                active_only=True,
            )
            if not bindings:
                raise ValueError(f"No active Max binding for agent {conversation.agent_id}")
            binding_id = bindings[0].binding_id
            external_user_id = conversation.external_user_id

        if not external_user_id:
            raise ValueError("external_user_id (chat_id) is required for Max messages")

        from app.services.max_service import _build_max_inline_keyboard
        keyboard = (
            _build_max_inline_keyboard(quick_replies, conversation_id=conversation_id)
            if quick_replies
            else None
        )

        await self.max_service.send_message(
            binding_id=binding_id,
            chat_id=external_user_id,
            message_text=message_text,
            media_url=media_url,
            media_type=media_type,
            keyboard=keyboard,
        )


def get_channel_sender(
    channel: MessageChannel,
    db: Any,
    instagram_service: Optional["InstagramService"] = None,
    telegram_service: Optional["TelegramService"] = None,
    whatsapp_service: Optional["WhatsAppService"] = None,
    twilio_service: Optional["TwilioWhatsAppService"] = None,
    vk_service: Optional["VKService"] = None,
    max_service: Optional["MaxService"] = None,
) -> ChannelSender:
    """Get appropriate channel sender for the given channel."""
    if channel == MessageChannel.WEB_CHAT:
        return WebChatSender(db)
    elif channel == MessageChannel.INSTAGRAM:
        if not instagram_service:
            raise ValueError("InstagramService is required for Instagram channel")
        return InstagramSender(instagram_service, db)
    elif channel == MessageChannel.TELEGRAM:
        if not telegram_service:
            raise ValueError("TelegramService is required for Telegram channel")
        return TelegramSender(telegram_service, db)
    elif channel == MessageChannel.WHATSAPP:
        return WhatsAppSender(whatsapp_service, db, twilio_service=twilio_service)
    elif channel == MessageChannel.VK:
        if not vk_service:
            from app.services.channel_binding_service import ChannelBindingService
            from app.services.vk_service import VKService
            from app.storage.resolver import get_secrets_manager
            binding_service = ChannelBindingService(db, get_secrets_manager())
            vk_service = VKService(binding_service, db)
        return VkSender(vk_service, db)
    elif channel == MessageChannel.MAX:
        if not max_service:
            from app.services.channel_binding_service import ChannelBindingService
            from app.services.max_service import MaxService
            from app.storage.resolver import get_secrets_manager
            binding_service = ChannelBindingService(db, get_secrets_manager())
            max_service = MaxService(binding_service, db)
        return MaxSender(max_service, db)
    else:
        raise ValueError(f"Unsupported channel: {channel}")

