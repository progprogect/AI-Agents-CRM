"""Chat API endpoints."""

import logging
import uuid
from typing import Optional

logger = logging.getLogger(__name__)

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from pydantic import BaseModel, Field, model_validator

from app.api.exceptions import AgentNotFoundError, ConversationNotFoundError
from app.api.schemas import AgentIDValidator
from app.api.v1.media import MediaUploadResponse, store_chat_media_bytes
from app.dependencies import CommonDependencies
from app.models.agent_config import AgentConfig
from app.models.conversation import Conversation, ConversationStatus, MarketingStatus
from app.models.message import Message, MessageChannel, MessageRole
from app.services.agent_reply_coordinator import cancel_timer_trigger, notify_user_message_saved
from app.services.agent_service import create_agent_service
from app.services.channel_sender import get_channel_sender
from app.services.conversation_service import build_conversation_history_for_agent
from app.services.channel_binding_service import ChannelBindingService
from app.services.instagram_service import InstagramService
from app.services.telegram_service import TelegramService
from app.config import get_settings
from app.storage.redis import get_redis_client
from app.storage.resolver import get_secrets_manager
from app.utils.enum_helpers import get_enum_value
from app.utils.datetime_utils import utc_now, to_utc_iso_string

router = APIRouter()


class CreateConversationRequest(BaseModel, AgentIDValidator):
    """Request to create a conversation."""

    agent_id: str = Field(..., description="Agent ID")


class CreateConversationResponse(BaseModel):
    """Response for created conversation."""

    conversation_id: str
    agent_id: str
    status: str


class CloseConversationResponse(BaseModel):
    """Response after closing a web chat conversation (idempotent)."""

    conversation_id: str
    status: str


class SendMessageRequest(BaseModel):
    """Request to send a message (text and/or image from web chat upload)."""

    content: str = Field(default="", description="Caption / text", max_length=10000)
    media_url: Optional[str] = Field(None, description="Public URL from POST .../media/upload")
    media_type: Optional[str] = Field(None, description="image | video | … (web chat: image only)")
    media_filename: Optional[str] = Field(None, description="Original filename")

    @model_validator(mode="after")
    def validate_has_body_or_media(self) -> "SendMessageRequest":
        text = (self.content or "").strip()
        has_media = bool(self.media_url and self.media_type)
        if not text and not has_media:
            raise ValueError("Message must include text or an image attachment")
        if bool(self.media_url) != bool(self.media_type):
            raise ValueError("media_url and media_type must be sent together")
        if has_media and self.media_type != "image":
            raise ValueError("Web chat supports image attachments only")
        if self.media_url and not self.media_url.startswith(("https://", "http://")):
            raise ValueError("media_url must be an http(s) URL")
        return self


class SendMessageResponse(BaseModel):
    """Response for sent message."""

    message_id: str
    role: str
    content: str
    timestamp: str


