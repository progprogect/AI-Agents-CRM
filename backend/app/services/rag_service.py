"""RAG service for document retrieval."""

import logging
from functools import lru_cache
from typing import Any, Optional, TypedDict

from app.api.exceptions import RAGServiceError
from app.chains.rag_chain import RAGChain
from app.config import get_settings
from app.models.agent_config import AgentConfig
from app.services.llm_factory import LLMFactory, get_llm_factory
from app.storage.dynamodb_rag import DynamoDBRAGClient, get_dynamodb_rag_client
from app.storage.postgres_rag import PostgresRAGClient, get_postgres_rag_client
from app.utils.llm_provider import get_rag_embeddings_config

logger = logging.getLogger(__name__)

# Minimum similarity score to attach media from a RAG document.
# Higher than the general text-context threshold (0.2) so we only
# send images / files when the document is clearly relevant.
MEDIA_SCORE_THRESHOLD = 0.6


class RAGMediaAttachment(TypedDict):
    """A media file found in the RAG knowledge base."""

    url: str
    media_type: str   # "image" | "video" | "audio" | "document"
    title: str
    score: float


def _rag_file_type_to_media_type(file_type: str | None) -> str:
    """Map RAG file_type column value to our channel media_type category."""
    if file_type == "image":
        return "image"
    if file_type == "video":
        return "video"
    if file_type == "audio":
        return "audio"
    return "document"   # pdf, text, raw → document


