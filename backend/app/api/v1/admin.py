"""Admin API endpoints."""

import logging
import uuid
from datetime import datetime, timedelta
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field

from app.api.auth import require_admin
from app.api.exceptions import ConversationNotFoundError
from app.api.schemas import ConversationIDValidator
from app.api.websocket import connection_manager
from app.config import get_settings
from app.dependencies import CommonDependencies
from app.models.conversation import Conversation, ConversationStatus, MarketingStatus
from app.models.message import Message, MessageChannel, MessageRole
from app.services.channel_binding_service import ChannelBindingService
from app.services.channel_sender import get_channel_sender
from app.services.instagram_service import InstagramService
from app.services.telegram_service import TelegramService
from app.storage.resolver import get_secrets_manager
from app.utils.datetime_utils import parse_utc_datetime, to_utc_iso_string, utc_now
from app.utils.enum_helpers import get_enum_value

logger = logging.getLogger(__name__)

router = APIRouter()


class HandoffRequest(BaseModel):
    """Request to handoff conversation to human."""

    admin_id: str = Field(..., description="Admin user ID", min_length=1)
    reason: Optional[str] = Field(
        None, description="Reason for handoff", max_length=500
    )


class HandoffResponse(BaseModel):
    """Response for handoff."""

    conversation_id: str
    status: str
    message: str


@router.get("/conversations")
async def list_conversations(
    agent_id: Optional[str] = Query(None, description="Filter by agent ID"),
    status: Optional[str] = Query(None, description="Filter by conversation status"),
    marketing_status: Optional[str] = Query(None, description="Filter by marketing status (legacy)"),
    crm_stage_id: Optional[str] = Query(None, description="Filter by CRM stage UUID"),
    limit: int = Query(default=100, ge=1, le=1000, description="Maximum number of conversations"),
    deps: CommonDependencies = Depends(),
    _admin: str = require_admin(),
):
    """List conversations (admin view)."""
    status_enum = None
    if status:
        try:
            status_enum = ConversationStatus(status)
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid status: {status}. Valid values: {', '.join([s.value for s in ConversationStatus])}",
            )

    if marketing_status:
        valid_marketing_statuses = [s.value for s in MarketingStatus]
        if marketing_status not in valid_marketing_statuses:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid marketing_status: {marketing_status}. Valid values: {', '.join(valid_marketing_statuses)}",
            )

    conversations = await deps.dynamodb.list_conversations(
        agent_id=agent_id,
        status=status_enum,
        marketing_status=marketing_status,
        crm_stage_id=crm_stage_id,
        limit=limit,
    )
    return conversations


@router.get("/conversations/{conversation_id}", response_model=Conversation)
async def get_conversation(
    conversation_id: str,
    deps: CommonDependencies = Depends(),
    _admin: str = require_admin(),
):
    """Get conversation by ID (admin view)."""
    # Validate UUID format
    try:
        UUID(conversation_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid conversation ID format",
        )

    conversation = await deps.dynamodb.get_conversation(conversation_id)
    if not conversation:
        raise ConversationNotFoundError(conversation_id)
    
    # If this is an Instagram conversation, try to fetch profile data
    from app.utils.enum_helpers import get_enum_value
    conversation_channel = get_enum_value(conversation.channel)
    if conversation_channel == MessageChannel.INSTAGRAM.value and conversation.external_user_id:
        profile = await deps.dynamodb.get_instagram_profile(conversation.external_user_id)
        if profile:
            conversation.external_user_name = profile.name
            conversation.external_user_username = profile.username
            conversation.external_user_profile_pic = profile.profile_pic
    
    return conversation


@router.post(
    "/conversations/{conversation_id}/handoff",
    response_model=HandoffResponse,
    status_code=status.HTTP_200_OK,
)
async def handoff_conversation(
    conversation_id: str,
    request: HandoffRequest,
    deps: CommonDependencies = Depends(),
    _admin: str = require_admin(),
):
    """Handoff conversation to human admin."""
    # Validate UUID format
    try:
        UUID(conversation_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid conversation ID format",
        )

    conversation = await deps.dynamodb.get_conversation(conversation_id)
    if not conversation:
        raise ConversationNotFoundError(conversation_id)

    try:
        # Update conversation status
        updated = await deps.dynamodb.update_conversation(
            conversation_id=conversation_id,
            status=ConversationStatus.HUMAN_ACTIVE,
            handoff_reason=request.reason or "Manual handoff",
        )

        # Create audit log
        await deps.dynamodb.create_audit_log(
            admin_id=request.admin_id,
            action="handoff",
            resource_type="conversation",
            resource_id=conversation_id,
            metadata={"reason": request.reason},
        )

        # Get status value safely (handle both enum and string)
        status_value = (
            get_enum_value(updated.status) if updated else ConversationStatus.HUMAN_ACTIVE.value
        )
        
        return HandoffResponse(
            conversation_id=conversation_id,
            status=status_value,
            message="Conversation handed off to human",
        )
    except Exception as e:
        logger.error(f"Error handing off conversation: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to handoff conversation: {str(e)}",
        )


