"""PostgreSQL-based secrets manager (Fernet encryption)."""

import json
import logging
from datetime import datetime
from functools import lru_cache
from typing import Optional

from cryptography.fernet import Fernet, InvalidToken

from app.config import Settings, get_settings

from app.storage.postgres import get_pool

logger = logging.getLogger(__name__)


def _get_fernet(settings: Settings) -> Fernet:
    key = settings.secret_encryption_key
    if not key:
        raise RuntimeError(
            "SECRET_ENCRYPTION_KEY must be set for PostgreSQL secrets. "
            "Generate with: python -c \"from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())\""
        )
    key = key.strip().strip('"').strip("'")
    if len(key) != 44:  # Fernet key is 44 chars base64
        raise RuntimeError("SECRET_ENCRYPTION_KEY must be a valid Fernet key (44 chars base64)")
    return Fernet(key.encode() if isinstance(key, str) else key)


class PostgresSecretsManager:
    """PostgreSQL secrets manager with Fernet encryption."""

    def __init__(self, settings: Settings):
        self.settings = settings
        self._fernet: Optional[Fernet] = None
        self._cache: dict[str, str] = {}

    def _get_fernet(self) -> Fernet:
        if self._fernet is None:
            self._fernet = _get_fernet(self.settings)
        return self._fernet

    def clear_cache(self, secret_name: Optional[str] = None, json_key: Optional[str] = None) -> None:
        if secret_name:
            keys_to_remove = [k for k in self._cache if k == secret_name or k.startswith(f"{secret_name}:")]
            for k in keys_to_remove:
                self._cache.pop(k, None)
        else:
            self._cache.clear()

    async def get_openai_api_key(self) -> str:
        key = self.settings.openai_api_key
        if not key:
            raise RuntimeError("OPENAI_API_KEY not found in environment")
        key = key.strip().strip('"').strip("'")
        if not key.startswith("sk-"):
            raise ValueError("Invalid OpenAI API key format")
        return key

    async def create_channel_token_secret(
        self,
        binding_id: str,
        channel_type: str,
        access_token: str,
        metadata: dict,
    ) -> str:
        secret_name = f"channel:{channel_type}:{binding_id}:access_token"
        secret_value = json.dumps({"access_token": access_token, **metadata})
        encrypted = self._get_fernet().encrypt(secret_value.encode()).decode()
        pool = await get_pool()
        async with pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO secrets (key, value_encrypted, created_at)
                VALUES ($1, $2, $3)
                ON CONFLICT (key) DO UPDATE SET value_encrypted = EXCLUDED.value_encrypted
                """,
                secret_name,
                encrypted,
                datetime.utcnow(),
            )
        return secret_name

    async def get_channel_token(self, secret_name: str) -> str:
        cache_key = f"{secret_name}:access_token"
        if cache_key in self._cache:
            return self._cache[cache_key]
        pool = await get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT value_encrypted FROM secrets WHERE key = $1",
                secret_name,
            )
        if not row:
            raise ValueError(f"Secret {secret_name} not found")
        try:
            decrypted = self._get_fernet().decrypt(row["value_encrypted"].encode()).decode()
            data = json.loads(decrypted)
            token = data.get("access_token", data.get("value", ""))
            if not token:
                raise ValueError(f"No access_token in secret {secret_name}")
            self._cache[cache_key] = token
            return token
        except InvalidToken:
            raise ValueError(f"Failed to decrypt secret {secret_name}")

    async def create_notification_token_secret(
        self,
        config_id: str,
        bot_token: str,
    ) -> str:
        secret_name = f"notification:{config_id}:bot_token"
        secret_value = json.dumps({"bot_token": bot_token, "created_at": datetime.utcnow().isoformat()})
        encrypted = self._get_fernet().encrypt(secret_value.encode()).decode()
        pool = await get_pool()
        async with pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO secrets (key, value_encrypted, created_at)
                VALUES ($1, $2, $3)
                ON CONFLICT (key) DO UPDATE SET value_encrypted = EXCLUDED.value_encrypted
                """,
                secret_name,
                encrypted,
                datetime.utcnow(),
            )
        return secret_name

    async def get_notification_bot_token(self, secret_name: str) -> str:
        pool = await get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT value_encrypted FROM secrets WHERE key = $1",
                secret_name,
            )
        if not row:
            raise ValueError(f"Secret {secret_name} not found")
        try:
            decrypted = self._get_fernet().decrypt(row["value_encrypted"].encode()).decode()
            data = json.loads(decrypted)
            token = data.get("bot_token", data.get("value", ""))
            if not token:
                raise ValueError(f"No bot_token in secret {secret_name}")
            return token
        except InvalidToken:
            raise ValueError(f"Failed to decrypt secret {secret_name}")

    async def update_notification_token_secret(
        self,
        secret_name: str,
        bot_token: str,
        created_at: Optional[str] = None,
    ) -> None:
        secret_value = json.dumps({"bot_token": bot_token, **({"created_at": created_at} if created_at else {})})
        encrypted = self._get_fernet().encrypt(secret_value.encode()).decode()
        pool = await get_pool()
        async with pool.acquire() as conn:
            await conn.execute(
                "UPDATE secrets SET value_encrypted = $1 WHERE key = $2",
                encrypted,
                secret_name,
            )

    async def update_channel_token(
        self,
        secret_name: str,
        access_token: str,
        metadata: dict,
    ) -> None:
        secret_value = json.dumps({"access_token": access_token, **metadata})
        encrypted = self._get_fernet().encrypt(secret_value.encode()).decode()
        pool = await get_pool()
        async with pool.acquire() as conn:
            await conn.execute(
                "UPDATE secrets SET value_encrypted = $1 WHERE key = $2",
                encrypted,
                secret_name,
            )

    async def delete_channel_token_secret(self, secret_name: str) -> None:
        pool = await get_pool()
        async with pool.acquire() as conn:
            await conn.execute("DELETE FROM secrets WHERE key = $1", secret_name)
        self.clear_cache(secret_name)

    async def delete_notification_token_secret(self, secret_name: str) -> None:
        pool = await get_pool()
        async with pool.acquire() as conn:
            await conn.execute("DELETE FROM secrets WHERE key = $1", secret_name)
        self.clear_cache(secret_name)


@lru_cache()
def get_postgres_secrets_manager() -> PostgresSecretsManager:
    settings = get_settings()
    return PostgresSecretsManager(settings)
