"""Redis client wrapper."""

import json
from functools import lru_cache
from typing import Any, Optional

import redis.asyncio as redis

from app.config import Settings, get_settings


class RedisClient:
    """Redis client wrapper."""

    def __init__(self, settings: Settings):
        """Initialize Redis client."""
        self.settings = settings
        self.client: Optional[redis.Redis] = None

    async def connect(self) -> None:
        """Connect to Redis. Prefers REDIS_URL if set (Railway), falls back to individual fields."""
        if self.client is None:
            url = self.settings.redis_url
            if url:
                self.client = redis.from_url(url, decode_responses=True)
            else:
                self.client = redis.Redis(
                    host=self.settings.redis_host,
                    port=self.settings.redis_port,
                    db=self.settings.redis_db,
                    password=self.settings.redis_password,
                    ssl=self.settings.redis_ssl,
                    decode_responses=True,
                )

    async def disconnect(self) -> None:
        """Disconnect from Redis."""
        if self.client:
            await self.client.close()
            self.client = None

    async def get(self, key: str) -> Optional[str]:
        """Get value from Redis."""
        await self.connect()
        if not self.client:
            return None
        return await self.client.get(key)

    async def set(
        self,
        key: str,
        value: str,
        ttl: Optional[int] = None,
    ) -> bool:
        """Set value in Redis."""
        await self.connect()
        if not self.client:
            return False
        if ttl:
            return await self.client.setex(key, ttl, value)
        return await self.client.set(key, value)

    async def delete(self, key: str) -> int:
        """Delete key from Redis."""
        await self.connect()
        if not self.client:
            return 0
        return await self.client.delete(key)

    async def get_json(self, key: str) -> Optional[dict[str, Any]]:
        """Get JSON value from Redis."""
        value = await self.get(key)
        if value is None:
            return None
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return None

    async def set_json(
        self,
        key: str,
        value: dict[str, Any],
        ttl: Optional[int] = None,
    ) -> bool:
        """Set JSON value in Redis."""
        json_value = json.dumps(value)
        return await self.set(key, json_value, ttl)

    async def incr(self, key: str) -> int:
        """Increment integer value of key by 1. Returns new value."""
        await self.connect()
        if not self.client:
            return 0
        return int(await self.client.incr(key))

    async def exists(self, key: str) -> bool:
        """Check if key exists."""
        await self.connect()
        if not self.client:
            return False
        return bool(await self.client.exists(key))

    async def set_conversation_status(
        self, conversation_id: str, status: str, ttl: Optional[int] = None
    ) -> bool:
        """Set conversation status in Redis."""
        key = f"conversation:{conversation_id}:status"
        return await self.set(key, status, ttl)

    async def get_conversation_status(self, conversation_id: str) -> Optional[str]:
        """Get conversation status from Redis."""
        key = f"conversation:{conversation_id}:status"
        return await self.get(key)


@lru_cache()
def get_redis_client() -> RedisClient:
    """Get cached Redis client instance."""
    settings = get_settings()
    return RedisClient(settings)