class ReturnToAIRequest(BaseModel):
    """Request to return conversation to AI."""

    admin_id: str = Field(..., description="Admin user ID", min_length=1)


@router.post("/conversations/{conversation_id}/return")
async def return_to_ai(
    conversation_id: str,
    request: ReturnToAIRequest,
    deps: CommonDependencies = Depends(),
    _admin: str = require_admin(),
):
    """Return conversation to AI."""
    # Validate UUID format
    try:
        UUID(conversation_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid conversation ID format",
        )

    conversation = await deps.dynamodb.get_conversation(conversation_id)
    if not conversation:
        raise ConversationNotFoundError(conversation_id)

    try:
        # Update conversation status
        updated = await deps.dynamodb.update_conversation(
            conversation_id=conversation_id,
            status=ConversationStatus.AI_ACTIVE,
        )

        # Create audit log
        await deps.dynamodb.create_audit_log(
            admin_id=request.admin_id,
            action="return_to_ai",
            resource_type="conversation",
            resource_id=conversation_id,
        )

        # Get status value safely (handle both enum and string)
        status_value = (
            get_enum_value(updated.status) if updated else ConversationStatus.AI_ACTIVE.value
        )
        
        return {
            "conversation_id": conversation_id,
            "status": status_value,
            "message": "Conversation returned to AI",
        }
    except Exception as e:
        logger.error(f"Error returning conversation to AI: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to return conversation to AI: {str(e)}",
        )


@router.get("/audit")
async def get_audit_logs(
    admin_id: Optional[str] = Query(None, description="Filter by admin ID"),
    resource_type: Optional[str] = Query(None, description="Filter by resource type"),
    action: Optional[str] = Query(None, description="Filter by action"),
    start_date: Optional[str] = Query(None, description="Start date (ISO format)"),
    end_date: Optional[str] = Query(None, description="End date (ISO format)"),
    sort: str = Query(default="desc", description="Sort order: 'asc' or 'desc'"),
    limit: int = Query(default=100, ge=1, le=1000, description="Maximum number of logs"),
    deps: CommonDependencies = Depends(),
    _admin: str = require_admin(),
):
    """Get audit logs with filtering and sorting."""
    try:
        # Validate sort parameter
        if sort not in ["asc", "desc"]:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid sort parameter. Must be 'asc' or 'desc'",
            )
        
        # Parse dates if provided
        start_datetime = None
        end_datetime = None
        if start_date:
            try:
                start_datetime = parse_utc_datetime(start_date)
            except ValueError as e:
                logger.warning(f"Invalid start_date format: {start_date}, error: {e}")
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Invalid start_date format. Use ISO format (e.g., 2024-01-01T00:00:00Z)",
                )
        if end_date:
            try:
                end_datetime = parse_utc_datetime(end_date)
            except ValueError as e:
                logger.warning(f"Invalid end_date format: {end_date}, error: {e}")
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Invalid end_date format. Use ISO format (e.g., 2024-01-01T00:00:00Z)",
                )
        
        logs = await deps.dynamodb.list_audit_logs(
            admin_id=admin_id,
            resource_type=resource_type,
            action=action,
            start_date=start_datetime,
            end_date=end_datetime,
            sort_desc=sort == "desc",
            limit=limit,
        )
        
        # Ensure we always return a list, even if empty
        if not isinstance(logs, list):
            logger.warning(f"list_audit_logs returned non-list: {type(logs)}")
            return []
        
        return logs
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Unexpected error in get_audit_logs: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve audit logs: {str(e)}",
        )


class SendAdminMessageRequest(BaseModel):
    """Request to send admin message."""

    admin_id: str = Field(..., description="Admin user ID", min_length=1)
    content: str = Field(..., description="Message content", min_length=1, max_length=10000)


