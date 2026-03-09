"""PostgreSQL-based RAG client (JSONB embeddings, cosine similarity in Python)."""

import json
import logging
import math
from functools import lru_cache
from typing import Any, Optional
from uuid import UUID

from app.config import Settings, get_settings

from app.storage.postgres import get_pool

logger = logging.getLogger(__name__)


def cosine_similarity(vec1: list[float], vec2: list[float]) -> float:
    """Compute cosine similarity between two vectors."""
    if len(vec1) != len(vec2):
        logger.warning(f"Vector length mismatch: {len(vec1)} vs {len(vec2)}")
        return 0.0
    dot = sum(a * b for a, b in zip(vec1, vec2))
    m1 = math.sqrt(sum(a * a for a in vec1))
    m2 = math.sqrt(sum(a * a for a in vec2))
    if m1 == 0 or m2 == 0:
        return 0.0
    return dot / (m1 * m2)


class PostgresRAGClient:
    """PostgreSQL RAG client with JSONB embeddings."""

    def __init__(self, settings: Settings):
        self.settings = settings

    async def connect(self) -> "PostgresRAGClient":
        return self

    async def create_index(
        self,
        index_name: str,
        vector_dimension: int = 1536,
        shards: int = 1,
        replicas: int = 0,
    ) -> bool:
        logger.info(f"Index creation requested for {index_name} (table already exists)")
        return True

    async def index_document(
        self,
        index_name: str,
        agent_id: str,
        document_id: str,
        title: str,
        content: str,
        embedding: list[float],
        folder_id: Optional[UUID] = None,
        file_type: str = "text",
        file_url: Optional[str] = None,
        original_filename: Optional[str] = None,
        file_size: Optional[int] = None,
    ) -> bool:
        emb_json = json.dumps(embedding)
        meta_json = json.dumps({})
        try:
            pool = await get_pool()
            async with pool.acquire() as conn:
                await conn.execute(
                    """
                    INSERT INTO rag_documents (
                        agent_id, document_id, title, content, embedding, metadata,
                        folder_id, file_type, file_url, original_filename, file_size
                    )
                    VALUES ($1, $2, $3, $4, $5::jsonb, $6::jsonb, $7, $8, $9, $10, $11)
                    ON CONFLICT (agent_id, document_id) DO UPDATE SET
                        title = EXCLUDED.title, content = EXCLUDED.content,
                        embedding = EXCLUDED.embedding, metadata = EXCLUDED.metadata,
                        folder_id = EXCLUDED.folder_id, file_type = EXCLUDED.file_type,
                        file_url = EXCLUDED.file_url, original_filename = EXCLUDED.original_filename,
                        file_size = EXCLUDED.file_size, updated_at = NOW()
                    """,
                    agent_id,
                    document_id,
                    title,
                    content,
                    emb_json,
                    meta_json,
                    folder_id,
                    file_type,
                    file_url,
                    original_filename,
                    file_size,
                )
            return True
        except Exception as e:
            logger.error(f"Failed to index document {document_id}: {e}", exc_info=True)
            return False

    async def bulk_index_documents(
        self,
        index_name: str,
        documents: list[dict[str, Any]],
    ) -> tuple[int, int]:
        success_count = 0
        failed_count = 0
        pool = await get_pool()
        async with pool.acquire() as conn:
            async with conn.transaction():
                for doc in documents:
                    try:
                        emb = doc.get("embedding", [])
                        emb_json = json.dumps(emb)
                        meta_json = json.dumps(doc.get("metadata", {}))
                        await conn.execute(
                            """
                            INSERT INTO rag_documents (agent_id, document_id, title, content, embedding, metadata)
                            VALUES ($1, $2, $3, $4, $5::jsonb, $6::jsonb)
                            ON CONFLICT (agent_id, document_id) DO UPDATE SET
                                title = EXCLUDED.title, content = EXCLUDED.content,
                                embedding = EXCLUDED.embedding, metadata = EXCLUDED.metadata
                            """,
                            doc["agent_id"],
                            doc["document_id"],
                            doc.get("title", ""),
                            doc.get("content", ""),
                            emb_json,
                            meta_json,
                        )
                        success_count += 1
                    except Exception as e:
                        logger.error(f"Failed to index document {doc.get('document_id')}: {e}", exc_info=True)
                        failed_count += 1
        return success_count, failed_count

    async def search(
        self,
        index_name: str,
        query_embedding: list[float],
        agent_id: str,
        top_k: int = 6,
        score_threshold: float = 0.2,
    ) -> list[dict[str, Any]]:
        try:
            pool = await get_pool()
            async with pool.acquire() as conn:
                rows = await conn.fetch(
                    """SELECT agent_id, document_id, title, content, embedding,
                              file_url, file_type
                       FROM rag_documents WHERE agent_id = $1""",
                    agent_id,
                )
            results = []
            for row in rows:
                try:
                    emb_raw = row.get("embedding")
                    if isinstance(emb_raw, str):
                        emb = json.loads(emb_raw)
                    elif isinstance(emb_raw, list):
                        emb = emb_raw
                    else:
                        emb = []
                    if not emb:
                        continue
                    sim = cosine_similarity(query_embedding, emb)
                    if sim >= score_threshold:
                        r = {
                            "document_id": row["document_id"],
                            "title": row.get("title", ""),
                            "content": row.get("content", ""),
                            "score": sim,
                        }
                        if row.get("file_url"):
                            r["file_url"] = row["file_url"]
                            r["file_type"] = row.get("file_type") or "text"
                        results.append(r)
                except (json.JSONDecodeError, ValueError, TypeError) as e:
                    logger.warning(f"Error processing document {row.get('document_id')}: {e}")
                    continue
            results.sort(key=lambda x: x["score"], reverse=True)
            return results[:top_k]
        except Exception as e:
            logger.error(f"Error searching RAG: {e}", exc_info=True)
            return []

    async def get_document(
        self, agent_id: str, document_id: str
    ) -> Optional[dict[str, Any]]:
        """Get a single document by agent_id and document_id."""
        try:
            pool = await get_pool()
            async with pool.acquire() as conn:
                row = await conn.fetchrow(
                    """SELECT agent_id, document_id, title, content, folder_id, file_type,
                              file_url, original_filename, file_size, created_at, updated_at
                       FROM rag_documents WHERE agent_id = $1 AND document_id = $2""",
                    agent_id,
                    document_id,
                )
            return dict(row) if row else None
        except Exception as e:
            logger.error(f"Failed to get document: {e}", exc_info=True)
            return None

    async def list_documents(
        self,
        agent_id: str,
        folder_id: Optional[UUID] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        """List documents for agent, optionally filtered by folder."""
        try:
            pool = await get_pool()
            async with pool.acquire() as conn:
                if folder_id is not None:
                    rows = await conn.fetch(
                        """SELECT agent_id, document_id, title, file_type, file_url,
                                  original_filename, file_size, folder_id, created_at, updated_at
                           FROM rag_documents WHERE agent_id = $1 AND folder_id = $2
                           ORDER BY created_at DESC
                           LIMIT $3 OFFSET $4""",
                        agent_id,
                        folder_id,
                        limit,
                        offset,
                    )
                else:
                    rows = await conn.fetch(
                        """SELECT agent_id, document_id, title, file_type, file_url,
                                  original_filename, file_size, folder_id, created_at, updated_at
                           FROM rag_documents WHERE agent_id = $1
                           ORDER BY created_at DESC
                           LIMIT $2 OFFSET $3""",
                        agent_id,
                        limit,
                        offset,
                    )
            return [dict(r) for r in rows]
        except Exception as e:
            logger.error(f"Failed to list documents: {e}", exc_info=True)
            return []

    async def update_document(
        self,
        agent_id: str,
        document_id: str,
        title: Optional[str] = None,
        folder_id: Optional[UUID] = None,
    ) -> bool:
        """Update document title and/or folder."""
        try:
            pool = await get_pool()
            async with pool.acquire() as conn:
                updates = []
                params: list[Any] = []
                i = 1
                if title is not None:
                    updates.append(f"title = ${i}")
                    params.append(title)
                    i += 1
                if folder_id is not None:
                    updates.append(f"folder_id = ${i}")
                    params.append(folder_id)
                    i += 1
                if not updates:
                    return True
                updates.append("updated_at = NOW()")
                params.extend([agent_id, document_id])
                result = await conn.execute(
                    f"""UPDATE rag_documents SET {', '.join(updates)}
                        WHERE agent_id = ${i} AND document_id = ${i + 1}""",
                    *params,
                )
            return result.startswith("UPDATE ") and result != "UPDATE 0"
        except Exception as e:
            logger.error(f"Failed to update document: {e}", exc_info=True)
            return False

    async def update_document_content(
        self, agent_id: str, document_id: str, content: str, embedding: list[float]
    ) -> bool:
        """Update document content and embedding (e.g. after comparative description)."""
        emb_json = json.dumps(embedding)
        try:
            pool = await get_pool()
            async with pool.acquire() as conn:
                await conn.execute(
                    """UPDATE rag_documents SET content = $1, embedding = $2::jsonb, updated_at = NOW()
                       WHERE agent_id = $3 AND document_id = $4""",
                    content,
                    emb_json,
                    agent_id,
                    document_id,
                )
            return True
        except Exception as e:
            logger.error(f"Failed to update document content: {e}", exc_info=True)
            return False

    async def list_image_documents_with_embeddings(
        self, agent_id: str
    ) -> list[dict[str, Any]]:
        """List image documents with content and embedding for similarity detection."""
        try:
            pool = await get_pool()
            async with pool.acquire() as conn:
                rows = await conn.fetch(
                    """SELECT document_id, content, embedding FROM rag_documents
                       WHERE agent_id = $1 AND file_type = 'image'""",
                    agent_id,
                )
            result = []
            for row in rows:
                emb_raw = row.get("embedding")
                if isinstance(emb_raw, str):
                    emb = json.loads(emb_raw)
                elif isinstance(emb_raw, list):
                    emb = emb_raw
                else:
                    emb = []
                result.append({
                    "document_id": row["document_id"],
                    "content": row.get("content", ""),
                    "embedding": emb,
                })
            return result
        except Exception as e:
            logger.error(f"Failed to list image documents: {e}", exc_info=True)
            return []

    async def delete_document(self, agent_id: str, document_id: str) -> bool:
        """Delete a single document."""
        try:
            pool = await get_pool()
            async with pool.acquire() as conn:
                result = await conn.execute(
                    "DELETE FROM rag_documents WHERE agent_id = $1 AND document_id = $2",
                    agent_id,
                    document_id,
                )
            return result == "DELETE 1"
        except Exception as e:
            logger.error(f"Failed to delete document: {e}", exc_info=True)
            return False

    async def delete_documents_by_agent(self, index_name: str, agent_id: str) -> int:
        try:
            pool = await get_pool()
            async with pool.acquire() as conn:
                result = await conn.execute(
                    "DELETE FROM rag_documents WHERE agent_id = $1",
                    agent_id,
                )
            # Parse "DELETE N" from result
            if result and result.startswith("DELETE "):
                return int(result.split()[1])
            return 0
        except Exception as e:
            logger.error(f"Error deleting RAG documents: {e}", exc_info=True)
            return 0

    async def close(self) -> None:
        pass


@lru_cache()
def get_postgres_rag_client() -> PostgresRAGClient:
    settings = get_settings()
    return PostgresRAGClient(settings)
