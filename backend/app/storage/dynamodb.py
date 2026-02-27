"""DynamoDB client wrapper."""

import asyncio
import logging
import time
from datetime import datetime, timedelta
from decimal import Decimal
from functools import lru_cache
from typing import Any, Optional

import boto3
from botocore.exceptions import ClientError
from pydantic import BaseModel

from app.config import Settings, get_settings
from app.models.channel_binding import ChannelBinding
from app.models.conversation import Conversation, ConversationStatus, MarketingStatus
from app.models.instagram_user_profile import InstagramUserProfile
from app.models.message import Message, MessageRole
from app.utils.datetime_utils import parse_utc_datetime, to_utc_iso_string, utc_now
from app.utils.enum_helpers import get_enum_value

logger = logging.getLogger(__name__)


class DynamoDBClient:
    """DynamoDB client wrapper."""

    def __init__(self, settings: Settings):
        """Initialize DynamoDB client."""
        self.settings = settings
        self.dynamodb = boto3.resource(
            "dynamodb",
            region_name=settings.aws_region,
            endpoint_url=settings.dynamodb_endpoint_url,
            aws_access_key_id=settings.aws_access_key_id,
            aws_secret_access_key=settings.aws_secret_access_key,
        )
        self.tables = {
            "conversations": self.dynamodb.Table(settings.dynamodb_table_conversations),
            "messages": self.dynamodb.Table(settings.dynamodb_table_messages),
            "agents": self.dynamodb.Table(settings.dynamodb_table_agents),
            "audit_logs": self.dynamodb.Table(settings.dynamodb_table_audit_logs),
            "channel_bindings": self.dynamodb.Table(settings.dynamodb_table_channel_bindings),
            "instagram_profiles": self.dynamodb.Table(settings.dynamodb_table_instagram_profiles),
            "notification_configs": self.dynamodb.Table(settings.dynamodb_table_notification_configs),
        }
        self.message_ttl_seconds = settings.message_ttl_hours * 3600
        
        # Reserved keywords in DynamoDB that require ExpressionAttributeNames
        self._reserved_keywords = {"is_active", "status"}

    def _build_expression_attribute_names(
        self, attributes: list[str]
    ) -> dict[str, str]:
        """
        Build ExpressionAttributeNames dict for DynamoDB reserved keywords.
        
        Args:
            attributes: List of attribute names that may be reserved keywords
            
        Returns:
            Dict mapping placeholder names (e.g., "#is_active") to actual names
        """
        result = {}
        for attr in attributes:
            if attr in self._reserved_keywords:
                result[f"#{attr}"] = attr
        return result

    def _build_filter_expression(
        self,
        conditions: list[tuple[str, str, Any]],
        expression_attribute_values: dict[str, Any],
        expression_attribute_names: Optional[dict[str, str]] = None,
    ) -> tuple[str, dict[str, Any], dict[str, str]]:
        """
        Build FilterExpression for DynamoDB queries/scans.
        
        Args:
            conditions: List of (attribute, operator, value_placeholder) tuples
                       e.g., [("is_active", "=", ":active")]
            expression_attribute_values: Dict to populate with values
            expression_attribute_names: Optional existing attribute names dict
            
        Returns:
            Tuple of (filter_expression, updated_values, updated_names)
        """
        if not conditions:
            return "", expression_attribute_values, expression_attribute_names or {}
        
        filter_parts = []
        names = expression_attribute_names.copy() if expression_attribute_names else {}
        
        for attr, operator, value_placeholder in conditions:
            # Use placeholder if attribute is reserved keyword
            attr_placeholder = f"#{attr}" if attr in self._reserved_keywords else attr
            if attr in self._reserved_keywords:
                names[f"#{attr}"] = attr
            
            filter_parts.append(f"{attr_placeholder} {operator} {value_placeholder}")
        
        filter_expression = " AND ".join(filter_parts)
        return filter_expression, expression_attribute_values, names

    def _convert_floats_to_decimal(self, obj: Any) -> Any:
        """Recursively convert float values to Decimal for DynamoDB compatibility."""
        if isinstance(obj, float):
            return Decimal(str(obj))
        elif isinstance(obj, dict):
            return {k: self._convert_floats_to_decimal(v) for k, v in obj.items()}
        elif isinstance(obj, list):
            return [self._convert_floats_to_decimal(item) for item in obj]
        else:
            return obj

    def _calculate_ttl(self, base_time: datetime) -> int:
        """Calculate TTL timestamp (Unix epoch seconds)."""
        expiry_time = base_time + timedelta(seconds=self.message_ttl_seconds)
        return int(expiry_time.timestamp())

    def _calculate_profile_ttl(self, base_time: datetime) -> int:
        """Calculate TTL timestamp for Instagram profiles (5 days = 432000 seconds)."""
        profile_ttl_seconds = 5 * 24 * 3600  # 5 days
        expiry_time = base_time + timedelta(seconds=profile_ttl_seconds)
        return int(expiry_time.timestamp())

    # Conversation operations
    async def create_conversation(self, conversation: Conversation) -> Conversation:
        """Create a new conversation."""
        item = conversation.model_dump(exclude_none=True)
        # Convert datetime objects to ISO format strings for DynamoDB
        if "created_at" in item and isinstance(item["created_at"], datetime):
            item["created_at"] = to_utc_iso_string(item["created_at"])
        if "updated_at" in item and isinstance(item["updated_at"], datetime):
            item["updated_at"] = to_utc_iso_string(item["updated_at"])
        item["ttl"] = self._calculate_ttl(conversation.created_at)
        
        # Ensure marketing_status defaults to NEW if not set
        if "marketing_status" not in item or item["marketing_status"] is None:
            item["marketing_status"] = MarketingStatus.NEW.value

        self.tables["conversations"].put_item(Item=item)
        return conversation

    async def get_conversation(self, conversation_id: str) -> Optional[Conversation]:
        """Get conversation by ID."""
        response = self.tables["conversations"].get_item(
            Key={"conversation_id": conversation_id}
        )
        item = response.get("Item")
        if not item:
            return None
        # Ensure marketing_status defaults to NEW for existing conversations
        if "marketing_status" not in item or item["marketing_status"] is None:
            item["marketing_status"] = MarketingStatus.NEW.value
        return Conversation(**item)

    async def update_conversation(
        self,
        conversation_id: str,
        status: Optional[ConversationStatus] = None,
        handoff_reason: Optional[str] = None,
        request_type: Optional[str] = None,
        **kwargs: Any,
    ) -> Optional[Conversation]:
        """Update conversation."""
        # Get old conversation to check status change
        old_conversation = await self.get_conversation(conversation_id)
        old_status = None
        if old_conversation:
            old_status = get_enum_value(old_conversation.status)

        update_expression_parts = []
        expression_attribute_values = {}
        expression_attribute_names = {}

        if status:
            update_expression_parts.append("#status = :status")
            expression_attribute_names["#status"] = "status"
            expression_attribute_values[":status"] = status.value

        if handoff_reason is not None:
            update_expression_parts.append("handoff_reason = :handoff_reason")
            expression_attribute_values[":handoff_reason"] = handoff_reason

        if request_type is not None:
            update_expression_parts.append("request_type = :request_type")
            expression_attribute_values[":request_type"] = request_type

        for key, value in kwargs.items():
            update_expression_parts.append(f"{key} = :{key}")
            expression_attribute_values[f":{key}"] = value

        if not update_expression_parts:
            return await self.get_conversation(conversation_id)

        update_expression_parts.append("updated_at = :updated_at")
        expression_attribute_values[":updated_at"] = to_utc_iso_string(utc_now())

        try:
            update_kwargs = {
                "Key": {"conversation_id": conversation_id},
                "UpdateExpression": f"SET {', '.join(update_expression_parts)}",
                "ExpressionAttributeValues": expression_attribute_values,
                "ReturnValues": "ALL_NEW",
            }
            # Only include ExpressionAttributeNames if it's not empty
            # DynamoDB doesn't accept empty ExpressionAttributeNames
            if expression_attribute_names:
                update_kwargs["ExpressionAttributeNames"] = expression_attribute_names
            
            self.tables["conversations"].update_item(**update_kwargs)
            updated_conversation = await self.get_conversation(conversation_id)
            
            # Broadcast update to admin dashboard
            if updated_conversation:
                try:
                    from app.api.admin_websocket import get_admin_broadcast_manager
                    from app.models.conversation import ConversationStatus
                    
                    broadcast_manager = get_admin_broadcast_manager()
                    new_status = get_enum_value(updated_conversation.status)
                    
                    # Check if this is a new escalation (status changed to NEEDS_HUMAN)
                    if (
                        status
                        and status == ConversationStatus.NEEDS_HUMAN
                        and (old_status is None or old_status != ConversationStatus.NEEDS_HUMAN.value)
                    ):
                        await broadcast_manager.broadcast_new_escalation(
                            updated_conversation, handoff_reason
                        )
                        
                        # Send Telegram notifications (async, non-blocking)
                        try:
                            # Import here to avoid circular dependencies and handle missing modules gracefully
                            try:
                                from app.services.notification_service import NotificationService
                                from app.services.telegram_service import TelegramService
                                from app.storage.resolver import get_secrets_manager
                                from app.config import get_settings
                            except ImportError as import_error:
                                logger.debug(
                                    f"Notification service modules not available: {import_error}. "
                                    "Skipping notification sending."
                                )
                                # Skip notification sending if modules are not available
                                pass
                            else:
                                # Get agent display name for notification
                                agent_data = await self.get_agent(updated_conversation.agent_id)
                                agent_display_name = "Unknown Agent"
                                if agent_data and "config" in agent_data:
                                    from app.models.agent_config import AgentConfig
                                    agent_config = AgentConfig.from_dict(agent_data["config"])
                                    agent_display_name = agent_config.profile.agent_display_name
                                
                                # Create notification service
                                # Note: TelegramService requires channel_binding_service for some methods,
                                # but send_notification_message doesn't need it, so we can pass a dummy
                                # For notifications, we only use send_notification_message which doesn't use channel_binding_service
                                secrets_manager = get_secrets_manager()
                                settings = get_settings()
                                from app.services.channel_binding_service import ChannelBindingService
                                # Create a minimal ChannelBindingService instance (won't be used for notifications)
                                channel_binding_service = ChannelBindingService(self, secrets_manager)
                                telegram_service = TelegramService(
                                    channel_binding_service=channel_binding_service,
                                    dynamodb=self,
                                    settings=settings
                                )
                                notification_service = NotificationService(
                                    dynamodb=self,
                                    secrets_manager=secrets_manager,
                                    telegram_service=telegram_service
                                )
                                
                                # Send notifications (async, non-blocking)
                                # Use asyncio.create_task to not block the main flow
                                asyncio.create_task(
                                    notification_service.send_escalation_notification(
                                        conversation=updated_conversation,
                                        escalation_reason=handoff_reason or "Escalation required",
                                        agent_display_name=agent_display_name
                                    )
                                )
                        except Exception as e:
                            # Don't fail the update if notification fails
                            logger.warning(
                                f"Failed to send escalation notifications: {e}",
                                exc_info=True
                            )
                    else:
                        # Regular status update
                        await broadcast_manager.broadcast_conversation_update(
                            updated_conversation
                        )
                except Exception as e:
                    # Don't fail the update if broadcast fails
                    import logging
                    logger = logging.getLogger(__name__)
                    logger.warning(
                        f"Failed to broadcast conversation update: {e}",
                        exc_info=True,
                    )
            
            return updated_conversation
        except ClientError as e:
            raise RuntimeError(f"Failed to update conversation: {e}") from e

    async def list_conversations(
        self,
        agent_id: Optional[str] = None,
        status: Optional[ConversationStatus] = None,
        marketing_status: Optional[str] = None,
        limit: int = 100,
    ) -> list[Conversation]:
        """List conversations with optional filters."""
        # For MVP, using scan (not efficient for large datasets)
        # In production, use GSI for agent_id and status
        filter_expression = None
        expression_attribute_values = {}
        expression_attribute_names = {}

        if agent_id:
            filter_expression = "agent_id = :agent_id"
            expression_attribute_values[":agent_id"] = agent_id

        if status:
            # Use ExpressionAttributeNames for reserved keywords like "status"
            status_filter = "#status = :status"
            expression_attribute_names["#status"] = "status"
            if filter_expression:
                filter_expression += " AND " + status_filter
            else:
                filter_expression = status_filter
            expression_attribute_values[":status"] = status.value

        if marketing_status:
            marketing_status_filter = "marketing_status = :marketing_status"
            if filter_expression:
                filter_expression += " AND " + marketing_status_filter
            else:
                filter_expression = marketing_status_filter
            expression_attribute_values[":marketing_status"] = marketing_status

        scan_kwargs = {"Limit": limit}
        if filter_expression:
            scan_kwargs["FilterExpression"] = filter_expression
            scan_kwargs["ExpressionAttributeValues"] = expression_attribute_values
            # Only include ExpressionAttributeNames if it's not empty
            # DynamoDB doesn't accept empty ExpressionAttributeNames
            if expression_attribute_names:
                scan_kwargs["ExpressionAttributeNames"] = expression_attribute_names

        response = self.tables["conversations"].scan(**scan_kwargs)
        items = response.get("Items", [])
        # Ensure marketing_status defaults to NEW for existing conversations
        for item in items:
            if "marketing_status" not in item or item["marketing_status"] is None:
                item["marketing_status"] = MarketingStatus.NEW.value
        return [Conversation(**item) for item in items]

    # Message operations
    async def create_message(self, message: Message) -> Message:
        """Create a new message."""
        item = message.model_dump(exclude_none=True)
        # Convert datetime objects to ISO format strings for DynamoDB
        if "timestamp" in item and isinstance(item["timestamp"], datetime):
            item["timestamp"] = to_utc_iso_string(item["timestamp"])
        item["ttl"] = self._calculate_ttl(message.timestamp)

        self.tables["messages"].put_item(Item=item)
        return message

    async def get_message(self, conversation_id: str, message_id: str) -> Optional[Message]:
        """Get message by conversation ID and message ID."""
        response = self.tables["messages"].get_item(
            Key={
                "conversation_id": conversation_id,
                "message_id": message_id,
            }
        )
        item = response.get("Item")
        if not item:
            return None
        return Message(**item)

    async def list_messages(
        self,
        conversation_id: str,
        limit: int = 100,
        reverse: bool = True,
    ) -> list[Message]:
        """List messages for a conversation."""
        # Use query on the primary key (conversation_id is the partition key)
        # Since conversation_id is the partition key, we can query directly without GSI
        response = self.tables["messages"].query(
            KeyConditionExpression="conversation_id = :conv_id",
            ExpressionAttributeValues={":conv_id": conversation_id},
            Limit=limit,
            ScanIndexForward=not reverse,  # False = descending (newest first), True = ascending
        )
        items = response.get("Items", [])
        
        # Парсим timestamp из строки перед созданием Message объектов
        # Pydantic может не парсить ISO строки автоматически из DynamoDB
        for item in items:
            if "timestamp" in item and isinstance(item["timestamp"], str):
                try:
                    # Парсим ISO строку в datetime как UTC
                    item["timestamp"] = parse_utc_datetime(item["timestamp"])
                except (ValueError, AttributeError) as e:
                    logger.warning(f"Failed to parse timestamp '{item.get('timestamp')}': {e}, keeping as string")

        result = [Message(**item) for item in items]
        
        # Сортировка по timestamp для правильного хронологического порядка
        # Обрабатываем случаи, когда timestamp может быть строкой или datetime
        def get_timestamp(msg: Message) -> datetime:
            """Extract timestamp from message, handling both datetime and string formats."""
            ts = msg.timestamp
            if isinstance(ts, datetime):
                return ts
            elif isinstance(ts, str):
                try:
                    # Парсим ISO строку как UTC
                    return parse_utc_datetime(ts)
                except (ValueError, AttributeError):
                    # Fallback to current time if parsing fails
                    logger.warning(f"Failed to parse timestamp '{ts}', using current time")
                    return utc_now()
            else:
                # Fallback for any other type
                logger.warning(f"Unexpected timestamp type: {type(ts)}, using current time")
                return utc_now()
        
        # Сортировка: старые → новые (хронологический порядок)
        result.sort(key=get_timestamp)
        
        # Если reverse=True был запрошен, разворачиваем список после сортировки
        if reverse:
            result.reverse()
        
        # #region agent log
        try:
            import json
            import os
            log_path = '/Users/mikitavalkunovich/Desktop/Doctor Agent/doctor-agent/.cursor/debug.log'
            if os.path.exists(os.path.dirname(log_path)) or os.path.exists('/Users/mikitavalkunovich'):
                with open(log_path, 'a') as f:
                    log_data = {
                        "sessionId":"debug-session",
                        "runId":"run1",
                        "hypothesisId":"A,E",
                        "location":"dynamodb.py:345",
                        "message":"list_messages exit",
                        "data":{
                            "conversation_id":conversation_id,
                            "method":method_used,
                            "count":len(result),
                            "message_ids":[m.message_id for m in result[:5]] if result else []
                        },
                        "timestamp":int(__import__('time').time()*1000)
                    }
                    f.write(json.dumps(log_data) + '\n')
        except Exception:
            # Don't fail if logging fails
            pass
        # #endregion
        return result

    # Agent operations
    async def create_agent(self, agent_id: str, config: dict[str, Any]) -> dict[str, Any]:
        """Create or update agent configuration."""
        # Convert float values to Decimal for DynamoDB compatibility
        config_converted = self._convert_floats_to_decimal(config)
        
        item = {
            "agent_id": agent_id,
            "config": config_converted,
            "created_at": to_utc_iso_string(utc_now()),
            "updated_at": to_utc_iso_string(utc_now()),
            "is_active": True,
        }
        self.tables["agents"].put_item(Item=item)
        return item

    async def get_agent(self, agent_id: str) -> Optional[dict[str, Any]]:
        """Get agent configuration."""
        response = self.tables["agents"].get_item(Key={"agent_id": agent_id})
        item = response.get("Item")
        return item

    async def update_agent_status(
        self, 
        agent_id: str, 
        is_active: bool
    ) -> Optional[dict[str, Any]]:
        """Update agent is_active status atomically."""
        try:
            # Use ExpressionAttributeNames for reserved keyword "is_active"
            response = self.tables["agents"].update_item(
                Key={"agent_id": agent_id},
                UpdateExpression="SET #is_active = :active, updated_at = :updated_at",
                ExpressionAttributeNames={
                    "#is_active": "is_active",
                },
                ExpressionAttributeValues={
                    ":active": is_active,
                    ":updated_at": to_utc_iso_string(utc_now()),
                },
                ReturnValues="ALL_NEW",
                ConditionExpression="attribute_exists(agent_id)",
            )
            return response.get("Attributes")
        except ClientError as e:
            if e.response["Error"]["Code"] == "ConditionalCheckFailedException":
                return None  # Agent doesn't exist
            raise RuntimeError(f"Failed to update agent status: {e}") from e

    async def list_agents(self, active_only: bool = True) -> list[dict[str, Any]]:
        """List all agents."""
        if active_only:
            filter_expr, attr_values, attr_names = self._build_filter_expression(
                [("is_active", "=", ":active")],
                {":active": True},
            )
            scan_kwargs = {
                "FilterExpression": filter_expr,
                "ExpressionAttributeValues": attr_values,
            }
            # Only include ExpressionAttributeNames if it's not empty
            # DynamoDB doesn't accept empty ExpressionAttributeNames
            if attr_names:
                scan_kwargs["ExpressionAttributeNames"] = attr_names
            response = self.tables["agents"].scan(**scan_kwargs)
        else:
            response = self.tables["agents"].scan()
        return response.get("Items", [])

    # Channel binding operations
    async def create_channel_binding(self, binding: ChannelBinding) -> ChannelBinding:
        """Create a new channel binding."""
        item = binding.model_dump(exclude_none=True)
        # Convert datetime objects to ISO format strings for DynamoDB
        if "created_at" in item and isinstance(item["created_at"], datetime):
            item["created_at"] = to_utc_iso_string(item["created_at"])
        if "updated_at" in item and isinstance(item["updated_at"], datetime):
            item["updated_at"] = to_utc_iso_string(item["updated_at"])
        # Convert enum to string
        if "channel_type" in item:
            item["channel_type"] = get_enum_value(item["channel_type"])

        self.tables["channel_bindings"].put_item(Item=item)
        return binding

    async def get_channel_binding(self, binding_id: str) -> Optional[ChannelBinding]:
        """Get channel binding by ID."""
        response = self.tables["channel_bindings"].get_item(
            Key={"binding_id": binding_id}
        )
        item = response.get("Item")
        if not item:
            return None
        return ChannelBinding(**item)

    async def get_channel_bindings_by_agent(
        self,
        agent_id: str,
        channel_type: Optional[str] = None,
        active_only: bool = True,
    ) -> list[ChannelBinding]:
        """Get channel bindings for an agent."""
        items = []
        
        try:
            # Use GSI if available
            # agent_id-index has agent_id as hash key and channel_type as range key
            key_condition = "agent_id = :agent_id"
            expression_attribute_values = {":agent_id": agent_id}
            expression_attribute_names = {}
            filter_expressions = []
            
            # channel_type is range key in GSI, so it can be in KeyConditionExpression
            if channel_type:
                key_condition += " AND channel_type = :channel_type"
                expression_attribute_values[":channel_type"] = channel_type

            if active_only:
                # Use ExpressionAttributeNames for reserved keyword "is_active"
                expression_attribute_names["#is_active"] = "is_active"
                filter_expressions.append("#is_active = :is_active")
                expression_attribute_values[":is_active"] = True

            query_kwargs = {
                "IndexName": "agent_id-index",
                "KeyConditionExpression": key_condition,
                "ExpressionAttributeValues": expression_attribute_values,
            }
            
            # Only include ExpressionAttributeNames if it's not empty
            # DynamoDB doesn't accept empty ExpressionAttributeNames
            if expression_attribute_names:
                query_kwargs["ExpressionAttributeNames"] = expression_attribute_names
            
            if filter_expressions:
                query_kwargs["FilterExpression"] = " AND ".join(filter_expressions)

            response = self.tables["channel_bindings"].query(**query_kwargs)
            items = response.get("Items", [])
        except ClientError as e:
            # Log error for debugging
            error_code = e.response.get("Error", {}).get("Code", "Unknown")
            error_message = e.response.get("Error", {}).get("Message", str(e))
            logger.warning(
                f"GSI query failed for channel bindings, falling back to scan: {error_code} - {error_message}",
                extra={
                    "agent_id": agent_id,
                    "channel_type": channel_type,
                    "active_only": active_only,
                    "error_code": error_code,
                },
            )
            
            # Fallback to scan if GSI doesn't exist or query fails
            filter_expression = "agent_id = :agent_id"
            expression_attribute_values = {":agent_id": agent_id}
            expression_attribute_names = {}

            if channel_type:
                filter_expression += " AND channel_type = :channel_type"
                expression_attribute_values[":channel_type"] = channel_type

            if active_only:
                # Use ExpressionAttributeNames for reserved keyword "is_active"
                expression_attribute_names["#is_active"] = "is_active"
                filter_expression += " AND #is_active = :active"
                expression_attribute_values[":active"] = True

            scan_kwargs = {
                "FilterExpression": filter_expression,
                "ExpressionAttributeValues": expression_attribute_values,
            }
            
            # Only include ExpressionAttributeNames if it's not empty
            # DynamoDB doesn't accept empty ExpressionAttributeNames
            if expression_attribute_names:
                scan_kwargs["ExpressionAttributeNames"] = expression_attribute_names

            try:
                response = self.tables["channel_bindings"].scan(**scan_kwargs)
                items = response.get("Items", [])
            except ClientError as scan_error:
                logger.error(
                    f"Scan also failed for channel bindings: {scan_error}",
                    extra={
                        "agent_id": agent_id,
                        "error_code": scan_error.response.get("Error", {}).get("Code", "Unknown"),
                    },
                    exc_info=True,
                )
                # Return empty list instead of raising exception
                return []

        # Filter by active_only if needed (when using scan without channel_type filter)
        if active_only and not channel_type:
            items = [item for item in items if item.get("is_active", True)]

        # Normalize items and create ChannelBinding models with error handling
        bindings = []
        for item in items:
            try:
                # Normalize empty strings to None for Optional fields
                if "channel_username" in item and item["channel_username"] == "":
                    item["channel_username"] = None
                
                binding = ChannelBinding(**item)
                bindings.append(binding)
            except Exception as e:
                logger.error(
                    f"Failed to create ChannelBinding from DynamoDB item: {e}",
                    extra={
                        "agent_id": agent_id,
                        "binding_id": item.get("binding_id"),
                        "error_type": type(e).__name__,
                    },
                    exc_info=True,
                )
                # Skip invalid items instead of failing entire request
                continue
        
        return bindings

    async def get_channel_binding_by_account_id(
        self, channel_type: str, account_id: str
    ) -> Optional[ChannelBinding]:
        """Get channel binding by channel account ID."""
        try:
            # Use GSI if available
            response = self.tables["channel_bindings"].query(
                IndexName="channel_account-index",
                KeyConditionExpression="channel_type = :channel_type AND channel_account_id = :account_id",
                ExpressionAttributeValues={
                    ":channel_type": channel_type,
                    ":account_id": account_id,
                },
            )
            items = response.get("Items", [])
            if not items:
                return None
            # Return first active binding if multiple exist
            active_bindings = [item for item in items if item.get("is_active", True)]
            if active_bindings:
                return ChannelBinding(**active_bindings[0])
            # Return first binding if no active ones
            return ChannelBinding(**items[0])
        except ClientError:
            # Fallback to scan if GSI doesn't exist
            response = self.tables["channel_bindings"].scan(
                FilterExpression="channel_type = :channel_type AND channel_account_id = :account_id",
                ExpressionAttributeValues={
                    ":channel_type": channel_type,
                    ":account_id": account_id,
                },
                # Don't pass ExpressionAttributeNames if it's empty - DynamoDB doesn't accept empty dict
            )
            items = response.get("Items", [])
            if not items:
                return None
            # Return first active binding if multiple exist
            active_bindings = [item for item in items if item.get("is_active", True)]
            if active_bindings:
                return ChannelBinding(**active_bindings[0])
            return ChannelBinding(**items[0])

    async def update_channel_binding(
        self, binding_id: str, **kwargs: Any
    ) -> Optional[ChannelBinding]:
        """Update channel binding."""
        update_expression_parts = []
        expression_attribute_values = {}
        expression_attribute_names = {}

        for key, value in kwargs.items():
            if key == "channel_type":
                value = get_enum_value(value)
            
            # Check if key is a reserved keyword and use ExpressionAttributeNames
            if key in self._reserved_keywords:
                attr_placeholder = f"#{key}"
                expression_attribute_names[attr_placeholder] = key
                update_expression_parts.append(f"{attr_placeholder} = :{key}")
            else:
                update_expression_parts.append(f"{key} = :{key}")
            
            expression_attribute_values[f":{key}"] = value

        if not update_expression_parts:
            return await self.get_channel_binding(binding_id)

        update_expression_parts.append("updated_at = :updated_at")
        expression_attribute_values[":updated_at"] = to_utc_iso_string(utc_now())

        try:
            update_kwargs = {
                "Key": {"binding_id": binding_id},
                "UpdateExpression": f"SET {', '.join(update_expression_parts)}",
                "ExpressionAttributeValues": expression_attribute_values,
                "ReturnValues": "ALL_NEW",
            }
            # Only include ExpressionAttributeNames if it's not empty
            # DynamoDB doesn't accept empty ExpressionAttributeNames
            if expression_attribute_names:
                update_kwargs["ExpressionAttributeNames"] = expression_attribute_names
            
            self.tables["channel_bindings"].update_item(**update_kwargs)
            return await self.get_channel_binding(binding_id)
        except ClientError as e:
            logger.error(f"Failed to update channel binding: {e}")
            return None

    async def delete_channel_binding(self, binding_id: str) -> None:
        """Delete channel binding."""
        self.tables["channel_bindings"].delete_item(Key={"binding_id": binding_id})

    # Notification config operations
    async def create_notification_config(
        self, config: "NotificationConfig"
    ) -> "NotificationConfig":
        """Create a new notification config."""
        from app.models.notification_config import NotificationConfig

        item = config.model_dump(exclude_none=True)
        # Convert datetime objects to ISO format strings for DynamoDB
        if "created_at" in item and isinstance(item["created_at"], datetime):
            item["created_at"] = to_utc_iso_string(item["created_at"])
        if "updated_at" in item and isinstance(item["updated_at"], datetime):
            item["updated_at"] = to_utc_iso_string(item["updated_at"])
        # Convert enum to string
        if "notification_type" in item:
            item["notification_type"] = get_enum_value(item["notification_type"])

        self.tables["notification_configs"].put_item(Item=item)
        return config

    async def get_notification_config(
        self, config_id: str
    ) -> Optional["NotificationConfig"]:
        """Get notification config by ID."""
        from app.models.notification_config import NotificationConfig

        try:
            response = self.tables["notification_configs"].get_item(
                Key={"config_id": config_id}
            )
            item = response.get("Item")
            if not item:
                return None
            return NotificationConfig(**item)
        except ClientError as e:
            error_code = e.response.get("Error", {}).get("Code", "")
            if error_code == "ResourceNotFoundException":
                logger.debug("Notification configs table does not exist yet")
                return None
            logger.warning(
                f"Failed to get notification config {config_id}: {error_code} - {e.response.get('Error', {}).get('Message', str(e))}"
            )
            return None

    async def list_notification_configs(
        self, active_only: bool = False
    ) -> list["NotificationConfig"]:
        """List all notification configs."""
        from app.models.notification_config import NotificationConfig

        try:
            if active_only:
                filter_expr, attr_values, attr_names = self._build_filter_expression(
                    [("is_active", "=", ":active")],
                    {":active": True},
                )
                scan_kwargs = {
                    "FilterExpression": filter_expr,
                    "ExpressionAttributeValues": attr_values,
                }
                if attr_names:
                    scan_kwargs["ExpressionAttributeNames"] = attr_names
                response = self.tables["notification_configs"].scan(**scan_kwargs)
            else:
                response = self.tables["notification_configs"].scan()

            items = response.get("Items", [])
            configs = []
            for item in items:
                try:
                    config = NotificationConfig(**item)
                    configs.append(config)
                except Exception as e:
                    logger.error(
                        f"Failed to create NotificationConfig from DynamoDB item: {e}",
                        extra={
                            "config_id": item.get("config_id"),
                            "error_type": type(e).__name__,
                        },
                        exc_info=True,
                    )
                    continue
            return configs
        except ClientError as e:
            error_code = e.response.get("Error", {}).get("Code", "")
            if error_code == "ResourceNotFoundException":
                # Table doesn't exist yet, return empty list
                logger.debug("Notification configs table does not exist yet, returning empty list")
                return []
            # For other errors, log warning and return empty list to not break the main flow
            logger.warning(
                f"Failed to list notification configs: {error_code} - {e.response.get('Error', {}).get('Message', str(e))}",
                exc_info=True
            )
            return []

    async def update_notification_config(
        self, config_id: str, **kwargs: Any
    ) -> Optional["NotificationConfig"]:
        """Update notification config."""
        from app.models.notification_config import NotificationConfig

        update_expression_parts = []
        expression_attribute_values = {}
        expression_attribute_names = {}

        for key, value in kwargs.items():
            if key == "notification_type":
                value = get_enum_value(value)

            # Check if key is a reserved keyword and use ExpressionAttributeNames
            if key in self._reserved_keywords:
                attr_placeholder = f"#{key}"
                expression_attribute_names[attr_placeholder] = key
                update_expression_parts.append(f"{attr_placeholder} = :{key}")
            else:
                update_expression_parts.append(f"{key} = :{key}")

            expression_attribute_values[f":{key}"] = value

        if not update_expression_parts:
            return await self.get_notification_config(config_id)

        update_expression_parts.append("updated_at = :updated_at")
        expression_attribute_values[":updated_at"] = to_utc_iso_string(utc_now())

        try:
            update_kwargs = {
                "Key": {"config_id": config_id},
                "UpdateExpression": f"SET {', '.join(update_expression_parts)}",
                "ExpressionAttributeValues": expression_attribute_values,
                "ReturnValues": "ALL_NEW",
            }
            # Only include ExpressionAttributeNames if it's not empty
            if expression_attribute_names:
                update_kwargs["ExpressionAttributeNames"] = expression_attribute_names

            self.tables["notification_configs"].update_item(**update_kwargs)
            return await self.get_notification_config(config_id)
        except ClientError as e:
            logger.error(f"Failed to update notification config: {e}", exc_info=True)
            return None

    async def delete_notification_config(self, config_id: str) -> None:
        """Delete notification config."""
        try:
            self.tables["notification_configs"].delete_item(Key={"config_id": config_id})
        except ClientError as e:
            error_code = e.response.get("Error", {}).get("Code", "")
            if error_code == "ResourceNotFoundException":
                logger.debug("Notification configs table does not exist yet, skipping deletion")
                return
            logger.warning(
                f"Failed to delete notification config {config_id}: {error_code} - {e.response.get('Error', {}).get('Message', str(e))}"
            )
            # Don't raise exception, just log warning

    # Audit log operations
    async def create_audit_log(
        self,
        admin_id: str,
        action: str,
        resource_type: str,
        resource_id: str,
        metadata: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        """Create audit log entry."""
        log_id = f"{resource_type}_{resource_id}_{int(time.time())}"
        item = {
            "log_id": log_id,
            "admin_id": admin_id,
            "action": action,
            "resource_type": resource_type,
            "resource_id": resource_id,
            "timestamp": to_utc_iso_string(utc_now()),
            "metadata": metadata or {},
        }
        self.tables["audit_logs"].put_item(Item=item)
        return item

    async def list_audit_logs(
        self,
        admin_id: Optional[str] = None,
        resource_type: Optional[str] = None,
        action: Optional[str] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        sort_desc: bool = True,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """List audit logs with filtering and sorting."""
        filter_expression = None
        expression_attribute_values = {}

        if admin_id:
            filter_expression = "admin_id = :admin_id"
            expression_attribute_values[":admin_id"] = admin_id

        if resource_type:
            resource_filter = "resource_type = :resource_type"
            if filter_expression:
                filter_expression += " AND " + resource_filter
            else:
                filter_expression = resource_filter
            expression_attribute_values[":resource_type"] = resource_type

        if action:
            action_filter = "action = :action"
            if filter_expression:
                filter_expression += " AND " + action_filter
            else:
                filter_expression = action_filter
            expression_attribute_values[":action"] = action

        # Note: Date filtering is done client-side after fetching
        # because DynamoDB FilterExpression string comparison may not work reliably for ISO dates
        scan_kwargs: dict[str, Any] = {"Limit": min(limit * 2, 2000)}  # Fetch more to account for date filtering, but cap at 2000
        if filter_expression:
            scan_kwargs["FilterExpression"] = filter_expression
            scan_kwargs["ExpressionAttributeValues"] = expression_attribute_values

        items: list[dict[str, Any]] = []
        try:
            response = self.tables["audit_logs"].scan(**scan_kwargs)
            items = response.get("Items", [])
            if items is None:
                items = []
        except ClientError as e:
            error_code = e.response.get("Error", {}).get("Code", "Unknown")
            error_message = e.response.get("Error", {}).get("Message", str(e))
            logger.error(
                f"Failed to scan audit logs: {error_code} - {error_message}",
                exc_info=True,
                extra={
                    "error_code": error_code,
                    "has_filter": bool(filter_expression),
                    "limit": limit,
                },
            )
            # Handle specific error cases
            if error_code == "ResourceNotFoundException":
                logger.warning("Audit logs table does not exist, returning empty list")
                return []
            elif error_code == "AccessDeniedException":
                logger.error("Access denied to audit logs table")
                return []
            elif error_code == "ValidationException":
                logger.error(f"Validation error in audit logs scan: {error_message}")
                # Try without filters if validation error
                if filter_expression:
                    # Will be handled in fallback below
                    pass
                else:
                    return []
            # Fallback: try without filters if filter expression fails
            if filter_expression:
                try:
                    logger.info("Retrying audit logs scan without FilterExpression")
                    response = self.tables["audit_logs"].scan(Limit=min(limit * 2, 2000))
                    items = response.get("Items", [])
                    if items is None:
                        items = []
                    # Apply filters client-side
                    if admin_id:
                        items = [item for item in items if item.get("admin_id") == admin_id]
                    if resource_type:
                        items = [item for item in items if item.get("resource_type") == resource_type]
                    if action:
                        items = [item for item in items if item.get("action") == action]
                except ClientError as e2:
                    error_code_2 = e2.response.get("Error", {}).get("Code", "Unknown")
                    error_message_2 = e2.response.get("Error", {}).get("Message", str(e2))
                    logger.error(
                        f"Failed to scan audit logs even without filters: {error_code_2} - {error_message_2}",
                        exc_info=True,
                    )
                    return []
            else:
                logger.error("No filter expression but scan still failed, returning empty list")
                return []
        except Exception as e:
            logger.error(f"Unexpected error scanning audit logs: {e}", exc_info=True)
            return []
        
        # Filter by date range client-side
        from datetime import timezone
        
        def get_timestamp(item: dict[str, Any]) -> datetime:
            """Extract timestamp from audit log item."""
            ts_str = item.get("timestamp", "")
            if isinstance(ts_str, str):
                try:
                    # Парсим ISO строку как UTC
                    return parse_utc_datetime(ts_str)
                except (ValueError, AttributeError):
                    return datetime.min.replace(tzinfo=timezone.utc)
            return datetime.min.replace(tzinfo=timezone.utc)
        
        # Ensure items is a list
        if not isinstance(items, list):
            logger.warning(f"Items is not a list: {type(items)}, returning empty list")
            return []
        
        # Normalize date filters to timezone-aware (defensive programming)
        normalized_start_date = None
        normalized_end_date = None
        if start_date:
            if start_date.tzinfo is None:
                normalized_start_date = start_date.replace(tzinfo=timezone.utc)
            else:
                normalized_start_date = start_date
        if end_date:
            if end_date.tzinfo is None:
                normalized_end_date = end_date.replace(tzinfo=timezone.utc)
            else:
                normalized_end_date = end_date
        
        # Apply date filters
        if normalized_start_date or normalized_end_date:
            filtered_items = []
            for item in items:
                if not isinstance(item, dict):
                    continue
                item_timestamp = get_timestamp(item)
                # Ensure item_timestamp is timezone-aware
                if item_timestamp.tzinfo is None:
                    item_timestamp = item_timestamp.replace(tzinfo=timezone.utc)
                if normalized_start_date and item_timestamp < normalized_start_date:
                    continue
                if normalized_end_date and item_timestamp > normalized_end_date:
                    continue
                filtered_items.append(item)
            items = filtered_items
        
        # Sort by timestamp (only if we have items)
        if items:
            try:
                items.sort(key=get_timestamp, reverse=sort_desc)
            except Exception as e:
                logger.error(f"Failed to sort audit logs: {e}", exc_info=True)
                # Return unsorted if sorting fails
                pass
        
        # Apply limit after filtering
        return items[:limit]

    # Instagram profile operations
    async def create_or_update_instagram_profile(
        self, profile: InstagramUserProfile
    ) -> InstagramUserProfile:
        """Create or update Instagram user profile."""
        item = profile.model_dump(exclude_none=True)
        # Convert datetime objects to ISO format strings for DynamoDB
        if "updated_at" in item and isinstance(item["updated_at"], datetime):
            item["updated_at"] = to_utc_iso_string(item["updated_at"])
        # Ensure TTL is set
        if "ttl" not in item or not item["ttl"]:
            item["ttl"] = self._calculate_profile_ttl(profile.updated_at)

        self.tables["instagram_profiles"].put_item(Item=item)
        logger.info(f"Created/updated Instagram profile for user {profile.external_user_id}")
        return profile

    async def get_instagram_profile(
        self, external_user_id: str
    ) -> Optional[InstagramUserProfile]:
        """Get Instagram user profile by external_user_id."""
        try:
            response = self.tables["instagram_profiles"].get_item(
                Key={"external_user_id": external_user_id}
            )
            item = response.get("Item")
            if not item:
                return None

            # Parse datetime from ISO string
            if "updated_at" in item and isinstance(item["updated_at"], str):
                try:
                    item["updated_at"] = parse_utc_datetime(item["updated_at"])
                except (ValueError, AttributeError) as e:
                    logger.warning(f"Failed to parse updated_at for profile {external_user_id}: {e}, using current time")
                    item["updated_at"] = utc_now()

            return InstagramUserProfile(**item)
        except Exception as e:
            logger.error(f"Failed to get Instagram profile for {external_user_id}: {e}")
            return None


@lru_cache()
def get_dynamodb_client() -> DynamoDBClient:
    """Get cached DynamoDB client instance."""
    settings = get_settings()
    return DynamoDBClient(settings)




