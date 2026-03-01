"""RAG retrieval chain."""

from typing import Optional

from langchain_openai import OpenAIEmbeddings

from app.config import get_settings
from app.services.llm_factory import LLMFactory
from app.storage.dynamodb_rag import DynamoDBRAGClient
from app.storage.postgres_rag import PostgresRAGClient


class RAGChain:
    """RAG retrieval chain for document search."""

    def __init__(
        self,
        llm_factory: LLMFactory,
        rag_client: DynamoDBRAGClient | PostgresRAGClient,
    ):
        """Initialize RAG chain."""
        self.llm_factory = llm_factory
        self.rag_client = rag_client
        self._embeddings: Optional[OpenAIEmbeddings] = None

    async def _get_embeddings(self, agent_id: Optional[str] = None) -> OpenAIEmbeddings:
        """Get or create embeddings client."""
        if self._embeddings is None:
            client = await self.llm_factory.get_client(agent_id)
            settings = get_settings()
            self._embeddings = OpenAIEmbeddings(
                model=settings.openai_embedding_model,
                openai_api_key=client.api_key,
            )
        return self._embeddings

    async def retrieve(
        self,
        query: str,
        agent_id: str,
        index_name: str,
        top_k: int = 6,
        score_threshold: float = 0.2,
    ) -> list[dict]:
        """Retrieve relevant documents for query."""
        # Generate query embedding
        embeddings = await self._get_embeddings(agent_id)
        query_embedding = await embeddings.aembed_query(query)

        # Search in DynamoDB
        results = await self.rag_client.search(
            index_name=index_name,
            query_embedding=query_embedding,
            agent_id=agent_id,
            top_k=top_k,
            score_threshold=score_threshold,
        )

        return results

    async def get_relevant_context(
        self,
        query: str,
        agent_id: str,
        index_name: str,
        top_k: int = 6,
        score_threshold: float = 0.2,
    ) -> str:
        """Get relevant context as formatted string."""
        results = await self.retrieve(
            query=query,
            agent_id=agent_id,
            index_name=index_name,
            top_k=top_k,
            score_threshold=score_threshold,
        )

        if not results:
            return "No relevant context found."

        context_parts = []
        for i, result in enumerate(results, 1):
            title = result.get("title", "Document")
            content = result.get("content", "")
            part = f"[{i}] {title}\n{content}"
            if result.get("file_url"):
                part += f"\nImage: {result['file_url']}"
            context_parts.append(part)

        return "\n\n".join(context_parts)

