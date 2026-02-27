"""Notification configs API endpoints."""

import json
import logging
import uuid
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from app.api.auth import require_admin
from app.dependencies import CommonDependencies
from app.models.notification_config import NotificationConfig, NotificationType
from app.services.channel_binding_service import ChannelBindingService
from app.services.telegram_service import TelegramService
from app.storage.dynamodb import DynamoDBClient
from app.storage.resolver import get_secrets_manager
from app.storage.secrets import SecretsManager
from app.utils.datetime_utils import to_utc_iso_string
from app.utils.enum_helpers import get_enum_value
from app.config import get_settings

logger = logging.getLogger(__name__)
router = APIRouter()


class CreateNotificationConfigRequest(BaseModel):
    """Request to create a notification config."""

    notification_type: str = Field(..., description="Notification type (e.g., 'telegram')")
    bot_token: str = Field(..., description="Telegram bot token")
    chat_id: str = Field(..., description="Telegram chat ID for receiving notifications")
    description: Optional[str] = Field(None, description="Optional description")


class UpdateNotificationConfigRequest(BaseModel):
    """Request to update a notification config."""

    is_active: Optional[bool] = Field(None, description="Whether config is active")
    bot_token: Optional[str] = Field(None, description="New bot token")
    chat_id: Optional[str] = Field(None, description="New chat ID")
    description: Optional[str] = Field(None, description="Updated description")


class NotificationConfigResponse(BaseModel):
    """Response for notification config."""

    config_id: str
    notification_type: str
    chat_id: str
    is_active: bool
    description: Optional[str]
    created_at: str
    updated_at: str
    created_by: Optional[str]

    @classmethod
    def from_config(cls, config: NotificationConfig) -> "NotificationConfigResponse":
        """Create response from config model."""
        return cls(
            config_id=config.config_id,
            notification_type=get_enum_value(config.notification_type),
            chat_id=config.chat_id,
            is_active=config.is_active,
            description=config.description,
            created_at=to_utc_iso_string(config.created_at),
            updated_at=to_utc_iso_string(config.updated_at),
            created_by=config.created_by,
        )


def get_notification_service(
    deps: CommonDependencies = Depends(),
) -> tuple[DynamoDBClient, SecretsManager]:
    """Get dependencies for notification service."""
    secrets_manager = get_secrets_manager()
    return deps.dynamodb, secrets_manager


@router.get(
    "/notifications",
    response_model=list[NotificationConfigResponse],
)
async def list_notification_configs(
    active_only: bool = False,
    deps: CommonDependencies = Depends(),
    _admin: str = require_admin(),
):
    """List all notification configs."""
    try:
        configs = await deps.dynamodb.list_notification_configs(active_only=active_only)
        return [NotificationConfigResponse.from_config(config) for config in configs]
    except Exception as e:
        logger.error(f"Failed to list notification configs: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to list notification configs: {str(e)}",
        )


@router.post(
    "/notifications",
    response_model=NotificationConfigResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_notification_config(
    request: CreateNotificationConfigRequest,
    deps: CommonDependencies = Depends(),
    _admin: str = require_admin(),
):
    """Create a new notification config."""
    # Validate notification type
    try:
        NotificationType(request.notification_type)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid notification type: {request.notification_type}",
        )

    # Validate bot token is not empty
    if not request.bot_token.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Bot token cannot be empty",
        )

    # For Telegram, verify bot token
    if request.notification_type == NotificationType.TELEGRAM.value:
        try:
            settings = get_settings()
            secrets_manager = get_secrets_manager()
            channel_binding_service = ChannelBindingService(deps.dynamodb, secrets_manager)
            telegram_service = TelegramService(
                channel_binding_service=channel_binding_service,
                dynamodb=deps.dynamodb,
                settings=settings,
            )
            is_valid = await telegram_service.verify_bot_token(request.bot_token)
            if not is_valid:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Invalid bot token. Please verify the token is correct.",
                )
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Failed to verify bot token: {e}", exc_info=True)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to verify bot token: {str(e)}",
            )

    try:
        # Generate config ID
        config_id = str(uuid.uuid4())

        # Create secret in Secrets Manager
        secrets_manager = get_secrets_manager()
        secret_name = await secrets_manager.create_notification_token_secret(
            config_id=config_id,
            bot_token=request.bot_token,
        )

        # Create config record in DynamoDB
        config = NotificationConfig(
            config_id=config_id,
            notification_type=NotificationType(request.notification_type),
            bot_token_secret_name=secret_name,
            chat_id=request.chat_id,
            is_active=True,
            description=request.description,
            created_by=_admin,
        )

        await deps.dynamodb.create_notification_config(config)

        logger.info(
            f"Created notification config: {config_id}, type: {request.notification_type}"
        )
        return NotificationConfigResponse.from_config(config)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except Exception as e:
        logger.error(f"Failed to create notification config: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create notification config: {str(e)}",
        )


