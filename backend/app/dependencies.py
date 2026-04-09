"""Dependency injection for FastAPI.

Storage backend: PostgreSQL (primary) + Redis (cache / debounce).
DynamoDB is NOT supported — see storage/dynamodb.py for the historical reference.
"""

from fastapi import Depends

from app.config import Settings, get_settings
from app.storage.postgres import PostgreSQLClient, get_postgres_client
from app.storage.postgres_cache import PostgresCacheClient, get_postgres_cache_client
from app.storage.postgres_secrets import PostgresSecretsManager, get_postgres_secrets_manager
from app.services.llm_factory import LLMFactory, get_llm_factory
from app.services.moderation_service import ModerationService, get_moderation_service


def get_config() -> Settings:
    """Get application settings."""
    return get_settings()


# Storage dependencies — PostgreSQL only

def get_dynamodb() -> PostgreSQLClient:
    """Get the PostgreSQL database client.

    Named get_dynamodb() for backward compatibility with existing call sites,
    but always returns the PostgreSQL client.  DynamoDB is not supported.
    """
    return get_postgres_client()


def get_cache() -> PostgresCacheClient:
    """Get the PostgreSQL-backed cache client."""
    return get_postgres_cache_client()


def get_secrets() -> PostgresSecretsManager:
    """Get the PostgreSQL-backed secrets manager."""
    return get_postgres_secrets_manager()


# Service dependencies

def get_llm_factory_dep() -> LLMFactory:
    """Get LLM factory."""
    return get_llm_factory()


def get_moderation_service_dep() -> ModerationService:
    """Get moderation service."""
    return get_moderation_service()


# Common dependency combinations
class CommonDependencies:
    """Common dependencies for endpoints."""

    def __init__(
        self,
        config: Settings = Depends(get_config),
        dynamodb: PostgreSQLClient = Depends(get_dynamodb),
        cache: PostgresCacheClient = Depends(get_cache),
    ):
        self.config = config
        self.dynamodb = dynamodb
        self.cache = cache