class SendAdminMessageResponse(BaseModel):
    """Response for admin message."""

    message_id: str
    role: str
    content: str
    timestamp: str


@router.post(
    "/conversations/{conversation_id}/messages",
    response_model=SendAdminMessageResponse,
    status_code=status.HTTP_201_CREATED,
)
async def send_admin_message(
    conversation_id: str,
    request: SendAdminMessageRequest,
    deps: CommonDependencies = Depends(),
    _admin: str = require_admin(),
):
    """Send a message as admin in a conversation."""
    # Validate UUID format
    try:
        UUID(conversation_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid conversation ID format",
        )

    conversation = await deps.dynamodb.get_conversation(conversation_id)
    if not conversation:
        raise ConversationNotFoundError(conversation_id)

    # Check conversation status - admin can only send messages when human is handling
    status_value = get_enum_value(conversation.status)
    if status_value not in [
        ConversationStatus.NEEDS_HUMAN.value,
        ConversationStatus.HUMAN_ACTIVE.value,
    ]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Admin can only send messages when conversation status is NEEDS_HUMAN or HUMAN_ACTIVE",
        )

    try:
        # Create admin message
        message_id = str(uuid.uuid4())
        admin_message = Message(
            message_id=message_id,
            conversation_id=conversation_id,
            agent_id=conversation.agent_id,
            role=MessageRole.ADMIN,
            content=request.content,
            channel=conversation.channel,
            external_user_id=conversation.external_user_id,
            timestamp=utc_now(),
        )

        logger.info(f"Creating admin message: conversation_id={conversation_id}, message_id={message_id}, content_len={len(request.content)}")
        await deps.dynamodb.create_message(admin_message)
        logger.info(f"Admin message created successfully: message_id={message_id}")
        
        # Verify message was saved by reading it back
        verify_msg = await deps.dynamodb.get_message(conversation_id, message_id)
        if verify_msg:
            logger.info(f"Message verification: message_id={message_id}, found=True, role={get_enum_value(verify_msg.role)}")
        else:
            logger.error(f"Message verification FAILED: message_id={message_id}, found=False")
        
        # Check messages list immediately after save
        msgs_after_save = await deps.dynamodb.list_messages(conversation_id, limit=100, reverse=False)
        contains_new = message_id in [m.message_id for m in msgs_after_save]
        logger.info(f"Messages list after save: conversation_id={conversation_id}, count={len(msgs_after_save)}, contains_new={contains_new}, message_ids={[m.message_id for m in msgs_after_save[:5]]}")

        # Determine channel and send message accordingly
        conversation_channel = get_enum_value(conversation.channel)
        
        if conversation_channel == MessageChannel.INSTAGRAM.value:
            # Send via Instagram API for Instagram conversations
            try:
                # Create Instagram service and sender
                settings = get_settings()
                secrets_manager = get_secrets_manager()
                binding_service = ChannelBindingService(deps.dynamodb, secrets_manager)
                instagram_service = InstagramService(binding_service, deps.dynamodb, settings)
                
                # Convert string back to enum for get_channel_sender
                channel_enum = MessageChannel(conversation_channel) if isinstance(conversation_channel, str) else conversation.channel
                instagram_sender = get_channel_sender(
                    channel_enum, deps.dynamodb, instagram_service
                )
                
                # Send message via Instagram API
                await instagram_sender.send_message(
                    conversation_id=conversation_id,
                    message_text=request.content,
                )
                
                logger.info(f"Sent admin message to Instagram conversation {conversation_id}")
            except ValueError as e:
                # No binding or missing external_user_id - return clear error
                logger.error(f"Failed to send Instagram message: {e}")
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Cannot send message to Instagram conversation: {str(e)}",
                )
            except Exception as instagram_error:
                # Instagram API error - log but don't fail (message already saved)
                logger.error(
                    f"Failed to send message via Instagram API: {instagram_error}",
                    exc_info=True,
                )
                # Message is already saved in DB, so we continue
        elif conversation_channel == MessageChannel.TELEGRAM.value:
            # Send via Telegram API for Telegram conversations
            try:
                # Create Telegram service and sender
                settings = get_settings()
                secrets_manager = get_secrets_manager()
                binding_service = ChannelBindingService(deps.dynamodb, secrets_manager)
                telegram_service = TelegramService(binding_service, deps.dynamodb, settings)
                
                # Convert string back to enum for get_channel_sender
                channel_enum = MessageChannel(conversation_channel) if isinstance(conversation_channel, str) else conversation.channel
                telegram_sender = get_channel_sender(
                    channel_enum, deps.dynamodb, telegram_service=telegram_service
                )
                
                # Send message via Telegram API
                await telegram_sender.send_message(
                    conversation_id=conversation_id,
                    message_text=request.content,
                )
                
                logger.info(f"Sent admin message to Telegram conversation {conversation_id}")
            except ValueError as e:
                # No binding or missing external_user_id - return clear error
                logger.error(f"Failed to send Telegram message: {e}")
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Cannot send message to Telegram conversation: {str(e)}",
                )
            except Exception as telegram_error:
                # Telegram API error - log but don't fail (message already saved)
                logger.error(
                    f"Failed to send message via Telegram API: {telegram_error}",
                    exc_info=True,
                )
                # Message is already saved in DB, so we continue
        else:
            # Send via WebSocket for web chat (don't fail if WebSocket is not connected)
            try:
                await connection_manager.send_message(
                    conversation_id,
                    {
                        "type": "message",
                        "message_id": message_id,
                        "role": "admin",
                        "content": request.content,
                        "timestamp": to_utc_iso_string(admin_message.timestamp),
                    },
                )
            except Exception as ws_error:
                # Log but don't fail the request if WebSocket fails
                logger.warning(f"Failed to send message via WebSocket: {ws_error}")

        # Create audit log
        await deps.dynamodb.create_audit_log(
            admin_id=request.admin_id,
            action="send_message",
            resource_type="conversation",
            resource_id=conversation_id,
            metadata={"message_id": message_id},
        )

        # Handle both enum and string role (from DynamoDB)
        role_value = get_enum_value(admin_message.role)
        return SendAdminMessageResponse(
            message_id=message_id,
            role=role_value,
            content=admin_message.content,
            timestamp=to_utc_iso_string(admin_message.timestamp),
        )
    except Exception as e:
        logger.error(f"Error sending admin message: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to send admin message: {str(e)}",
        )