class RAGService:
    """Service for RAG operations."""

    def __init__(
        self,
        llm_factory: LLMFactory,
        rag_client: DynamoDBRAGClient | PostgresRAGClient,
    ):
        """Initialize RAG service."""
        self.llm_factory = llm_factory
        self.rag_client = rag_client
        self.rag_chain = RAGChain(llm_factory, rag_client)

    async def index_documents(
        self,
        agent_id: str,
        documents: list[dict],
        index_name: Optional[str] = None,
        agent_config: Optional[AgentConfig] = None,
    ) -> tuple[int, int]:
        """Index documents for an agent."""
        try:
            if index_name is None:
                index_name = f"agent_{agent_id}_documents"

            if agent_config:
                embeddings_config = get_rag_embeddings_config(agent_config)
            else:
                from app.models.agent_config import EmbeddingsConfig
                settings = get_settings()
                embeddings_config = EmbeddingsConfig(
                    provider="openai",
                    model=settings.openai_embedding_model,
                    dimensions=1536,
                )

            # Ensure index exists
            await self.rag_client.create_index(
                index_name=index_name,
                vector_dimension=embeddings_config.dimensions,
            )

            embeddings = await self.rag_chain._get_embeddings(embeddings_config)
            indexed_docs = []

            for doc in documents:
                try:
                    document_id = doc.get("id", doc.get("document_id"))
                    title = doc.get("title", "")
                    content = doc.get("content", "")

                    if not content:
                        logger.warning(
                            f"Skipping document {document_id} - empty content",
                            extra={"agent_id": agent_id, "document_id": document_id},
                        )
                        continue

                    # Generate embedding
                    embedding = await embeddings.aembed_query(content)

                    indexed_docs.append({
                        "agent_id": agent_id,
                        "document_id": document_id,
                        "title": title,
                        "content": content,
                        "embedding": embedding,
                    })
                except Exception as e:
                    logger.error(
                        f"Error processing document {doc.get('id', 'unknown')}: {str(e)}",
                        exc_info=True,
                        extra={"agent_id": agent_id, "document_id": doc.get("id")},
                    )
                    # Continue with other documents
                    continue

            if not indexed_docs:
                logger.warning(
                    f"No documents to index for agent {agent_id}",
                    extra={"agent_id": agent_id},
                )
                return 0, len(documents)

            # Bulk index
            success_count, failed_count = await self.rag_client.bulk_index_documents(
                index_name=index_name,
                documents=indexed_docs,
            )

            logger.info(
                f"Indexed {success_count} documents for agent {agent_id}, "
                f"{failed_count} failed",
                extra={"agent_id": agent_id, "success_count": success_count, "failed_count": failed_count},
            )

            return success_count, failed_count
        except Exception as e:
            logger.error(
                f"RAG indexing error for agent {agent_id}: {str(e)}",
                exc_info=True,
                extra={"agent_id": agent_id, "documents_count": len(documents)},
            )
            raise RAGServiceError(
                f"Failed to index documents: {str(e)}",
                agent_id=agent_id,
            )

    async def retrieve_context(
        self,
        query: str,
        agent_id: str,
        index_name: Optional[str] = None,
        agent_config: Optional[AgentConfig] = None,
        top_k: int = 6,
        score_threshold: float = 0.2,
    ) -> list[dict]:
        """Retrieve relevant context for a query."""
        try:
            if index_name is None:
                index_name = f"agent_{agent_id}_documents"

            if agent_config:
                embeddings_config = get_rag_embeddings_config(agent_config)
            else:
                from app.models.agent_config import EmbeddingsConfig
                settings = get_settings()
                embeddings_config = EmbeddingsConfig(
                    provider="openai",
                    model=settings.openai_embedding_model,
                    dimensions=1536,
                )

            results = await self.rag_chain.retrieve(
                query=query,
                agent_id=agent_id,
                index_name=index_name,
                embeddings_config=embeddings_config,
                top_k=top_k,
                score_threshold=score_threshold,
            )

            logger.debug(
                f"Retrieved {len(results)} documents for query",
                extra={"agent_id": agent_id, "query_length": len(query), "results_count": len(results)},
            )

            return results
        except Exception as e:
            logger.error(
                f"RAG retrieval error for agent {agent_id}: {str(e)}",
                exc_info=True,
                extra={"agent_id": agent_id, "query_length": len(query)},
            )
            # Return empty list on error to allow conversation to continue
            return []

    async def get_formatted_context(
        self,
        query: str,
        agent_id: str,
        index_name: Optional[str] = None,
        agent_config: Optional[AgentConfig] = None,
        top_k: int = 6,
        score_threshold: float = 0.2,
    ) -> str:
        """Get formatted context string for LLM prompt."""
        try:
            if index_name is None:
                index_name = f"agent_{agent_id}_documents"

            if agent_config:
                embeddings_config = get_rag_embeddings_config(agent_config)
            else:
                from app.models.agent_config import EmbeddingsConfig
                settings = get_settings()
                embeddings_config = EmbeddingsConfig(
                    provider="openai",
                    model=settings.openai_embedding_model,
                    dimensions=1536,
                )

            context = await self.rag_chain.get_relevant_context(
                query=query,
                agent_id=agent_id,
                index_name=index_name,
                embeddings_config=embeddings_config,
                top_k=top_k,
                score_threshold=score_threshold,
            )

            return context
        except Exception as e:
            logger.error(
                f"RAG context formatting error for agent {agent_id}: {str(e)}",
                exc_info=True,
                extra={"agent_id": agent_id, "query_length": len(query)},
            )
            # Return empty string on error to allow conversation to continue
            return ""

    async def get_context_and_media(
        self,
        query: str,
        agent_id: str,
        index_name: Optional[str] = None,
        agent_config: Optional[AgentConfig] = None,
        top_k: int = 6,
        score_threshold: float = 0.2,
        media_score_threshold: float = MEDIA_SCORE_THRESHOLD,
    ) -> tuple[str, list[RAGMediaAttachment]]:
        """Single retrieval call that returns both the formatted context string
        and a list of media attachments (documents with file_url above the
        media_score_threshold).

        Replaces the separate get_formatted_context() + retrieve_context() pair
        so the vector search is performed only once per agent response.
        """
        if index_name is None:
            index_name = f"agent_{agent_id}_documents"

        if agent_config:
            embeddings_config = get_rag_embeddings_config(agent_config)
        else:
            from app.models.agent_config import EmbeddingsConfig
            settings = get_settings()
            embeddings_config = EmbeddingsConfig(
                provider="openai",
                model=settings.openai_embedding_model,
                dimensions=1536,
            )

        try:
            raw_results = await self.rag_chain.retrieve(
                query=query,
                agent_id=agent_id,
                index_name=index_name,
                embeddings_config=embeddings_config,
                top_k=top_k,
                score_threshold=score_threshold,
            )
        except Exception as e:
            logger.warning(
                f"RAG retrieval error in get_context_and_media for agent {agent_id}: {e}",
                exc_info=True,
                extra={"agent_id": agent_id},
            )
            return "", []

        if not raw_results:
            return "No relevant context found.", []

        # Build context string (identical format to rag_chain.get_relevant_context)
        context_parts: list[str] = []
        for i, result in enumerate(raw_results, 1):
            title = result.get("title", "Document")
            content = result.get("content", "")
            part = f"[{i}] {title}\n{content}"
            if result.get("file_url"):
                part += f"\nImage: {result['file_url']}"
            context_parts.append(part)
        context = "\n\n".join(context_parts)

        # Extract media attachments that clear the higher similarity bar
        media: list[RAGMediaAttachment] = [
            RAGMediaAttachment(
                url=r["file_url"],
                media_type=_rag_file_type_to_media_type(r.get("file_type")),
                title=r.get("title", ""),
                score=r.get("score", 0.0),
            )
            for r in raw_results
            if r.get("file_url") and r.get("score", 0.0) >= media_score_threshold
        ]

        logger.debug(
            "RAG context_and_media: %d docs, %d media attachments (threshold=%.2f)",
            len(raw_results),
            len(media),
            media_score_threshold,
            extra={"agent_id": agent_id},
        )

        return context, media

    async def delete_agent_documents(
        self,
        agent_id: str,
        index_name: Optional[str] = None,
    ) -> int:
        """Delete all documents for an agent."""
        if index_name is None:
            index_name = f"agent_{agent_id}_documents"

        return await self.rag_client.delete_documents_by_agent(
            index_name=index_name,
            agent_id=agent_id,
        )


@lru_cache()
def get_rag_service() -> RAGService:
    """Get cached RAG service instance."""
    llm_factory = get_llm_factory()
    if get_settings().database_backend == "postgres":
        rag_client = get_postgres_rag_client()
    else:
        rag_client = get_dynamodb_rag_client()
    return RAGService(llm_factory, rag_client)

