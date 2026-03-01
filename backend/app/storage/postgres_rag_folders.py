"""PostgreSQL storage for RAG folders."""

import logging
from typing import Any, Optional
from uuid import UUID

from app.config import Settings, get_settings
from app.storage.postgres import get_pool

logger = logging.getLogger(__name__)


class PostgresRAGFolders:
    """PostgreSQL RAG folders storage."""

    def __init__(self, settings: Settings):
        self.settings = settings

    async def create_folder(
        self,
        agent_id: str,
        name: str,
        parent_id: Optional[UUID] = None,
    ) -> Optional[dict[str, Any]]:
        """Create a folder. Returns folder dict or None on conflict."""
        try:
            pool = await get_pool()
            async with pool.acquire() as conn:
                row = await conn.fetchrow(
                    """
                    INSERT INTO rag_folders (agent_id, parent_id, name)
                    VALUES ($1, $2, $3)
                    ON CONFLICT (agent_id, parent_id, name) DO NOTHING
                    RETURNING id, agent_id, parent_id, name, created_at, updated_at
                    """,
                    agent_id,
                    parent_id,
                    name,
                )
            if row:
                return dict(row)
            return None
        except Exception as e:
            logger.error(f"Failed to create folder: {e}", exc_info=True)
            raise

    async def list_folders(self, agent_id: str) -> list[dict[str, Any]]:
        """List all folders for agent as flat list (build tree on client if needed)."""
        try:
            pool = await get_pool()
            async with pool.acquire() as conn:
                rows = await conn.fetch(
                    """
                    SELECT id, agent_id, parent_id, name, created_at, updated_at
                    FROM rag_folders
                    WHERE agent_id = $1
                    ORDER BY parent_id NULLS FIRST, name
                    """,
                    agent_id,
                )
            return [dict(r) for r in rows]
        except Exception as e:
            logger.error(f"Failed to list folders: {e}", exc_info=True)
            raise

    async def rename_folder(self, folder_id: UUID, name: str) -> bool:
        """Rename a folder."""
        try:
            pool = await get_pool()
            async with pool.acquire() as conn:
                result = await conn.execute(
                    "UPDATE rag_folders SET name = $1, updated_at = NOW() WHERE id = $2",
                    name,
                    folder_id,
                )
            return result == "UPDATE 1"
        except Exception as e:
            logger.error(f"Failed to rename folder: {e}", exc_info=True)
            raise

    async def delete_folder(self, folder_id: UUID) -> bool:
        """Delete folder (cascade deletes subfolders, documents get folder_id SET NULL)."""
        try:
            pool = await get_pool()
            async with pool.acquire() as conn:
                await conn.execute(
                    "DELETE FROM rag_folders WHERE id = $1",
                    folder_id,
                )
            return True
        except Exception as e:
            logger.error(f"Failed to delete folder: {e}", exc_info=True)
            raise


def get_postgres_rag_folders() -> PostgresRAGFolders:
    """Get PostgresRAGFolders instance."""
    return PostgresRAGFolders(get_settings())
