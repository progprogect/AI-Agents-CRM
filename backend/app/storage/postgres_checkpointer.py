"""LangGraph AsyncPostgresSaver singleton for workflow state persistence."""

from __future__ import annotations

import logging
from typing import Optional

logger = logging.getLogger(__name__)

_pool: Optional[object] = None
_checkpointer: Optional[object] = None


async def init_checkpointer(db_url: str) -> object:
    """Initialize AsyncConnectionPool + AsyncPostgresSaver and run setup()."""
    global _pool, _checkpointer

    from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
    from psycopg_pool import AsyncConnectionPool

    _pool = AsyncConnectionPool(
        conninfo=db_url,
        kwargs={"autocommit": True},
        open=False,
    )
    await _pool.open()

    _checkpointer = AsyncPostgresSaver(_pool)
    await _checkpointer.setup()

    logger.info("LangGraph PostgreSQL checkpointer initialised")
    return _checkpointer


async def close_checkpointer() -> None:
    """Close the connection pool on shutdown."""
    global _pool, _checkpointer
    if _pool is not None:
        try:
            await _pool.close()
            logger.info("LangGraph checkpointer pool closed")
        except Exception as exc:
            logger.warning("Error closing checkpointer pool: %s", exc)
    _pool = None
    _checkpointer = None


def get_checkpointer() -> object:
    """Return the shared AsyncPostgresSaver instance (must call init_checkpointer first)."""
    if _checkpointer is None:
        raise RuntimeError(
            "LangGraph checkpointer is not initialised. "
            "Call init_checkpointer() in the application lifespan."
        )
    return _checkpointer
