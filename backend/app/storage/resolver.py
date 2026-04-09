"""Resolve storage clients. PostgreSQL is the only supported backend."""

from app.storage.postgres_secrets import get_postgres_secrets_manager


def get_secrets_manager():
    """Get the PostgreSQL-backed secrets manager."""
    return get_postgres_secrets_manager()