class RefreshProfileResponse(BaseModel):
    """Response for profile refresh."""

    name: Optional[str] = None
    username: Optional[str] = None
    profile_pic: Optional[str] = None
    error: Optional[str] = None


class UpdateMarketingStatusRequest(BaseModel):
    """Request to update marketing status."""

    marketing_status: str = Field(..., description="New marketing status")
    rejection_reason: Optional[str] = Field(
        None, description="Reason for rejection (required when marketing_status is REJECTED)", max_length=1000
    )
    admin_id: str = Field(..., description="Admin user ID", min_length=1)


class UpdateMarketingStatusResponse(BaseModel):
    """Response for marketing status update."""

    conversation_id: str
    marketing_status: str
    rejection_reason: Optional[str] = None
    message: str


@router.post(
    "/conversations/{conversation_id}/refresh-profile",
    response_model=RefreshProfileResponse,
    status_code=status.HTTP_200_OK,
)
async def refresh_instagram_profile(
    conversation_id: str,
    deps: CommonDependencies = Depends(),
    _admin: str = require_admin(),
):
    """Refresh Instagram user profile information."""
    # Validate UUID format
    try:
        UUID(conversation_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid conversation ID format",
        )

    # Get conversation
    conversation = await deps.dynamodb.get_conversation(conversation_id)
    if not conversation:
        raise ConversationNotFoundError(conversation_id)

    # Verify it's an Instagram conversation
    conversation_channel = get_enum_value(conversation.channel)
    if conversation_channel != MessageChannel.INSTAGRAM.value:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This endpoint is only available for Instagram conversations",
        )

    if not conversation.external_user_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Conversation does not have an external user ID",
        )

    # Find active binding for agent
    secrets_manager = get_secrets_manager()
    binding_service = ChannelBindingService(deps.dynamodb, secrets_manager)
    
    bindings = await binding_service.get_bindings_by_agent(
        agent_id=conversation.agent_id,
        channel_type=MessageChannel.INSTAGRAM.value,
        active_only=True,
    )

    if not bindings:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No active Instagram binding found for this agent",
        )

    binding_id = bindings[0].binding_id

    # Get Instagram service
    instagram_service = InstagramService(
        binding_service, deps.dynamodb, get_settings()
    )

    # Refresh profile
    try:
        profile = await instagram_service.refresh_user_profile(
            conversation.external_user_id, binding_id
        )

        if profile:
            return RefreshProfileResponse(
                name=profile.name,
                username=profile.username,
                profile_pic=profile.profile_pic,
            )
        else:
            return RefreshProfileResponse(
                error="Failed to fetch profile. User consent may be required or user may have blocked this account."
            )
    except Exception as e:
        logger.error(f"Error refreshing Instagram profile: {e}", exc_info=True)
        return RefreshProfileResponse(
            error=f"Failed to refresh profile: {str(e)}"
        )


