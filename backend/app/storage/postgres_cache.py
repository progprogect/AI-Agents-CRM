"""PostgreSQL-based cache client (replacement for PostgreSQL cache)."""

import json
import logging
from datetime import timedelta
from functools import lru_cache
from typing import Any, Optional

from app.config import Settings, get_settings
from app.utils.datetime_utils import utc_now

from app.storage.postgres import get_pool

logger = logging.getLogger(__name__)


class PostgresCacheClient:
    """PostgreSQL cache client with Redis-compatible interface."""

    def __init__(self, settings: Settings):
        self.settings = settings

    async def get(self, key: str) -> Optional[str]:
        pool = await get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT value, expires_at FROM sessions WHERE session_key = $1",
                key,
            )
        if not row:
            return None
        expires_at = row.get("expires_at")
        if expires_at:
            now = int(utc_now().timestamp())
            if now >= int(expires_at):
                await self.delete(key)
                return None
        return row.get("value")

    async def set(
        self,
        key: str,
        value: str,
        ttl: Optional[int] = None,
    ) -> bool:
        expires_at = None
        if ttl:
            expires_at = int((utc_now() + timedelta(seconds=ttl)).timestamp())
        pool = await get_pool()
        async with pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO sessions (session_key, value, expires_at)
                VALUES ($1, $2, $3)
                ON CONFLICT (session_key) DO UPDATE SET value = EXCLUDED.value, expires_at = EXCLUDED.expires_at
                """,
                key,
                value,
                expires_at,
            )
        return True

    async def delete(self, key: str) -> int:
        pool = await get_pool()
        async with pool.acquire() as conn:
            await conn.execute("DELETE FROM sessions WHERE session_key = $1", key)
        return 1

    async def get_json(self, key: str) -> Optional[dict[str, Any]]:
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
        return await self.set(key, json.dumps(value), ttl)

    async def exists(self, key: str) -> bool:
        return await self.get(key) is not None

    async def set_conversation_status(
        self, conversation_id: str, status: str, ttl: Optional[int] = None
    ) -> bool:
        key = f"conversation:{conversation_id}:status"
        return await self.set(key, status, ttl)

    async def get_conversation_status(self, conversation_id: str) -> Optional[str]:
        key = f"conversation:{conversation_id}:status"
        return await self.get(key)


@lru_cache()
def get_postgres_cache_client() -> PostgresCacheClient:
    settings = get_settings()
    return PostgresCacheClient(settings)