@router.get(
    "/notifications/{config_id}",
    response_model=NotificationConfigResponse,
)
async def get_notification_config(
    config_id: str,
    deps: CommonDependencies = Depends(),
    _admin: str = require_admin(),
):
    """Get notification config by ID."""
    config = await deps.dynamodb.get_notification_config(config_id)
    if not config:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Notification config {config_id} not found",
        )
    return NotificationConfigResponse.from_config(config)


@router.put(
    "/notifications/{config_id}",
    response_model=NotificationConfigResponse,
)
async def update_notification_config(
    config_id: str,
    request: UpdateNotificationConfigRequest,
    deps: CommonDependencies = Depends(),
    _admin: str = require_admin(),
):
    """Update notification config."""
    config = await deps.dynamodb.get_notification_config(config_id)
    if not config:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Notification config {config_id} not found",
        )

    update_kwargs: dict[str, Any] = {}

    if request.is_active is not None:
        update_kwargs["is_active"] = request.is_active

    if request.chat_id is not None:
        update_kwargs["chat_id"] = request.chat_id

    if request.description is not None:
        update_kwargs["description"] = request.description

    if request.bot_token is not None:
        # Validate bot token is not empty
        if not request.bot_token.strip():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Bot token cannot be empty",
            )
        # Verify bot token if provided
        secrets_manager = get_secrets_manager()
        if config.notification_type == NotificationType.TELEGRAM:
            try:
                settings = get_settings()
                channel_binding_service = ChannelBindingService(
                    deps.dynamodb, secrets_manager
                )
                telegram_service = TelegramService(
                    channel_binding_service=channel_binding_service,
                    dynamodb=deps.dynamodb,
                    settings=settings,
                )
                is_valid = await telegram_service.verify_bot_token(request.bot_token)
                if not is_valid:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail="Invalid bot token. Please verify the token is correct.",
                    )
            except HTTPException:
                raise
            except Exception as e:
                logger.error(f"Failed to verify bot token: {e}", exc_info=True)
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail=f"Failed to verify bot token: {str(e)}",
                )

        # Update token in Secrets Manager
        await secrets_manager.update_notification_token_secret(
            secret_name=config.bot_token_secret_name,
            bot_token=request.bot_token,
            created_at=to_utc_iso_string(config.created_at),
        )

    if update_kwargs:
        updated_config = await deps.dynamodb.update_notification_config(
            config_id, **update_kwargs
        )
        if not updated_config:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to update notification config",
            )
        return NotificationConfigResponse.from_config(updated_config)

    # If only bot_token was updated (no other fields), still return updated config
    # to reflect the change (even though DynamoDB record wasn't updated)
    return NotificationConfigResponse.from_config(config)


@router.delete(
    "/notifications/{config_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_notification_config(
    config_id: str,
    deps: CommonDependencies = Depends(),
    _admin: str = require_admin(),
):
    """Delete notification config and its secret."""
    config = await deps.dynamodb.get_notification_config(config_id)
    if not config:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Notification config {config_id} not found",
        )

    try:
        # Delete secret from Secrets Manager
        secrets_manager = get_secrets_manager()
        try:
            await secrets_manager.delete_notification_token_secret(config.bot_token_secret_name)
        except Exception as e:
            logger.warning(
                f"Failed to delete secret for config {config_id}: {e}",
                exc_info=True,
            )

        # Delete config from storage
        await deps.dynamodb.delete_notification_config(config_id)

        logger.info(f"Deleted notification config: {config_id}")
    except Exception as e:
        logger.error(f"Failed to delete notification config: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete notification config: {str(e)}",
        )


@router.post(
    "/notifications/{config_id}/test",
    status_code=status.HTTP_200_OK,
)
async def test_notification(
    config_id: str,
    deps: CommonDependencies = Depends(),
    _admin: str = require_admin(),
):
    """Send a test notification."""
    config = await deps.dynamodb.get_notification_config(config_id)
    if not config:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Notification config {config_id} not found",
        )

    if not config.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Notification config is not active",
        )

    try:
        secrets_manager = get_secrets_manager()
        bot_token = await secrets_manager.get_notification_bot_token(
            config.bot_token_secret_name
        )

        settings = get_settings()
        channel_binding_service = ChannelBindingService(deps.dynamodb, secrets_manager)
        telegram_service = TelegramService(
            channel_binding_service=channel_binding_service,
            dynamodb=deps.dynamodb,
            settings=settings,
        )

        test_message = (
            f"✅ Test Notification\n\n"
            f"This is a test notification from Agent system.\n"
            f"Config ID: {config_id}\n"
            f"If you received this message, your notification settings are working correctly!"
        )

        await telegram_service.send_notification_message(
            bot_token=bot_token,
            chat_id=config.chat_id,
            message_text=test_message,
        )

        return {"status": "success", "message": "Test notification sent successfully"}
    except Exception as e:
        logger.error(f"Failed to send test notification: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to send test notification: {str(e)}",
        )
