"""Telegram service for handling Telegram Bot messaging."""

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
from app.storage.dynamodb import DynamoDBClient
from app.utils.datetime_utils import utc_now
from app.utils.enum_helpers import get_enum_value

logger = logging.getLogger(__name__)


class TelegramService:
    """Service for Telegram Bot messaging integration."""

    TELEGRAM_API_BASE_URL = "https://api.telegram.org/bot"

    def __init__(
        self,
        channel_binding_service: ChannelBindingService,
        dynamodb: DynamoDBClient,
        settings: Settings,
    ):
        """Initialize Telegram service."""
        self.channel_binding_service = channel_binding_service
        self.dynamodb = dynamodb
        self.settings = settings

    async def _get_file_url(self, bot_token: str, file_id: str) -> Optional[str]:
        """Resolve a Telegram file_id to a publicly accessible download URL."""
        url = f"{self.TELEGRAM_API_BASE_URL}{bot_token}/getFile?file_id={file_id}"
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(url)
                data = resp.json()
                if data.get("ok") and data.get("result", {}).get("file_path"):
                    file_path = data["result"]["file_path"]
                    return f"https://api.telegram.org/file/bot{bot_token}/{file_path}"
        except Exception as e:
            logger.warning(f"Could not resolve Telegram file_id {file_id}: {e}")
        return None

    async def handle_webhook_event(
        self, payload: dict[str, Any], binding_id: str
    ) -> None:
        """Handle incoming webhook event from Telegram."""
        try:
            binding = await self.channel_binding_service.get_binding(binding_id)
            if not binding or not binding.is_active:
                logger.warning(f"Binding {binding_id} not found or inactive")
                return
            if binding.channel_type != ChannelType.TELEGRAM:
                return

            message_data = payload.get("message")
            if not message_data:
                logger.debug(f"Telegram update without message: {payload.get('update_id')}")
                return

            # Extract basic fields
            chat = message_data.get("chat", {})
            chat_id = str(chat.get("id"))
            message_text = message_data.get("text") or message_data.get("caption") or ""
            message_id = message_data.get("message_id")
            from_user = message_data.get("from", {})

            if from_user.get("is_bot", False):
                return
            if not chat_id:
                return

            # Extract media info if present
            media_url: Optional[str] = None
            media_type: Optional[str] = None
            bot_token: Optional[str] = None

            has_photo = bool(message_data.get("photo"))
            has_video = bool(message_data.get("video"))
            has_audio = bool(message_data.get("audio") or message_data.get("voice"))
            has_document = bool(message_data.get("document"))
            has_sticker = bool(message_data.get("sticker"))

            if has_photo or has_video or has_audio or has_document or has_sticker:
                # Need bot token to resolve file URL
                try:
                    bot_token = await self.channel_binding_service.get_access_token(binding_id)
                except Exception:
                    pass

                if has_photo and bot_token:
                    photos = message_data["photo"]
                    file_id = photos[-1]["file_id"]  # highest resolution
                    media_url = await self._get_file_url(bot_token, file_id)
                    media_type = "image"
                elif has_video and bot_token:
                    file_id = message_data["video"]["file_id"]
                    media_url = await self._get_file_url(bot_token, file_id)
                    media_type = "video"
                elif has_audio and bot_token:
                    audio = message_data.get("audio") or message_data.get("voice", {})
                    file_id = audio.get("file_id")
                    if file_id:
                        media_url = await self._get_file_url(bot_token, file_id)
                    media_type = "audio"
                elif has_document and bot_token:
                    file_id = message_data["document"]["file_id"]
                    media_url = await self._get_file_url(bot_token, file_id)
                    media_type = "document"
                elif has_sticker:
                    media_type = "image"  # stickers treated as images

            # Skip if no text and no media at all
            if not message_text and not media_url and not has_sticker:
                logger.debug(f"Telegram message with no content (chat_id={chat_id}), skipping")
                return

            # Parse timestamp
            message_timestamp = utc_now()
            if "date" in message_data:
                try:
                    message_timestamp = datetime.fromtimestamp(
                        int(message_data["date"]), tz=timezone.utc
                    )
                except (ValueError, TypeError):
                    pass

            # Extract user info for conversation
            first_name = from_user.get("first_name", "")
            last_name = from_user.get("last_name", "")
            username = from_user.get("username")
            user_name = f"{first_name} {last_name}".strip() or None

            # Find or create conversation, and update user info if available
            conversation = await self._find_or_create_conversation(
                agent_id=binding.agent_id,
                external_user_id=chat_id,
                external_conversation_id=None,
                external_user_name=user_name,
                external_user_username=username,
            )

            # Build metadata for the message
            msg_metadata: dict[str, Any] = {}
            if media_url:
                msg_metadata["media_url"] = media_url
            if media_type:
                msg_metadata["media_type"] = media_type

            # Create user message
            user_message = Message(
                message_id=str(uuid.uuid4()),
                conversation_id=conversation.conversation_id,
                agent_id=binding.agent_id,
                role=MessageRole.USER,
                content=message_text,
                channel=MessageChannel.TELEGRAM,
                external_message_id=str(message_id) if message_id else None,
                external_user_id=chat_id,
                timestamp=message_timestamp,
                metadata=msg_metadata,
                media_url=media_url,
                media_type=media_type,
            )
            await self.dynamodb.create_message(user_message)

            # Skip AI for media-only messages (no text to process) OR if human is handling
            status_value = get_enum_value(conversation.status)
            if status_value in [ConversationStatus.NEEDS_HUMAN.value, ConversationStatus.HUMAN_ACTIVE.value]:
                return

            # Only call agent when there is text
            if not message_text:
                logger.debug(f"Media-only Telegram message saved for chat {chat_id} (no AI processing)")
                return

            try:
                agent_data = await self.dynamodb.get_agent(binding.agent_id)
                if not agent_data or "config" not in agent_data:
                    return

                from app.models.agent_config import AgentConfig
                from app.services.agent_service import create_agent_service
                from app.services.channel_sender import TelegramSender

                agent_config = AgentConfig.from_dict(agent_data["config"])
                history_messages = await self.dynamodb.list_messages(
                    conversation_id=conversation.conversation_id, limit=50, reverse=True
                )
                conversation_history = [
                    {"role": get_enum_value(m.role), "content": m.content}
                    for m in reversed(history_messages)
                ]
                if conversation_history and (
                    conversation_history[-1].get("role", "").lower() == "user"
                    and conversation_history[-1].get("content", "").strip() == message_text.strip()
                ):
                    conversation_history = conversation_history[:-1]

                telegram_sender = TelegramSender(self, self.dynamodb)
                agent_service = create_agent_service(agent_config, self.dynamodb, telegram_sender)
                result = await agent_service.process_message(
                    user_message=message_text,
                    conversation_id=conversation.conversation_id,
                    conversation_history=conversation_history,
                )
                if result.get("escalate"):
                    logger.info(f"Message escalated for conversation {conversation.conversation_id}")
            except Exception as e:
                logger.error(f"Error processing Telegram message through agent: {e}", exc_info=True)

        except Exception as e:
            logger.error(f"Error handling Telegram webhook event: {e}", exc_info=True)
            raise

    async def _find_or_create_conversation(
        self,
        agent_id: str,
        external_user_id: str,
        external_conversation_id: Optional[str],
        external_user_name: Optional[str] = None,
        external_user_username: Optional[str] = None,
    ) -> Conversation:
        """Find existing conversation or create new one. Updates user info if changed."""
        try:
            all_conversations = await self.dynamodb.list_conversations(agent_id=agent_id, limit=100)
            for conv in all_conversations:
                if (
                    get_enum_value(conv.channel) == MessageChannel.TELEGRAM.value
                    and conv.external_user_id == external_user_id
                ):
                    # Update user info if we now have it and it wasn't set before
                    updates: dict[str, Any] = {}
                    if external_user_name and not conv.external_user_name:
                        updates["external_user_name"] = external_user_name
                    if external_user_username and not conv.external_user_username:
                        updates["external_user_username"] = external_user_username
                    if updates:
                        await self.dynamodb.update_conversation(conv.conversation_id, **updates)
                        conv.external_user_name = external_user_name or conv.external_user_name
                        conv.external_user_username = external_user_username or conv.external_user_username
                    return conv
        except Exception as e:
            logger.warning(f"Error searching for existing Telegram conversation: {e}")

        conversation_id = str(uuid.uuid4())
        conversation = Conversation(
            conversation_id=conversation_id,
            agent_id=agent_id,
            channel=MessageChannel.TELEGRAM,
            external_user_id=external_user_id,
            external_conversation_id=external_conversation_id,
            external_user_name=external_user_name,
            external_user_username=external_user_username,
            status=ConversationStatus.AI_ACTIVE,
            marketing_status=MarketingStatus.NEW,
            created_at=utc_now(),
            updated_at=utc_now(),
        )
        await self.dynamodb.create_conversation(conversation)
        return conversation

    async def send_message(
        self,
        binding_id: str,
        chat_id: str,
        message_text: str,
        media_url: Optional[str] = None,
        media_type: Optional[str] = None,
    ) -> dict[str, Any]:
        """Send text and/or media message via Telegram Bot API."""
        bot_token = await self.channel_binding_service.get_access_token(binding_id)

        async with httpx.AsyncClient(timeout=30.0) as client:
            # Send media first if present
            if media_url and media_type:
                if media_type == "image":
                    endpoint = f"{self.TELEGRAM_API_BASE_URL}{bot_token}/sendPhoto"
                    payload: dict[str, Any] = {"chat_id": chat_id, "photo": media_url}
                    if message_text:
                        payload["caption"] = message_text
                elif media_type == "video":
                    endpoint = f"{self.TELEGRAM_API_BASE_URL}{bot_token}/sendVideo"
                    payload = {"chat_id": chat_id, "video": media_url}
                    if message_text:
                        payload["caption"] = message_text
                elif media_type == "audio":
                    endpoint = f"{self.TELEGRAM_API_BASE_URL}{bot_token}/sendAudio"
                    payload = {"chat_id": chat_id, "audio": media_url}
                    if message_text:
                        payload["caption"] = message_text
                else:
                    endpoint = f"{self.TELEGRAM_API_BASE_URL}{bot_token}/sendDocument"
                    payload = {"chat_id": chat_id, "document": media_url}
                    if message_text:
                        payload["caption"] = message_text

                resp = await client.post(endpoint, json=payload)
                if resp.status_code != 200 or not resp.json().get("ok"):
                    logger.error(f"Telegram media send failed: {resp.text}")
                    # Fall through to send text separately if caption failed
                    if message_text:
                        text_resp = await client.post(
                            f"{self.TELEGRAM_API_BASE_URL}{bot_token}/sendMessage",
                            json={"chat_id": chat_id, "text": message_text},
                        )
                        return text_resp.json()
                else:
                    logger.info(f"Sent Telegram {media_type} to chat {chat_id}")
                    return resp.json()

            # Text-only message
            if message_text:
                resp = await client.post(
                    f"{self.TELEGRAM_API_BASE_URL}{bot_token}/sendMessage",
                    json={"chat_id": chat_id, "text": message_text},
                )
                if resp.status_code != 200 or not resp.json().get("ok"):
                    logger.error(f"Telegram send failed: {resp.text}")
                    resp.raise_for_status()
                logger.info(f"Sent Telegram message to chat {chat_id}")
                return resp.json()

        return {}

    async def verify_bot_token(self, bot_token: str) -> bool:
        """Verify bot token by calling getMe API."""
        url = f"{self.TELEGRAM_API_BASE_URL}{bot_token}/getMe"
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(url)
                result = response.json()
                if result.get("ok") and result.get("result"):
                    bot_info = result["result"]
                    logger.info(f"Telegram bot verified: @{bot_info.get('username')} (id: {bot_info.get('id')})")
                    return True
                return False
        except Exception as e:
            logger.error(f"Error verifying Telegram bot token: {e}", exc_info=True)
            return False

    async def send_notification_message(
        self, bot_token: str, chat_id: str, message_text: str
    ) -> dict[str, Any]:
        """Send notification message directly (without ChannelBinding)."""
        url = f"{self.TELEGRAM_API_BASE_URL}{bot_token}/sendMessage"
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(url, json={"chat_id": chat_id, "text": message_text})
            response.raise_for_status()
            result = response.json()
            if not result.get("ok"):
                raise ValueError(f"Telegram API error: {result.get('description')}")
            return result

    async def set_webhook(
        self, binding_id: str, webhook_url: str, secret_token: Optional[str] = None
    ) -> bool:
        """Set webhook URL for Telegram bot."""
        bot_token = await self.channel_binding_service.get_access_token(binding_id)
        url = f"{self.TELEGRAM_API_BASE_URL}{bot_token}/setWebhook"
        payload: dict[str, Any] = {"url": webhook_url}
        if secret_token:
            payload["secret_token"] = secret_token
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(url, json=payload)
                result = response.json()
                if result.get("ok"):
                    logger.info(f"Telegram webhook set: {webhook_url}")
                    return True
                logger.error(f"Telegram setWebhook error: {result.get('description')}")
                return False
        except Exception as e:
            logger.error(f"Error setting Telegram webhook: {e}", exc_info=True)
            return False

    async def get_message_sender_from_api(
        self, account_id: str, message_id: str
    ) -> Optional[str]:
        """Placeholder for Instagram compatibility (not used in Telegram)."""
        return None
