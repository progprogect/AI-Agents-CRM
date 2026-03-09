"""Notification service for sending escalation notifications."""

import logging
from typing import Optional

from app.models.conversation import Conversation
from app.models.notification_config import NotificationType
from app.services.telegram_service import TelegramService
from app.storage.dynamodb import DynamoDBClient
from app.storage.secrets import SecretsManager

logger = logging.getLogger(__name__)


class NotificationService:
    """Service for sending escalation notifications."""

    def __init__(
        self,
        dynamodb: DynamoDBClient,
        secrets_manager: SecretsManager,
        telegram_service: TelegramService,
    ):
        """Initialize notification service."""
        self.dynamodb = dynamodb
        self.secrets_manager = secrets_manager
        self.telegram_service = telegram_service

    async def send_escalation_notification(
        self,
        conversation: Conversation,
        escalation_reason: str,
        agent_display_name: str,
        admin_panel_base_url: Optional[str] = None,
    ) -> None:
        """Send escalation notification to all active notification configs.

        Args:
            conversation: The conversation that was escalated
            escalation_reason: Reason for escalation
            agent_display_name: Display name of the agent
            admin_panel_base_url: Base URL for admin panel (for links). If None, uses default.
        """
        try:
            # Get all active notification configs
            configs = await self.dynamodb.list_notification_configs(active_only=True)

            if not configs:
                logger.debug("No active notification configs found, skipping notifications")
                return

            # Filter for Telegram notifications only (for now)
            telegram_configs = [
                config
                for config in configs
                if config.notification_type == NotificationType.TELEGRAM
            ]

            if not telegram_configs:
                logger.debug(
                    "No active Telegram notification configs found, skipping notifications"
                )
                return

            # Build notification message
            admin_url = admin_panel_base_url or ""
            conversation_url = f"{admin_url}/admin/conversations/{conversation.conversation_id}"

            message_text = (
                f"🚨 New Escalation\n\n"
                f"Conversation: {conversation.conversation_id}\n"
                f"Agent: {agent_display_name}\n"
                f"Reason: {escalation_reason}\n\n"
                f"View conversation:\n{conversation_url}"
            )

            # Send notification to each config
            for config in telegram_configs:
                try:
                    # Get bot token from Secrets Manager
                    bot_token = await self.secrets_manager.get_notification_bot_token(
                        config.bot_token_secret_name
                    )

                    # Send notification
                    await self.telegram_service.send_notification_message(
                        bot_token=bot_token,
                        chat_id=config.chat_id,
                        message_text=message_text,
                    )

                    logger.info(
                        f"Sent escalation notification to chat {config.chat_id}",
                        extra={
                            "config_id": config.config_id,
                            "conversation_id": conversation.conversation_id,
                        },
                    )
                except Exception as e:
                    # Log error but continue with other configs
                    logger.error(
                        f"Failed to send notification to config {config.config_id}: {e}",
                        extra={
                            "config_id": config.config_id,
                            "chat_id": config.chat_id,
                            "conversation_id": conversation.conversation_id,
                        },
                        exc_info=True,
                    )
                    # Continue with next config
                    continue

        except Exception as e:
            # Don't fail the escalation process if notifications fail
            logger.error(
                f"Failed to send escalation notifications: {e}",
                extra={"conversation_id": conversation.conversation_id},
                exc_info=True,
            )