@router.patch(
    "/conversations/{conversation_id}/marketing-status",
    response_model=UpdateMarketingStatusResponse,
    status_code=status.HTTP_200_OK,
)
async def update_marketing_status(
    conversation_id: str,
    request: UpdateMarketingStatusRequest,
    deps: CommonDependencies = Depends(),
    _admin: str = require_admin(),
):
    """Update marketing status of a conversation."""
    # Validate UUID format
    try:
        UUID(conversation_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid conversation ID format",
        )

    # Validate marketing status
    valid_marketing_statuses = [s.value for s in MarketingStatus]
    if request.marketing_status not in valid_marketing_statuses:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid marketing_status: {request.marketing_status}. Valid values: {', '.join(valid_marketing_statuses)}",
        )

    # Validate rejection_reason is provided when status is REJECTED
    if request.marketing_status == MarketingStatus.REJECTED.value:
        if not request.rejection_reason or not request.rejection_reason.strip():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="rejection_reason is required when marketing_status is REJECTED",
            )

    # Get current conversation
    conversation = await deps.dynamodb.get_conversation(conversation_id)
    if not conversation:
        raise ConversationNotFoundError(conversation_id)

    # Get old marketing status for audit log
    old_marketing_status = get_enum_value(conversation.marketing_status) if conversation.marketing_status else MarketingStatus.NEW.value

    try:
        # Update conversation
        update_kwargs = {
            "marketing_status": request.marketing_status,
        }
        
        # Update rejection_reason
        if request.marketing_status == MarketingStatus.REJECTED.value:
            update_kwargs["rejection_reason"] = request.rejection_reason
        else:
            # Clear rejection_reason when status is not REJECTED
            update_kwargs["rejection_reason"] = None

        updated = await deps.dynamodb.update_conversation(
            conversation_id=conversation_id,
            **update_kwargs,
        )

        if not updated:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to update marketing status",
            )

        # Create audit log entry
        await deps.dynamodb.create_audit_log(
            admin_id=request.admin_id,
            action="update_marketing_status",
            resource_type="conversation",
            resource_id=conversation_id,
            metadata={
                "old_marketing_status": old_marketing_status,
                "new_marketing_status": request.marketing_status,
                "rejection_reason": request.rejection_reason if request.marketing_status == MarketingStatus.REJECTED.value else None,
            },
        )

        # Broadcast update to admin dashboard
        try:
            from app.api.admin_websocket import get_admin_broadcast_manager
            broadcast_manager = get_admin_broadcast_manager()
            await broadcast_manager.broadcast_conversation_update(updated)
        except Exception as e:
            logger.warning(
                f"Failed to broadcast marketing status update: {e}",
                exc_info=True,
            )

        return UpdateMarketingStatusResponse(
            conversation_id=conversation_id,
            marketing_status=request.marketing_status,
            rejection_reason=request.rejection_reason if request.marketing_status == MarketingStatus.REJECTED.value else None,
            message="Marketing status updated successfully",
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating marketing status: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update marketing status: {str(e)}",
        )


