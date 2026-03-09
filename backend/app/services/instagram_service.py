"""Instagram service for handling Instagram Direct Messaging."""

import hashlib
import hmac
import json
import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

import httpx

from app.config import Settings, get_settings
from app.utils.datetime_utils import parse_utc_datetime, utc_now
from app.models.channel_binding import ChannelType
from app.models.conversation import Conversation, ConversationStatus, MarketingStatus
from app.models.instagram_user_profile import InstagramUserProfile
from app.models.message import Message, MessageChannel, MessageRole
from app.services.channel_binding_service import ChannelBindingService
from app.storage.dynamodb import DynamoDBClient

logger = logging.getLogger(__name__)


class InstagramService:
    """Service for Instagram Direct Messaging integration."""

    GRAPH_API_BASE_URL = "https://graph.instagram.com/v21.0"

    def __init__(
        self,
        channel_binding_service: ChannelBindingService,
        dynamodb: DynamoDBClient,
        settings: Settings,
    ):
        """Initialize Instagram service."""
        self.channel_binding_service = channel_binding_service
        self.dynamodb = dynamodb
        self.settings = settings

    def verify_webhook(self, mode: str, token: str, challenge: str) -> Optional[str]:
        """Verify Instagram webhook."""
        if mode == "subscribe" and token == self.settings.instagram_webhook_verify_token:
            logger.info("Instagram webhook verified successfully")
            return challenge
        logger.warning(f"Instagram webhook verification failed: mode={mode}, token mismatch")
        return None

    def verify_webhook_signature(self, payload: bytes, signature: str) -> bool:
        """Verify webhook signature using app secret."""
        if not self.settings.instagram_app_secret:
            logger.warning("Instagram app secret not configured, skipping signature verification")
            return True

        expected_signature = hmac.new(
            self.settings.instagram_app_secret.encode("utf-8"),
            payload,
            hashlib.sha256,
        ).hexdigest()

        # Instagram sends signature as "sha256=<hash>"
        if signature.startswith("sha256="):
            signature = signature[7:]

        return hmac.compare_digest(expected_signature, signature)

    async def handle_webhook_event(self, payload: dict[str, Any]) -> None:
        """Handle incoming webhook event from Instagram."""
        try:
            # Verify webhook signature if provided
            # Note: Signature verification should be done in the endpoint handler
            # This method assumes signature is already verified

            # Parse Instagram webhook payload
            if payload.get("object") != "instagram":
                logger.warning(f"Unknown webhook object type: {payload.get('object')}")
                return

            entries = payload.get("entry", [])
            for entry in entries:
                messaging = entry.get("messaging", [])
                for event in messaging:
                    # Check event type - only process message events, skip others (message_edit, etc.)
                    event_type = self._get_event_type(event)
                    
                    # Log detailed information about message_edit events
                    if event_type == "message_edit":
                        edit_data = event.get("message_edit", {})
                        num_edit = edit_data.get("num_edit", -1)
                        mid = edit_data.get("mid", "unknown")
                        entry_id = entry.get("id")  # This is the Instagram Business Account ID
                        
                        logger.warning(
                            f"Received message_edit event (num_edit={num_edit}, mid={mid[:50]}...)"
                        )
                        logger.warning(
                            f"⚠️  Instagram sent message_edit event without sender/recipient IDs. "
                            f"This is a known Instagram API behavior - they send message_edit with num_edit=0 for new messages. "
                            f"Instagram may send a separate 'message' event later with sender/recipient IDs."
                        )
                        
                        # Try to get message info via Graph API if we have entry_id (account ID)
                        if entry_id and num_edit == 0:
                            logger.info(
                                f"Attempting to fetch message info via Graph API for message_id={mid[:50]}..."
                            )
                            # Note: This would require Graph API call, but we don't have sender_id yet
                            # We'll wait for the 'message' event instead
                        
                        logger.info(
                            f"Skipping message_edit event (waiting for 'message' event with sender/recipient IDs)"
                        )
                    elif event_type == "message":
                        await self._process_messaging_event(event)
                    else:
                        logger.info(
                            f"Skipping event type '{event_type}': {event.get(event_type, {}).get('mid', 'unknown')}"
                        )

        except Exception as e:
            logger.error(f"Error handling Instagram webhook event: {e}", exc_info=True)
            raise

    def _get_event_type(self, event: dict[str, Any]) -> str:
        """Determine the type of Instagram webhook event."""
        # Instagram webhook events can have different types:
        # - message: regular message
        # - message_edit: message was edited (NOTE: Instagram may send message_edit with num_edit=0 for new messages!)
        # - message_reaction: reaction to message
        # - message_unsend: message was unsent
        # - etc.
        
        # IMPORTANT: Check for sender/recipient FIRST, as message_edit events may not have them
        # but if they do, we should treat it as a message event
        if "sender" in event and "recipient" in event:
            # If sender and recipient exist, treat as message (even if message_edit is also present)
            return "message"
        elif "message" in event:
            return "message"
        elif "message_edit" in event:
            # Instagram sometimes sends message_edit with num_edit=0 for new messages
            # But without sender/recipient, we can't process it
            return "message_edit"
        elif "message_reaction" in event:
            return "message_reaction"
        elif "message_unsend" in event:
            return "message_unsend"
        else:
            return "unknown"

    async def _process_messaging_event(self, event: dict[str, Any]) -> None:
        """Process a single messaging event."""
        sender = event.get("sender", {})
        recipient = event.get("recipient", {})
        message_data = event.get("message", {})

        sender_id = sender.get("id")
        recipient_id = recipient.get("id")  # This is the Instagram Business Account ID
        message_text = message_data.get("text", "")
        message_id = message_data.get("mid")
        is_echo = message_data.get("is_echo", False)
        is_self = message_data.get("is_self", False)

        # CRITICAL: Filter out echo messages (messages sent by our agent)
        # Instagram sends back webhook events for messages we send, marked with is_echo=True
        # If we process these, it creates an infinite loop
        if is_echo:
            logger.info(
                f"Ignoring echo message (sent by agent): message_id={message_id}, sender_id={sender_id}"
            )
            return

        # Extract media from attachments
        media_url: str | None = None
        media_type: str | None = None
        attachments = message_data.get("attachments", [])
        if attachments:
            attachment = attachments[0]
            att_type = attachment.get("type", "")
            payload_data = attachment.get("payload", {})
            att_url = payload_data.get("url")
            if att_url:
                media_url = att_url
                media_type = {
                    "image": "image",
                    "video": "video",
                    "audio": "audio",
                    "file": "document",
                }.get(att_type, "image")

        if not sender_id or not recipient_id or (not message_text and not media_url):
            logger.info(f"Ignoring incomplete Instagram messaging event (no text or media)")
            return

        # Log self-messaging events for debugging (but process them normally)
        if is_self:
            logger.info(
                f"Self-messaging event detected: sender_id={sender_id}, recipient_id={recipient_id}"
            )

        # Find binding by Instagram account ID
        binding = await self.channel_binding_service.get_binding_by_account_id(
            channel_type=ChannelType.INSTAGRAM.value, account_id=recipient_id
        )

        if not binding:
            logger.warning(
                f"Received message from unbound Instagram account: {recipient_id}. Ignoring."
            )
            return

        if not binding.is_active:
            logger.warning(
                f"Received message from inactive binding: {binding.binding_id}. Ignoring."
            )
            return

        # Find or create conversation
        # Use external_user_id to find existing conversation
        conversation = await self._find_or_create_conversation(
            agent_id=binding.agent_id,
            external_user_id=sender_id,
            external_conversation_id=None,  # Instagram doesn't provide thread ID in this format
        )

        # Проверяем, есть ли timestamp в webhook событии
        # Instagram может предоставлять время в разных полях:
        # - event.get("timestamp") - время события (в миллисекундах Unix epoch)
        # - entry.get("time") - время входа (если доступно)
        webhook_timestamp = None
        if "timestamp" in event:
            try:
                # Instagram timestamp обычно в миллисекундах Unix epoch
                timestamp_ms = event["timestamp"]
                if isinstance(timestamp_ms, (int, float)):
                    # Convert Unix timestamp (milliseconds) to UTC datetime
                    webhook_timestamp = datetime.fromtimestamp(int(timestamp_ms) / 1000, tz=timezone.utc)
                    logger.info(f"Using timestamp from Instagram webhook: {webhook_timestamp} (from {timestamp_ms} ms)")
                elif isinstance(timestamp_ms, str):
                    # Попытка парсинга строки
                    webhook_timestamp = datetime.fromtimestamp(int(timestamp_ms) / 1000, tz=timezone.utc)
                    logger.info(f"Using timestamp from Instagram webhook (parsed from string): {webhook_timestamp}")
            except (ValueError, TypeError, KeyError) as e:
                logger.warning(f"Failed to parse Instagram webhook timestamp: {e}, using current time")
                webhook_timestamp = None

        # Используем timestamp из webhook, если доступен, иначе текущее время
        message_timestamp = webhook_timestamp if webhook_timestamp else utc_now()

        msg_metadata: dict = {}
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
            channel=MessageChannel.INSTAGRAM,
            external_message_id=message_id,
            external_user_id=sender_id,
            timestamp=message_timestamp,
            metadata=msg_metadata,
            media_url=media_url,
            media_type=media_type,
        )

        await self.dynamodb.create_message(user_message)

        # Check if conversation is handled by human - don't process with agent
        from app.utils.enum_helpers import get_enum_value
        status_value = get_enum_value(conversation.status)
        if status_value in [
            ConversationStatus.NEEDS_HUMAN.value,
            ConversationStatus.HUMAN_ACTIVE.value,
        ]:
            logger.info(
                f"Conversation {conversation.conversation_id} is handled by human, skipping agent processing"
            )
            return

        # Process message through agent
        try:
            # Get agent configuration
            agent_data = await self.dynamodb.get_agent(binding.agent_id)
            if not agent_data or "config" not in agent_data:
                logger.error(f"Agent {binding.agent_id} not found or invalid configuration")
                return

            from app.models.agent_config import AgentConfig

            agent_config = AgentConfig.from_dict(agent_data["config"])

            # Get conversation history
            history_messages = await self.dynamodb.list_messages(
                conversation_id=conversation.conversation_id,
                limit=50,
                reverse=True,
            )
            conversation_history = [
                {
                    "role": get_enum_value(msg.role),
                    "content": msg.content,
                }
                for msg in reversed(history_messages)
            ]

            # Exclude current user message from history
            if conversation_history:
                last_msg = conversation_history[-1]
                if (
                    last_msg.get("role", "").lower() == "user"
                    and last_msg.get("content", "").strip() == message_text.strip()
                ):
                    conversation_history = conversation_history[:-1]

            # Create channel sender for Instagram
            from app.services.channel_sender import InstagramSender
            from app.services.agent_service import create_agent_service

            instagram_sender = InstagramSender(self, self.dynamodb)

            # Create agent service with channel sender
            agent_service = create_agent_service(agent_config, self.dynamodb, instagram_sender)

            result = await agent_service.process_message(
                user_message=message_text,
                conversation_id=conversation.conversation_id,
                conversation_history=conversation_history,
            )

            # Handle escalation
            if result.get("escalate"):
                logger.info(
                    f"Message escalated for conversation {conversation.conversation_id}"
                )
                return

            # Agent response is sent via ChannelSender in AgentService.process_message
            # No need to send manually here

        except Exception as e:
            logger.error(
                f"Error processing message through agent: {e}", exc_info=True
            )

    async def _find_or_create_conversation(
        self,
        agent_id: str,
        external_user_id: str,
        external_conversation_id: Optional[str],
    ) -> Conversation:
        """Find existing conversation or create new one."""
        # Try to find existing conversation by external_user_id and agent_id
        # This prevents creating multiple conversations for the same user
        try:
            all_conversations = await self.dynamodb.list_conversations(
                agent_id=agent_id,
                limit=100,
            )
            
            # Find conversation with matching external_user_id
            for conv in all_conversations:
                # Handle both enum and string channel (from DynamoDB)
                conv_channel = get_enum_value(conv.channel)
                if (
                    conv_channel == MessageChannel.INSTAGRAM.value
                    and conv.external_user_id == external_user_id
                ):
                    logger.info(
                        f"Found existing conversation {conv.conversation_id} for user {external_user_id}"
                    )
                    return conv
        except Exception as e:
            logger.warning(
                f"Error searching for existing conversation: {e}. Creating new one."
            )

        # No existing conversation found, create new one
        conversation_id = str(uuid.uuid4())
        conversation = Conversation(
            conversation_id=conversation_id,
            agent_id=agent_id,
            channel=MessageChannel.INSTAGRAM,
            external_user_id=external_user_id,
            external_conversation_id=external_conversation_id,
            status=ConversationStatus.AI_ACTIVE,
            marketing_status=MarketingStatus.NEW,
            created_at=utc_now(),
            updated_at=utc_now(),
        )

        await self.dynamodb.create_conversation(conversation)
        logger.info(
            f"Created new conversation {conversation_id} for user {external_user_id}"
        )
        return conversation

    async def send_message(
        self,
        binding_id: str,
        recipient_id: str,
        message_text: str,
        media_url: str | None = None,
        media_type: str | None = None,
    ) -> dict[str, Any]:
        """Send text and/or media message via Instagram Graph API."""
        access_token = await self.channel_binding_service.get_access_token(binding_id)
        binding = await self.channel_binding_service.get_binding(binding_id)
        if not binding:
            raise ValueError(f"Binding {binding_id} not found")

        url = f"{self.GRAPH_API_BASE_URL}/{binding.channel_account_id}/messages"
        headers = {"Authorization": f"Bearer {access_token}"}

        async with httpx.AsyncClient(timeout=30.0) as client:
            # Send media attachment if provided
            if media_url and media_type:
                ig_type = {
                    "image": "image",
                    "video": "video",
                    "audio": "audio",
                    "document": "file",
                }.get(media_type, "image")

                media_payload = {
                    "recipient": {"id": recipient_id},
                    "message": {
                        "attachment": {
                            "type": ig_type,
                            "payload": {"url": media_url, "is_reusable": True},
                        }
                    },
                }
                resp = await client.post(url, json=media_payload, headers=headers)
                if resp.status_code != 200:
                    logger.error(f"Instagram media send failed: {resp.status_code} {resp.text}")
                    # Fall through to text if media fails
                else:
                    logger.info(f"Sent Instagram {media_type} to {recipient_id}")
                    # Send text separately if both provided
                    if message_text:
                        await client.post(
                            url,
                            json={"recipient": {"id": recipient_id}, "message": {"text": message_text}},
                            headers=headers,
                        )
                    return resp.json()

            # Text-only message
            if message_text:
                payload = {"recipient": {"id": recipient_id}, "message": {"text": message_text}}
                response = await client.post(url, json=payload, headers=headers)
                if response.status_code != 200:
                    logger.error(f"Instagram send failed: {response.status_code} {response.text}")
                    response.raise_for_status()
                logger.info(f"Sent Instagram message to {recipient_id}")
                return response.json()

        return {}

    async def get_user_profile(
        self, igsid: str, access_token: str
    ) -> Optional[InstagramUserProfile]:
        """Get Instagram user profile information from Instagram Graph API.
        
        Args:
            igsid: Instagram-scoped ID (IGSID) of the user
            access_token: Instagram user access token
            
        Returns:
            InstagramUserProfile if successful, None otherwise
        """
        url = f"{self.GRAPH_API_BASE_URL}/{igsid}"
        params = {
            "fields": "name,username,profile_pic",
            "access_token": access_token,
        }

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(url, params=params)

                if response.status_code == 200:
                    try:
                        data = response.json()
                    except Exception as e:
                        logger.error(f"Failed to parse JSON response for Instagram profile {igsid}: {e}")
                        return None
                    
                    # Create profile object with proper TTL
                    updated_at = utc_now()
                    profile = InstagramUserProfile(
                        external_user_id=igsid,
                        name=data.get("name"),
                        username=data.get("username"),
                        profile_pic=data.get("profile_pic"),
                        updated_at=updated_at,
                        ttl=int((updated_at + timedelta(days=5)).timestamp()),
                    )
                    logger.info(f"Successfully fetched Instagram profile for user {igsid}")
                    return profile
                elif response.status_code == 400:
                    try:
                        error_data = response.json()
                        error_message = error_data.get("error", {}).get("message", "")
                        error_code = error_data.get("error", {}).get("code", 0)
                    except Exception:
                        error_message = "Bad request"
                        error_code = 0
                    
                    # Handle specific error cases
                    if "User consent is required" in error_message or error_code == 200:
                        logger.warning(
                            f"User consent required for Instagram profile {igsid}: {error_message}"
                        )
                    elif "user blocked" in error_message.lower():
                        logger.warning(f"User {igsid} has blocked this account")
                    else:
                        logger.warning(
                            f"Failed to fetch Instagram profile for {igsid}: {error_message}"
                        )
                    return None
                elif response.status_code == 429:
                    # Rate limit
                    logger.warning(f"Rate limit exceeded when fetching Instagram profile for {igsid}")
                    return None
                else:
                    error_text = response.text
                    logger.error(
                        f"Failed to fetch Instagram profile for {igsid}: {response.status_code} - {error_text}"
                    )
                    return None
        except httpx.TimeoutException:
            logger.error(f"Timeout when fetching Instagram profile for {igsid}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error fetching Instagram profile for {igsid}: {e}")
            return None

    async def refresh_user_profile(
        self, external_user_id: str, binding_id: str
    ) -> Optional[InstagramUserProfile]:
        """Refresh Instagram user profile and save to DynamoDB.
        
        Args:
            external_user_id: Instagram-scoped ID (IGSID) of the user
            binding_id: Channel binding ID to get access token
            
        Returns:
            InstagramUserProfile if successful, None otherwise
        """
        # Get access token
        access_token = await self.channel_binding_service.get_access_token(binding_id)

        # Fetch profile from Instagram API
        profile = await self.get_user_profile(external_user_id, access_token)
        
        if profile:
            # Profile already has correct TTL from get_user_profile, just save it
            await self.dynamodb.create_or_update_instagram_profile(profile)
            logger.info(f"Refreshed and saved Instagram profile for user {external_user_id}")
            return profile
        else:
            logger.warning(f"Failed to refresh Instagram profile for user {external_user_id}")
            return None

    async def subscribe_to_webhook(
        self, account_id: str, access_token: str
    ) -> bool:
        """Subscribe to webhook for Instagram account (optional, for automatic setup)."""
        # This is optional - webhook can be set up manually in Facebook Developer Console
        # If implementing automatic subscription, use Instagram Graph API subscriptions endpoint
        logger.info(
            f"Webhook subscription for account {account_id} should be configured manually in Facebook Developer Console"
        )
        return True

    async def get_message_sender_from_api(
        self, account_id: str, message_id: str
    ) -> Optional[str]:
        """
        Попытка получить sender_id из сообщения через Graph API.
        
        Использует conversations endpoint для поиска сообщения по message_id.
        """
        try:
            # Получаем access token из binding по account_id
            binding = await self.channel_binding_service.get_binding_by_account_id(
                channel_type=ChannelType.INSTAGRAM.value, account_id=account_id
            )
            
            if not binding:
                logger.warning(f"Binding not found for account_id: {account_id}")
                return None
            
            if not binding.is_active:
                logger.warning(f"Binding is not active for account_id: {account_id}")
                return None
            
            access_token = await self.channel_binding_service.get_access_token(binding.binding_id)
            
            # Пробуем получить conversations
            # Используем реальный Instagram Account ID из binding, а не Page ID
            instagram_account_id = binding.channel_account_id
            
            # Пробуем несколько вариантов endpoints
            endpoints_to_try = [
                f"{self.GRAPH_API_BASE_URL}/{instagram_account_id}/conversations?fields=id,participants,messages",
                f"{self.GRAPH_API_BASE_URL}/{instagram_account_id}/conversations",
                f"{self.GRAPH_API_BASE_URL}/{account_id}/conversations?fields=id,participants,messages",
                f"{self.GRAPH_API_BASE_URL}/{account_id}/conversations",
            ]
            
            async with httpx.AsyncClient(timeout=30.0) as client:
                for endpoint in endpoints_to_try:
                    try:
                        response = await client.get(
                            endpoint,
                            headers={"Authorization": f"Bearer {access_token}"},
                        )
                        
                        if response.status_code == 200:
                            data = response.json()
                            conversations = data.get("data", [])
                            
                            logger.info(f"Found {len(conversations)} conversations via {endpoint}")
                            
                            # Ищем сообщение в conversations
                            for conversation in conversations:
                                conv_id = conversation.get("id")
                                if not conv_id:
                                    continue
                                
                                # Получаем messages из conversation
                                messages_url = f"{self.GRAPH_API_BASE_URL}/{conv_id}/messages?fields=id,from,to,message"
                                messages_response = await client.get(
                                    messages_url,
                                    headers={"Authorization": f"Bearer {access_token}"},
                                )
                                
                                if messages_response.status_code == 200:
                                    messages_data = messages_response.json()
                                    messages = messages_data.get("data", [])
                                    
                                    # Ищем сообщение с нужным message_id
                                    for msg in messages:
                                        if msg.get("id") == message_id:
                                            sender_info = msg.get("from", {})
                                            sender_id = sender_info.get("id")
                                            if sender_id:
                                                logger.info(f"Found sender_id {sender_id} for message_id {message_id[:50]}...")
                                                return sender_id
                                    
                                    logger.debug(f"Message {message_id[:50]}... not found in conversation {conv_id}")
                        else:
                            logger.debug(f"Endpoint {endpoint} returned status {response.status_code}")
                    except Exception as e:
                        logger.debug(f"Error trying endpoint {endpoint}: {e}")
                        continue
            
            logger.warning(f"Could not find sender_id for message_id {message_id[:50]}... via Graph API")
            return None
            
        except Exception as e:
            logger.error(f"Error getting message sender from API: {e}", exc_info=True)
            return None

