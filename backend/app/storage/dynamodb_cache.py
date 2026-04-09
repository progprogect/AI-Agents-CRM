"""DynamoDB-based cache client (replacement for Redis).

NOT SUPPORTED — this backend is not used in production.
The project uses Redis (storage/redis.py) as its cache layer.
This file is kept for reference only and should not be imported in new code.
"""

import asyncio
import json
import logging
from datetime import datetime, timedelta
from functools import lru_cache
from typing import Any, Optional

import boto3
from botocore.exceptions import ClientError

from app.config import Settings, get_settings
from app.utils.datetime_utils import utc_now

logger = logging.getLogger(__name__)


class DynamoDBCacheClient:
    """DynamoDB-based cache client with Redis-compatible interface."""

    def __init__(self, settings: Settings):
        """Initialize DynamoDB cache client."""
        self.settings = settings
        self.dynamodb = boto3.resource(
            "dynamodb",
            region_name=settings.aws_region,
            endpoint_url=settings.dynamodb_endpoint_url,
            aws_access_key_id=settings.aws_access_key_id,
            aws_secret_access_key=settings.aws_secret_access_key,
        )
        self.table_name = "doctor-agent-sessions"
        self.table = self.dynamodb.Table(self.table_name)

    async def connect(self) -> None:
        """Connect to DynamoDB (no-op for DynamoDB, kept for compatibility)."""
        # DynamoDB connection is lazy, no need to connect explicitly
        pass

    async def disconnect(self) -> None:
        """Disconnect from DynamoDB (no-op for DynamoDB, kept for compatibility)."""
        # DynamoDB doesn't require explicit disconnection
        pass

    async def get(self, key: str) -> Optional[str]:
        """Get value from cache."""
        def _get_item():
            return self.table.get_item(Key={"session_key": key})

        try:
            response = await asyncio.to_thread(_get_item)
            if "Item" not in response:
                return None

            item = response["Item"]
            # Check if item has expired (TTL)
            # DynamoDB TTL is handled automatically, but we check manually for immediate consistency
            expires_at = item.get("expires_at")
            if expires_at:
                # Handle both int and Decimal types from DynamoDB
                expires_timestamp = int(float(expires_at))
                current_timestamp = int(utc_now().timestamp())
                if current_timestamp >= expires_timestamp:
                    # Item has expired, delete it
                    await self.delete(key)
                    return None

            return item.get("value")
        except ClientError as e:
            logger.error(f"Error getting cache key {key}: {e}", exc_info=True)
            return None
        except Exception as e:
            logger.error(f"Unexpected error getting cache key {key}: {e}", exc_info=True)
            return None

    async def set(
        self,
        key: str,
        value: str,
        ttl: Optional[int] = None,
    ) -> bool:
        """Set value in cache with optional TTL."""
        def _put_item():
            item = {
                "session_key": key,
                "value": value,
            }

            # Calculate expires_at if TTL is provided
            if ttl:
                expires_at = int((utc_now() + timedelta(seconds=ttl)).timestamp())
                item["expires_at"] = expires_at

            self.table.put_item(Item=item)
            return True

        try:
            return await asyncio.to_thread(_put_item)
        except ClientError as e:
            logger.error(f"Error setting cache key {key}: {e}", exc_info=True)
            return False
        except Exception as e:
            logger.error(f"Unexpected error setting cache key {key}: {e}", exc_info=True)
            return False

    async def delete(self, key: str) -> int:
        """Delete key from cache."""
        def _delete_item():
            self.table.delete_item(Key={"session_key": key})
            return 1

        try:
            return await asyncio.to_thread(_delete_item)
        except ClientError as e:
            logger.error(f"Error deleting cache key {key}: {e}", exc_info=True)
            return 0
        except Exception as e:
            logger.error(f"Unexpected error deleting cache key {key}: {e}", exc_info=True)
            return 0

    async def get_json(self, key: str) -> Optional[dict[str, Any]]:
        """Get JSON value from cache."""
        value = await self.get(key)
        if value is None:
            return None
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            logger.warning(f"Failed to parse JSON for key {key}")
            return None

    async def set_json(
        self,
        key: str,
        value: dict[str, Any],
        ttl: Optional[int] = None,
    ) -> bool:
        """Set JSON value in cache."""
        json_value = json.dumps(value)
        return await self.set(key, json_value, ttl)

    async def exists(self, key: str) -> bool:
        """Check if key exists."""
        value = await self.get(key)
        return value is not None

    async def set_conversation_status(
        self, conversation_id: str, status: str, ttl: Optional[int] = None
    ) -> bool:
        """Set conversation status (for compatibility with Redis)."""
        key = f"conversation:{conversation_id}:status"
        return await self.set(key, status, ttl)

    async def get_conversation_status(self, conversation_id: str) -> Optional[str]:
        """Get conversation status (for compatibility with Redis)."""
        key = f"conversation:{conversation_id}:status"
        return await self.get(key)


@lru_cache()
def get_dynamodb_cache_client() -> DynamoDBCacheClient:
    """Get cached DynamoDB cache client instance."""
    settings = get_settings()
    return DynamoDBCacheClient(settings)