@router.get("/stats")
async def get_stats(
    period: Optional[str] = Query(
        default="today",
        description="Time period: 'today', 'last_7_days', 'last_30_days'",
    ),
    include_comparison: bool = Query(
        default=False,
        description="Include comparison with previous period",
    ),
    deps: CommonDependencies = Depends(),
    _admin: str = require_admin(),
):
    """Get statistics with optional period filtering and comparison."""
    # Validate period parameter
    valid_periods = ["today", "last_7_days", "last_30_days"]
    if period not in valid_periods:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid period. Must be one of: {', '.join(valid_periods)}",
        )

    # Calculate date range based on period
    from datetime import timezone as tz
    now = utc_now()
    if period == "today":
        # Use timezone-aware datetime to avoid comparison errors with PostgreSQL timestamps
        start_date = datetime(now.year, now.month, now.day, 0, 0, 0, tzinfo=tz.utc)
        end_date = now
    elif period == "last_7_days":
        start_date = now - timedelta(days=7)
        end_date = now
    else:  # last_30_days
        start_date = now - timedelta(days=30)
        end_date = now

    # Get conversations for the period
    all_conversations = await deps.dynamodb.list_conversations(limit=1000)
    
    # Filter conversations by date range (handle both datetime and string formats)
    from datetime import timezone as tz
    period_conversations = []
    for c in all_conversations:
        if not c.created_at:
            continue
        created_dt = None
        if isinstance(c.created_at, datetime):
            created_dt = c.created_at
        elif isinstance(c.created_at, str):
            try:
                created_dt = parse_utc_datetime(c.created_at)
            except (ValueError, AttributeError):
                continue
        if created_dt is None:
            continue
        # Normalise to UTC-aware to avoid naive/aware comparison errors
        if created_dt.tzinfo is None:
            created_dt = created_dt.replace(tzinfo=tz.utc)
        _start = start_date.replace(tzinfo=tz.utc) if start_date.tzinfo is None else start_date
        _end = end_date.replace(tzinfo=tz.utc) if end_date.tzinfo is None else end_date
        if _start <= created_dt <= _end:
            period_conversations.append(c)

    # Calculate technical status metrics
    stats = {
        "total_conversations": len(period_conversations),
        "ai_active": sum(
            1
            for c in period_conversations
            if get_enum_value(c.status) == ConversationStatus.AI_ACTIVE.value
        ),
        "needs_human": sum(
            1
            for c in period_conversations
            if get_enum_value(c.status) == ConversationStatus.NEEDS_HUMAN.value
        ),
        "human_active": sum(
            1
            for c in period_conversations
            if get_enum_value(c.status) == ConversationStatus.HUMAN_ACTIVE.value
        ),
        "closed": sum(
            1
            for c in period_conversations
            if get_enum_value(c.status) == ConversationStatus.CLOSED.value
        ),
        # Marketing status metrics
        "marketing_new": sum(
            1
            for c in period_conversations
            if get_enum_value(c.marketing_status) == MarketingStatus.NEW.value
        ),
        "marketing_booked": sum(
            1
            for c in period_conversations
            if get_enum_value(c.marketing_status) == MarketingStatus.BOOKED.value
        ),
        "marketing_no_response": sum(
            1
            for c in period_conversations
            if get_enum_value(c.marketing_status) == MarketingStatus.NO_RESPONSE.value
        ),
        "marketing_rejected": sum(
            1
            for c in period_conversations
            if get_enum_value(c.marketing_status) == MarketingStatus.REJECTED.value
        ),
        "period": period,
    }

    # Add dynamic CRM stage stats using SQL aggregation
    from app.storage.postgres_crm import PostgresCRMStorage
    crm_storage = PostgresCRMStorage()
    stats["crm_stage_stats"] = await crm_storage.get_stage_counts(
        start_date=start_date, end_date=end_date
    )

    # Calculate comparison if requested
    if include_comparison:
        # Calculate previous period
        if period == "today":
            prev_start = start_date - timedelta(days=1)
            prev_end = start_date
        elif period == "last_7_days":
            prev_start = start_date - timedelta(days=7)
            prev_end = start_date
        else:  # last_30_days
            prev_start = start_date - timedelta(days=30)
            prev_end = start_date

        # Get previous period conversations (handle both datetime and string formats)
        prev_conversations = []
        for c in all_conversations:
            if not c.created_at:
                continue
            created_dt = None
            if isinstance(c.created_at, datetime):
                created_dt = c.created_at
            elif isinstance(c.created_at, str):
                try:
                    created_dt = parse_utc_datetime(c.created_at)
                except (ValueError, AttributeError):
                    continue
            if created_dt is None:
                continue
            if created_dt.tzinfo is None:
                created_dt = created_dt.replace(tzinfo=tz.utc)
            _ps = prev_start.replace(tzinfo=tz.utc) if prev_start.tzinfo is None else prev_start
            _pe = prev_end.replace(tzinfo=tz.utc) if prev_end.tzinfo is None else prev_end
            if _ps <= created_dt < _pe:
                prev_conversations.append(c)

        prev_stats = {
            "total_conversations": len(prev_conversations),
            "ai_active": sum(
                1
                for c in prev_conversations
                if get_enum_value(c.status) == ConversationStatus.AI_ACTIVE.value
            ),
            "needs_human": sum(
                1
                for c in prev_conversations
                if get_enum_value(c.status) == ConversationStatus.NEEDS_HUMAN.value
            ),
            "human_active": sum(
                1
                for c in prev_conversations
                if get_enum_value(c.status) == ConversationStatus.HUMAN_ACTIVE.value
            ),
            "closed": sum(
                1
                for c in prev_conversations
                if get_enum_value(c.status) == ConversationStatus.CLOSED.value
            ),
            "marketing_new": sum(
                1
                for c in prev_conversations
                if get_enum_value(c.marketing_status) == MarketingStatus.NEW.value
            ),
            "marketing_booked": sum(
                1
                for c in prev_conversations
                if get_enum_value(c.marketing_status) == MarketingStatus.BOOKED.value
            ),
            "marketing_no_response": sum(
                1
                for c in prev_conversations
                if get_enum_value(c.marketing_status) == MarketingStatus.NO_RESPONSE.value
            ),
            "marketing_rejected": sum(
                1
                for c in prev_conversations
                if get_enum_value(c.marketing_status) == MarketingStatus.REJECTED.value
            ),
        }

        # Calculate changes
        stats["comparison"] = {
            "total_conversations": stats["total_conversations"] - prev_stats["total_conversations"],
            "ai_active": stats["ai_active"] - prev_stats["ai_active"],
            "needs_human": stats["needs_human"] - prev_stats["needs_human"],
            "human_active": stats["human_active"] - prev_stats["human_active"],
            "closed": stats["closed"] - prev_stats["closed"],
            "marketing_new": stats["marketing_new"] - prev_stats["marketing_new"],
            "marketing_booked": stats["marketing_booked"] - prev_stats["marketing_booked"],
            "marketing_no_response": stats["marketing_no_response"] - prev_stats["marketing_no_response"],
            "marketing_rejected": stats["marketing_rejected"] - prev_stats["marketing_rejected"],
        }

    return stats


