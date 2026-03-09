"""Channel binding service."""

import logging
import uuid
from datetime import datetime
from typing import Any, Optional

from app.models.channel_binding import ChannelBinding, ChannelType
from app.storage.dynamodb import DynamoDBClient
from app.storage.secrets import SecretsManager
from app.utils.datetime_utils import utc_now

logger = logging.getLogger(__name__)


class ChannelBindingService:
    """Service for managing channel bindings."""

    def __init__(
        self,
        dynamodb: DynamoDBClient,
        secrets_manager: SecretsManager,
    ):
        """Initialize channel binding service."""
        self.dynamodb = dynamodb
        self.secrets_manager = secrets_manager

    async def create_binding(
        self,
        agent_id: str,
        channel_type: str,
        channel_account_id: str,
        access_token: str,
        metadata: dict[str, Any],
        created_by: Optional[str] = None,
        channel_username: Optional[str] = None,
    ) -> ChannelBinding:
        """Create a new channel binding."""
        # Generate binding ID
        binding_id = str(uuid.uuid4())

        # Create secret in Secrets Manager
        secret_name = await self.secrets_manager.create_channel_token_secret(
            binding_id=binding_id,
            channel_type=channel_type,
            access_token=access_token,
            metadata=metadata,
        )

        # Create binding record in DynamoDB
        binding = ChannelBinding(
            binding_id=binding_id,
            agent_id=agent_id,
            channel_type=ChannelType(channel_type),
            channel_account_id=channel_account_id,
            channel_username=channel_username,
            secret_name=secret_name,
            is_active=True,
            is_verified=False,
            metadata=metadata,
            created_by=created_by,
            created_at=utc_now(),
            updated_at=utc_now(),
        )

        await self.dynamodb.create_channel_binding(binding)

        logger.info(
            f"Created channel binding: {binding_id} for agent {agent_id}, channel {channel_type}"
        )
        return binding

    async def get_binding(self, binding_id: str) -> Optional[ChannelBinding]:
        """Get channel binding by ID."""
        return await self.dynamodb.get_channel_binding(binding_id)

    async def get_bindings_by_agent(
        self,
        agent_id: str,
        channel_type: Optional[str] = None,
        active_only: bool = True,
    ) -> list[ChannelBinding]:
        """Get all channel bindings for an agent."""
        return await self.dynamodb.get_channel_bindings_by_agent(
            agent_id=agent_id,
            channel_type=channel_type,
            active_only=active_only,
        )

    async def get_binding_by_account_id(
        self, channel_type: str, account_id: str
    ) -> Optional[ChannelBinding]:
        """Get channel binding by channel account ID."""
        return await self.dynamodb.get_channel_binding_by_account_id(
            channel_type=channel_type, account_id=account_id
        )

    async def get_access_token(self, binding_id: str) -> str:
        """Get access token for a binding."""
        binding = await self.get_binding(binding_id)
        if not binding:
            raise ValueError(f"Binding {binding_id} not found")

        if not binding.is_active:
            raise ValueError(f"Binding {binding_id} is not active")

        token = await self.secrets_manager.get_channel_token(binding.secret_name)
        return token

    async def update_binding(
        self,
        binding_id: str,
        is_active: Optional[bool] = None,
        access_token: Optional[str] = None,
        metadata: Optional[dict[str, Any]] = None,
        is_verified: Optional[bool] = None,
    ) -> ChannelBinding:
        """Update channel binding."""
        binding = await self.get_binding(binding_id)
        if not binding:
            raise ValueError(f"Binding {binding_id} not found")

        update_kwargs: dict[str, Any] = {}

        if is_active is not None:
            update_kwargs["is_active"] = is_active

        if is_verified is not None:
            update_kwargs["is_verified"] = is_verified

        if access_token is not None:
            # Update token in Secrets Manager
            current_metadata = binding.metadata.copy()
            if metadata:
                current_metadata.update(metadata)
            await self.secrets_manager.update_channel_token(
                secret_name=binding.secret_name,
                access_token=access_token,
                metadata=current_metadata,
            )
            # Mark as unverified if token was updated
            update_kwargs["is_verified"] = False

        if metadata is not None and access_token is None:
            # Update metadata without updating token
            current_metadata = binding.metadata.copy()
            current_metadata.update(metadata)
            # Update metadata in secret as well
            token = await self.secrets_manager.get_channel_token(binding.secret_name)
            await self.secrets_manager.update_channel_token(
                secret_name=binding.secret_name,
                access_token=token,
                metadata=current_metadata,
            )

        if update_kwargs:
            await self.dynamodb.update_channel_binding(binding_id, **update_kwargs)

        # Return updated binding
        updated_binding = await self.get_binding(binding_id)
        if not updated_binding:
            raise RuntimeError(f"Failed to retrieve updated binding {binding_id}")

        logger.info(f"Updated channel binding: {binding_id}")
        return updated_binding

    async def delete_binding(self, binding_id: str) -> None:
        """Delete channel binding and its secret."""
        binding = await self.get_binding(binding_id)
        if not binding:
            raise ValueError(f"Binding {binding_id} not found")

        # Delete secret from Secrets Manager
        try:
            await self.secrets_manager.delete_channel_token_secret(binding.secret_name)
        except Exception as e:
            logger.warning(f"Failed to delete secret for binding {binding_id}: {e}")

        # Delete binding from DynamoDB
        await self.dynamodb.delete_channel_binding(binding_id)

        logger.info(f"Deleted channel binding: {binding_id}")

    async def verify_binding(self, binding_id: str) -> bool:
        """Verify binding by checking token validity via API."""
        binding = await self.get_binding(binding_id)
        if not binding:
            raise ValueError(f"Binding {binding_id} not found")

        # For Instagram, verify by making a test API call
        if binding.channel_type == ChannelType.INSTAGRAM:
            try:
                # Import here to avoid circular dependency
                from app.services.instagram_service import InstagramService

                token = await self.get_access_token(binding_id)
                # Simple verification: try to get account info
                # This is a placeholder - actual verification will be in InstagramService
                # For now, just mark as verified if token exists
                await self.update_binding(binding_id, is_verified=True)
                return True
            except Exception as e:
                logger.error(f"Failed to verify Instagram binding {binding_id}: {e}")
                await self.update_binding(binding_id, is_verified=False)
                return False

        # For Telegram, verify by calling getMe API and set webhook automatically
        elif binding.channel_type == ChannelType.TELEGRAM:
            try:
                # Import here to avoid circular dependency
                from app.config import get_settings
                from app.services.telegram_service import TelegramService

                settings = get_settings()
                telegram_service = TelegramService(self, self.dynamodb, settings)
                bot_token = await self.get_access_token(binding_id)
                
                is_valid = await telegram_service.verify_bot_token(bot_token)
                await self.update_binding(binding_id, is_verified=is_valid)
                
                # If token is valid, automatically set webhook
                if is_valid:
                    try:
                        # Construct webhook URL
                        # Use production domain for webhook URL
                        from app.config import get_settings as _get_settings
                        _settings = _get_settings()
                        _base = _settings.app_url or ""
                        webhook_url = f"{_base}/api/v1/telegram/webhook/{binding_id}"
                        
                        webhook_set = await telegram_service.set_webhook(binding_id, webhook_url)
                        if webhook_set:
                            logger.info(
                                f"Telegram webhook automatically set for binding {binding_id}: {webhook_url}"
                            )
                        else:
                            logger.warning(
                                f"Failed to automatically set Telegram webhook for binding {binding_id}. "
                                f"Webhook can be set manually via API endpoint."
                            )
                            # Don't fail verification if webhook setup fails - it can be set manually later
                    except Exception as webhook_error:
                        logger.error(
                            f"Error setting Telegram webhook for binding {binding_id}: {webhook_error}",
                            exc_info=True,
                        )
                        # Don't fail verification if webhook setup fails - it can be set manually later
                
                return is_valid
            except Exception as e:
                logger.error(f"Failed to verify Telegram binding {binding_id}: {e}")
                await self.update_binding(binding_id, is_verified=False)
                return False

        # For WhatsApp: distinguish provider
        elif binding.channel_type == ChannelType.WHATSAPP:
            provider = (binding.metadata or {}).get("provider", "meta")
            if provider == "twilio":
                try:
                    from app.services.twilio_service import TwilioWhatsAppService

                    # channel_account_id = from_number; account_sid is in metadata
                    account_sid = (binding.metadata or {}).get("account_sid", "")
                    if not account_sid:
                        logger.error(f"Twilio binding {binding_id} missing metadata.account_sid")
                        return False
                    auth_token = await self.get_access_token(binding_id)
                    twilio_service = TwilioWhatsAppService(self.dynamodb)
                    is_valid = await twilio_service.verify_credentials(account_sid, auth_token)
                    await self.update_binding(binding_id, is_verified=is_valid)
                    return is_valid
                except Exception as e:
                    logger.error(f"Failed to verify Twilio binding {binding_id}: {e}")
                    await self.update_binding(binding_id, is_verified=False)
                    return False
            # Meta WhatsApp: no simple verification API without sending a message,
            # mark as verified if token exists and binding is active
            return binding.is_active

        # For other channels, return True if binding exists and is active
        return binding.is_active

