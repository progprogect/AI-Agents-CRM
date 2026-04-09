"""DynamoDB-based RAG client (replacement for OpenSearch).

NOT SUPPORTED — this backend is not used in production.
The project uses PostgreSQL rag_chunks table (storage/postgres_rag.py) for RAG.
This file is kept for reference only and should not be imported in new code.
"""

import asyncio
import json
import logging
import math
from functools import lru_cache
from typing import Any, Optional

import boto3
from botocore.exceptions import ClientError

from app.config import Settings, get_settings

logger = logging.getLogger(__name__)


def cosine_similarity(vec1: list[float], vec2: list[float]) -> float:
    """Вычисление cosine similarity между двумя векторами."""
    if len(vec1) != len(vec2):
        logger.warning(f"Vector length mismatch: {len(vec1)} vs {len(vec2)}")
        return 0.0
    
    dot_product = sum(a * b for a, b in zip(vec1, vec2))
    magnitude1 = math.sqrt(sum(a * a for a in vec1))
    magnitude2 = math.sqrt(sum(a * a for a in vec2))
    
    if magnitude1 == 0 or magnitude2 == 0:
        return 0.0
    
    return dot_product / (magnitude1 * magnitude2)


class DynamoDBRAGClient:
    """DynamoDB-based RAG client with OpenSearch-compatible interface."""

    def __init__(self, settings: Settings):
        """Initialize DynamoDB RAG client."""
        self.settings = settings
        self.dynamodb = boto3.resource(
            "dynamodb",
            region_name=settings.aws_region,
            endpoint_url=settings.dynamodb_endpoint_url,
            aws_access_key_id=settings.aws_access_key_id,
            aws_secret_access_key=settings.aws_secret_access_key,
        )
        self.table_name = "doctor-agent-rag-documents"
        self.table = self.dynamodb.Table(self.table_name)

    async def connect(self) -> "DynamoDBRAGClient":
        """Connect to DynamoDB (no-op for DynamoDB, kept for compatibility)."""
        # DynamoDB connection is lazy, no need to connect explicitly
        return self

    async def create_index(
        self,
        index_name: str,
        vector_dimension: int = 1536,
        shards: int = 1,
        replicas: int = 0,
    ) -> bool:
        """Create index (no-op for DynamoDB, kept for compatibility)."""
        # DynamoDB table is created via Terraform, this is a no-op
        logger.info(f"Index creation requested for {index_name} (DynamoDB table already exists)")
        return True

    async def index_document(
        self,
        index_name: str,  # Игнорируется
        agent_id: str,
        document_id: str,
        title: str,
        content: str,
        embedding: list[float],
    ) -> bool:
        """Index a document with embedding."""
        def _put_item():
            item = {
                "agent_id": agent_id,
                "document_id": document_id,
                "title": title,
                "content": content,
                "embedding": json.dumps(embedding),  # JSON строка для DynamoDB
                "metadata": json.dumps({}),
            }
            self.table.put_item(Item=item)
            return True

        try:
            return await asyncio.to_thread(_put_item)
        except ClientError as e:
            logger.error(f"Failed to index document {document_id}: {e}", exc_info=True)
            return False
        except Exception as e:
            logger.error(f"Unexpected error indexing document {document_id}: {e}", exc_info=True)
            return False

    async def bulk_index_documents(
        self,
        index_name: str,  # Игнорируется
        documents: list[dict[str, Any]],
    ) -> tuple[int, int]:
        """Bulk индексация документов в DynamoDB."""
        def _bulk_write():
            success_count = 0
            failed_count = 0

            # Batch write для эффективности (максимум 25 items за раз)
            batch_size = 25
            for i in range(0, len(documents), batch_size):
                batch = documents[i:i + batch_size]

                try:
                    with self.table.batch_writer() as writer:
                        for doc in batch:
                            try:
                                item = {
                                    "agent_id": doc["agent_id"],
                                    "document_id": doc["document_id"],
                                    "title": doc.get("title", ""),
                                    "content": doc.get("content", ""),
                                    "embedding": json.dumps(doc.get("embedding", [])),  # JSON строка
                                    "metadata": json.dumps(doc.get("metadata", {})),
                                }
                                writer.put_item(Item=item)
                                success_count += 1
                            except Exception as e:
                                logger.error(
                                    f"Failed to index document {doc.get('document_id')}: {e}",
                                    exc_info=True,
                                )
                                failed_count += 1
                except Exception as e:
                    logger.error(f"Batch write failed: {e}", exc_info=True)
                    failed_count += len(batch)

            return success_count, failed_count

        return await asyncio.to_thread(_bulk_write)

    async def search(
        self,
        index_name: str,  # Игнорируется, используется table_name
        query_embedding: list[float],
        agent_id: str,
        top_k: int = 6,
        score_threshold: float = 0.2,
    ) -> list[dict[str, Any]]:
        """Поиск похожих документов через сканирование DynamoDB."""
        def _query_all_documents():
            """Query всех документов агента с пагинацией."""
            all_documents = []
            last_evaluated_key = None
            
            while True:
                query_params = {
                    "KeyConditionExpression": "agent_id = :agent_id",
                    "ExpressionAttributeValues": {":agent_id": agent_id},
                }
                
                if last_evaluated_key:
                    query_params["ExclusiveStartKey"] = last_evaluated_key
                
                response = self.table.query(**query_params)
                items = response.get("Items", [])
                
                if items:
                    all_documents.extend(items)
                
                last_evaluated_key = response.get("LastEvaluatedKey")
                if not last_evaluated_key:
                    break
            
            return all_documents

        try:
            # Query всех документов агента с пагинацией (выполняем в thread pool для async совместимости)
            documents = await asyncio.to_thread(_query_all_documents)

            # Вычисление similarity для каждого документа
            results = []
            for doc in documents:
                try:
                    embedding_json = doc.get("embedding", "[]")
                    embedding = json.loads(embedding_json) if isinstance(embedding_json, str) else embedding_json
                    
                    if not embedding or len(embedding) == 0:
                        continue
                    
                    similarity = cosine_similarity(query_embedding, embedding)

                    if similarity >= score_threshold:
                        results.append(
                            {
                                "document_id": doc.get("document_id"),
                                "title": doc.get("title", ""),
                                "content": doc.get("content", ""),
                                "score": similarity,
                            }
                        )
                except (json.JSONDecodeError, ValueError, TypeError) as e:
                    logger.warning(f"Error processing document {doc.get('document_id')}: {e}")
                    continue

            # Сортировка по score и возврат top_k
            results.sort(key=lambda x: x["score"], reverse=True)
            return results[:top_k]

        except ClientError as e:
            logger.error(f"Error searching DynamoDB: {e}", exc_info=True)
            return []
        except Exception as e:
            logger.error(f"Unexpected error searching DynamoDB: {e}", exc_info=True)
            return []

    async def delete_documents_by_agent(
        self, index_name: str, agent_id: str
    ) -> int:
        """Удаление всех документов агента."""
        def _delete_documents():
            try:
                deleted_count = 0
                
                # Query всех документов агента с пагинацией
                last_evaluated_key = None
                while True:
                    query_params = {
                        "KeyConditionExpression": "agent_id = :agent_id",
                        "ExpressionAttributeValues": {":agent_id": agent_id},
                        "ProjectionExpression": "document_id",  # Только ключи для удаления
                    }
                    
                    if last_evaluated_key:
                        query_params["ExclusiveStartKey"] = last_evaluated_key
                    
                    response = self.table.query(**query_params)
                    
                    items = response.get("Items", [])
                    if not items:
                        break
                    
                    # Batch delete
                    with self.table.batch_writer() as writer:
                        for item in items:
                            try:
                                writer.delete_item(
                                    Key={
                                        "agent_id": agent_id,
                                        "document_id": item["document_id"],
                                    }
                                )
                                deleted_count += 1
                            except Exception as e:
                                logger.error(
                                    f"Failed to delete document {item.get('document_id')}: {e}",
                                    exc_info=True,
                                )
                    
                    # Проверяем, есть ли еще страницы
                    last_evaluated_key = response.get("LastEvaluatedKey")
                    if not last_evaluated_key:
                        break

                return deleted_count

            except ClientError as e:
                logger.error(f"Error deleting documents for agent {agent_id}: {e}", exc_info=True)
                return 0
            except Exception as e:
                logger.error(f"Unexpected error deleting documents: {e}", exc_info=True)
                return 0

        return await asyncio.to_thread(_delete_documents)

    async def close(self) -> None:
        """Close DynamoDB connection (no-op for DynamoDB, kept for compatibility)."""
        # DynamoDB doesn't require explicit disconnection
        pass


@lru_cache()
def get_dynamodb_rag_client() -> DynamoDBRAGClient:
    """Get cached DynamoDB RAG client instance."""
    settings = get_settings()
    return DynamoDBRAGClient(settings)