# ── Channel configuration ─────────────────────────────────────────────────────

@router.get("/channel-config")
async def get_channel_config(_admin: str = require_admin()):
    """Return webhook URLs and verify tokens for all supported channels (admin only)."""
    from app.storage.postgres_secrets import get_postgres_secrets_manager
    import uuid as _uuid

    settings = get_settings()
    base = settings.app_url.rstrip("/") if settings.app_url else ""
    mgr = get_postgres_secrets_manager()

    # Auto-generate WhatsApp verify token on first access
    wa_verify_token = await mgr.get_global_setting("whatsapp_verify_token")
    if not wa_verify_token:
        wa_verify_token = f"caworks-wa-{_uuid.uuid4().hex[:12]}"
        await mgr.set_global_setting("whatsapp_verify_token", wa_verify_token)

    wa_app_secret_set = (await mgr.get_global_setting("whatsapp_app_secret")) is not None

    return {
        "app_url": base,
        "instagram_webhook_url": f"{base}/api/v1/instagram/webhook",
        "instagram_verify_token": settings.instagram_webhook_verify_token or "",
        "telegram_webhook_base": f"{base}/api/v1/telegram/webhook",
        "whatsapp_webhook_url": f"{base}/api/v1/whatsapp/webhook",
        "whatsapp_verify_token": wa_verify_token,
        "whatsapp_app_secret_configured": wa_app_secret_set,
    }


class WhatsAppSettingsRequest(BaseModel):
    verify_token: Optional[str] = Field(None, min_length=4, max_length=256)
    app_secret: Optional[str] = Field(None, max_length=512)


@router.put("/whatsapp-settings")
async def update_whatsapp_settings(
    body: WhatsAppSettingsRequest,
    _admin: str = require_admin(),
):
    """Save WhatsApp app-level settings (verify token + app secret) to the DB."""
    from app.storage.postgres_secrets import get_postgres_secrets_manager
    mgr = get_postgres_secrets_manager()

    if body.verify_token is not None:
        await mgr.set_global_setting("whatsapp_verify_token", body.verify_token)
    if body.app_secret is not None:
        await mgr.set_global_setting("whatsapp_app_secret", body.app_secret)

    return {"message": "WhatsApp settings updated successfully"}