@router.post(
    "/conversations",
    response_model=CreateConversationResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_conversation(
    request: CreateConversationRequest,
    deps: CommonDependencies = Depends(),
):
    """Create a new conversation."""
    # Verify agent exists
    agent_data = await deps.dynamodb.get_agent(request.agent_id)
    if not agent_data:
        raise AgentNotFoundError(request.agent_id)

    conversation_id = str(uuid.uuid4())
    conversation = Conversation(
        conversation_id=conversation_id,
        agent_id=request.agent_id,
        channel=MessageChannel.WEB_CHAT,  # Web chat is default channel
        status=ConversationStatus.AI_ACTIVE,
        marketing_status=MarketingStatus.NEW,
        created_at=utc_now(),
        updated_at=utc_now(),
    )

    await deps.dynamodb.create_conversation(conversation)

    # Handle both enum and string status (from DynamoDB)
    status_value = get_enum_value(conversation.status)
    return CreateConversationResponse(
        conversation_id=conversation_id,
        agent_id=request.agent_id,
        status=status_value,
    )


@router.get("/conversations/{conversation_id}", response_model=Conversation)
async def get_conversation(
    conversation_id: str,
    deps: CommonDependencies = Depends(),
):
    """Get conversation by ID."""

    conversation = await deps.dynamodb.get_conversation(conversation_id)
    if not conversation:
        raise ConversationNotFoundError(conversation_id)
    return conversation


@router.post(
    "/conversations/{conversation_id}/close",
    response_model=CloseConversationResponse,
    status_code=status.HTTP_200_OK,
)
async def close_conversation(
    conversation_id: str,
    deps: CommonDependencies = Depends(),
):
    """Close a web chat conversation (public). Idempotent if already closed."""
    conversation = await deps.dynamodb.get_conversation(conversation_id)
    if not conversation:
        raise ConversationNotFoundError(conversation_id)

    channel_value = get_enum_value(conversation.channel)
    if channel_value != MessageChannel.WEB_CHAT.value:
        raise HTTPException(
            status_code=400,
            detail="Only web_chat conversations can be closed via this endpoint",
        )

    status_value = get_enum_value(conversation.status)
    if status_value == ConversationStatus.CLOSED.value:
        return CloseConversationResponse(
            conversation_id=conversation_id,
            status=ConversationStatus.CLOSED.value,
        )

    await deps.dynamodb.update_conversation(
        conversation_id=conversation_id,
        status=ConversationStatus.CLOSED,
        closed_at=utc_now(),
    )
    return CloseConversationResponse(
        conversation_id=conversation_id,
        status=ConversationStatus.CLOSED.value,
    )


@router.post(
    "/conversations/{conversation_id}/voice",
    status_code=status.HTTP_200_OK,
)
async def transcribe_voice_message(
    conversation_id: str,
    file: UploadFile = File(...),
    deps: CommonDependencies = Depends(),
):
    """Transcribe a voice recording captured in the web chat.

    Accepts a raw audio blob (webm, ogg, mp4 …) from MediaRecorder,
    sends it to the STT service, and returns the transcript text.
    The client then places the transcript in the message input and sends
    it as a regular text message — same pipeline as Telegram voice notes.
    """
    conversation = await deps.dynamodb.get_conversation(conversation_id)
    if not conversation:
        raise ConversationNotFoundError(conversation_id)

    status_value = get_enum_value(conversation.status)
    if status_value == ConversationStatus.CLOSED.value:
        raise HTTPException(status_code=400, detail="Conversation is closed")

    audio_bytes = await file.read()
    filename = file.filename or "voice.webm"

    try:
        from app.services.stt_service import STTError, transcribe_bytes
        transcript = await transcribe_bytes(audio_bytes, filename, language="ru")
    except Exception as exc:
        logger.warning("Voice transcription failed for conversation %s: %s", conversation_id, exc)
        raise HTTPException(status_code=500, detail="Transcription failed. Please try again.")

    return {"transcript": transcript}


@router.post(
    "/conversations/{conversation_id}/media/upload",
    response_model=MediaUploadResponse,
    status_code=status.HTTP_201_CREATED,
)
async def upload_web_chat_media(
    conversation_id: str,
    file: UploadFile = File(...),
    deps: CommonDependencies = Depends(),
):
    """Upload chat media for a web_chat conversation (no admin token; same CDN as /media/upload)."""
    conversation = await deps.dynamodb.get_conversation(conversation_id)
    if not conversation:
        raise ConversationNotFoundError(conversation_id)

    channel_value = get_enum_value(conversation.channel)
    if channel_value != MessageChannel.WEB_CHAT.value:
        raise HTTPException(
            status_code=400,
            detail="Media upload is only allowed for web chat conversations",
        )

    status_value = get_enum_value(conversation.status)
    if status_value == ConversationStatus.CLOSED.value:
        raise HTTPException(status_code=400, detail="Conversation is closed")

    file_bytes = await file.read()
    filename = file.filename or "upload"
    return store_chat_media_bytes(file_bytes, filename, file.content_type)


@router.post(
    "/conversations/{conversation_id}/messages",
    response_model=SendMessageResponse,
    status_code=status.HTTP_201_CREATED,
)
async def send_message(
    conversation_id: str,
    request: SendMessageRequest,
    deps: CommonDependencies = Depends(),
):
    """Send a message in a conversation."""

    # Verify conversation exists
    conversation = await deps.dynamodb.get_conversation(conversation_id)
    if not conversation:
        raise ConversationNotFoundError(conversation_id)

    # Check if conversation is active
    # Handle both enum and string status (from DynamoDB)
    status_value = get_enum_value(conversation.status)
    if status_value == ConversationStatus.CLOSED.value:
        raise HTTPException(status_code=400, detail="Conversation is closed")

    content_stripped = (request.content or "").strip()

    msg_metadata: dict = {}
    if request.media_url:
        msg_metadata["media_url"] = request.media_url
        msg_metadata["media_type"] = request.media_type
    if request.media_filename:
        msg_metadata["media_filename"] = request.media_filename

    agent_user_message = content_stripped
    # Pass the image URL natively to the LLM (multimodal) rather than
    # converting it to a text description first.
    user_media_url_for_agent: Optional[str] = (
        request.media_url if request.media_type == "image" else None
    )
    logger.info(
        "[vision] send_message: media_type=%r media_url=%r → user_media_url_for_agent=%r",
        request.media_type,
        request.media_url,
        user_media_url_for_agent,
        extra={"conversation_id": conversation_id},
    )

    # Create user message
    message_id = str(uuid.uuid4())
    user_message = Message(
        message_id=message_id,
        conversation_id=conversation_id,
        agent_id=conversation.agent_id,
        role=MessageRole.USER,
        content=content_stripped,
        channel=conversation.channel,
        external_user_id=conversation.external_user_id,
        timestamp=utc_now(),
        metadata=msg_metadata,
        media_url=request.media_url,
        media_type=request.media_type,
    )

    await deps.dynamodb.create_message(user_message)

    # Check if conversation is handled by human - don't process with agent
    if status_value in [
        ConversationStatus.NEEDS_HUMAN.value,
        ConversationStatus.HUMAN_ACTIVE.value,
    ]:
        # Return user message without agent processing
        role_value = get_enum_value(user_message.role)
        return SendMessageResponse(
            message_id=message_id,
            role=role_value,
            content=user_message.content,
            timestamp=to_utc_iso_string(user_message.timestamp),
        )

    # Get agent configuration
    agent_data = await deps.dynamodb.get_agent(conversation.agent_id)
    if not agent_data or "config" not in agent_data:
        raise HTTPException(status_code=404, detail="Agent not found or invalid configuration")

    agent_config = AgentConfig.from_dict(agent_data["config"])

    conversation_history = await build_conversation_history_for_agent(
        deps.dynamodb,
        conversation_id,
        content_stripped,
        agent_context_reset_at=conversation.agent_context_reset_at,
    )

    # Get channel sender for the conversation's channel
    # Handle both enum and string channel (from DynamoDB)
    conversation_channel = get_enum_value(conversation.channel)
    
    instagram_service = None
    telegram_service = None
    if conversation_channel != MessageChannel.WEB_CHAT.value:
        # Create channel-specific service if needed
        settings = get_settings()
        secrets_manager = get_secrets_manager()
        binding_service = ChannelBindingService(deps.dynamodb, secrets_manager)
        
        if conversation_channel == MessageChannel.INSTAGRAM.value:
            instagram_service = InstagramService(binding_service, deps.dynamodb, settings)
        elif conversation_channel == MessageChannel.TELEGRAM.value:
            telegram_service = TelegramService(binding_service, deps.dynamodb, settings)
    
    # Convert string back to enum for get_channel_sender
    channel_enum = MessageChannel(conversation_channel) if isinstance(conversation_channel, str) else conversation.channel
    channel_sender = get_channel_sender(
        channel_enum, deps.dynamodb, instagram_service, telegram_service
    )

    agent_service = create_agent_service(agent_config, deps.dynamodb, channel_sender)

    # Cancel any pending inactivity timer — user is actively responding.
    await cancel_timer_trigger(conversation_id)

    settings = get_settings()
    # Debounce is skipped for image messages — the media URL cannot be stored
    # in Redis, and image uploads are discrete single-turn actions that do not
    # benefit from batching.
    if settings.agent_reply_debounce_seconds > 0 and not user_media_url_for_agent:
        redis_client = get_redis_client()
        if await redis_client.ping():
            mod_early = await agent_service.run_pre_moderation_guard(
                agent_user_message, conversation_id
            )
            if mod_early and mod_early.get("escalate"):
                role_value = get_enum_value(user_message.role)
                return SendMessageResponse(
                    message_id=message_id,
                    role=role_value,
                    content=user_message.content,
                    timestamp=to_utc_iso_string(user_message.timestamp),
                )
            notify_result = await notify_user_message_saved(
                conversation_id,
                agent_user_message=agent_user_message,
                last_user_plain_content=content_stripped,
            )
            if notify_result == "scheduled":
                role_value = get_enum_value(user_message.role)
                return SendMessageResponse(
                    message_id=message_id,
                    role=role_value,
                    content=user_message.content,
                    timestamp=to_utc_iso_string(user_message.timestamp),
                )

    # Process message through agent service.
    # If the user attached an image, pass the URL natively — the LLM receives
    # it as a multimodal image_url content block.
    result = await agent_service.process_message(
        user_message=agent_user_message,
        conversation_id=conversation_id,
        conversation_history=conversation_history,
        user_media_url=user_media_url_for_agent,
    )

    # Handle escalation
    if result.get("escalate"):
        # Status already updated in agent_service, just return user message
        # Return user message with escalation notice
        # Handle both enum and string role (from DynamoDB)
        role_value = get_enum_value(user_message.role)
        return SendMessageResponse(
            message_id=message_id,
            role=role_value,
            content=user_message.content,
            timestamp=to_utc_iso_string(user_message.timestamp),
        )

    # Agent message is already created in agent_service.process_message
    # Use the message_id from result if available, otherwise create new one
    agent_response = result.get("response", "I apologize, but I couldn't generate a response.")
    agent_message_id = result.get("agent_message_id")
    agent_message_timestamp = utc_now()

    # If message wasn't created in agent_service (shouldn't happen, but handle gracefully)
    if not agent_message_id:
        agent_message_id = str(uuid.uuid4())
        fallback_meta: dict = {"rag_context_used": result.get("rag_context_used", False)}
        if result.get("rag_media_url"):
            fallback_meta["media_url"] = result["rag_media_url"]
            fallback_meta["media_type"] = result.get("rag_media_type")
        agent_message = Message(
            message_id=agent_message_id,
            conversation_id=conversation_id,
            agent_id=conversation.agent_id,
            role=MessageRole.AGENT,
            content=agent_response,
            channel=conversation.channel,
            external_user_id=conversation.external_user_id,
            timestamp=agent_message_timestamp,
            metadata=fallback_meta,
        )
        await deps.dynamodb.create_message(agent_message)
        agent_message_timestamp = agent_message.timestamp

    # Update conversation status if needed
    # Handle both enum and string status (from DynamoDB)
    status_value = get_enum_value(conversation.status)
    if status_value != ConversationStatus.AI_ACTIVE.value:
        await deps.dynamodb.update_conversation(
            conversation_id=conversation_id,
            status=ConversationStatus.AI_ACTIVE,
        )

    return SendMessageResponse(
        message_id=agent_message_id,
        role=get_enum_value(MessageRole.AGENT),
        content=agent_response,
        timestamp=to_utc_iso_string(agent_message_timestamp),
    )


@router.get("/conversations/{conversation_id}/messages")
async def get_messages(
    conversation_id: str,
    limit: int = Query(default=100, ge=1, le=1000, description="Maximum number of messages"),
    deps: CommonDependencies = Depends(),
):
    """Get messages for a conversation."""

    # Verify conversation exists
    conversation = await deps.dynamodb.get_conversation(conversation_id)
    if not conversation:
        raise ConversationNotFoundError(conversation_id)

    messages = await deps.dynamodb.list_messages(conversation_id, limit=limit, reverse=False)
    return messages

