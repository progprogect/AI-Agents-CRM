"""Shared RAG document indexing pipeline (upload and Cloudinary import)."""

import logging
import uuid
from io import BytesIO
from typing import Any, Optional
from uuid import UUID

from app.chains.rag_chain import RAGChain
from app.config import get_settings
from app.models.agent_config import EmbeddingsConfig
from app.services.image_processor_service import get_image_processor_service
from app.services.llm_factory import get_llm_factory
from app.storage.postgres import fetch_agent_organization_id
from app.storage.postgres_rag import PostgresRAGClient, cosine_similarity
from app.utils.llm_provider import get_rag_embeddings_config
from app.utils.text_chunking import split_text_into_chunks

logger = logging.getLogger(__name__)

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp"}
TEXT_EXTENSIONS = {".txt", ".md", ".json"}
PDF_EXTENSIONS = {".pdf"}


def infer_file_type(filename: str) -> str:
    ext = "." + filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if ext in IMAGE_EXTENSIONS:
        return "image"
    if ext in PDF_EXTENSIONS:
        return "pdf"
    if ext in TEXT_EXTENSIONS:
        return "text"
    return "raw"


async def extract_text_content(
    *,
    file_type: str,
    content: bytes,
    filename: str,
    file_url: str,
    agent_id: str,
    agent_config_dict: dict[str, Any],
) -> str:
    image_processor = get_image_processor_service()
    text_content = ""
    if file_type == "image":
        try:
            text_content = await image_processor.describe_image(
                file_url, agent_id, agent_config_dict
            )
        except Exception as e:
            logger.error(f"Image description failed: {e}", exc_info=True)
            text_content = f"Image: {filename}"
    elif file_type == "pdf":
        try:
            import PyPDF2

            reader = PyPDF2.PdfReader(BytesIO(content))
            parts = []
            for p in reader.pages:
                parts.append(p.extract_text() or "")
            text_content = "\n\n".join(parts).strip() or filename
        except ImportError:
            text_content = filename
        except Exception as e:
            logger.warning(f"PDF extraction failed: {e}")
            text_content = filename
    elif file_type == "text":
        try:
            text_content = content.decode("utf-8", errors="replace")
        except Exception:
            text_content = filename
    else:
        text_content = filename
    return text_content


async def _rebuild_chunks_for_postgres_document(
    agent_id: str,
    document_id: str,
    text_content: str,
    rag_client: PostgresRAGClient,
    embeddings: Any,
    agent_config_dict: dict[str, Any],
) -> None:
    """Embed overlapping chunks for semantic search (Postgres rag_chunks table)."""
    try:
        s = get_settings()
        rag = (agent_config_dict or {}).get("rag") or {}
        ret = rag.get("retrieval") or {}
        chunk_size = int(ret.get("chunk_size_chars", s.rag_chunk_size_chars))
        overlap = int(ret.get("chunk_overlap_chars", s.rag_chunk_overlap_chars))
        chunks = split_text_into_chunks(text_content, chunk_size, overlap)
        if not chunks:
            await rag_client.replace_document_chunks(agent_id, document_id, [])
            return
        rows: list[tuple[int, str, list[float]]] = []
        for idx, ch in enumerate(chunks):
            emb = await embeddings.aembed_query(ch)
            rows.append((idx, ch, emb))
        await rag_client.replace_document_chunks(agent_id, document_id, rows)
    except Exception as e:
        logger.warning(
            "RAG chunk indexing failed for %s (non-fatal): %s",
            document_id,
            e,
            exc_info=True,
        )


async def index_rag_document_core(
    *,
    agent_id: str,
    agent_config_dict: dict[str, Any],
    folder_id: Optional[UUID],
    doc_id: str,
    filename: str,
    content: bytes,
    file_url: str,
    title: Optional[str],
    rag_client: PostgresRAGClient,
) -> dict[str, Any]:
    """Extract text, embed, index, run image similarity updates. Returns response dict fields."""
    file_type = infer_file_type(filename)

    text_content = await extract_text_content(
        file_type=file_type,
        content=content,
        filename=filename,
        file_url=file_url,
        agent_id=agent_id,
        agent_config_dict=agent_config_dict,
    )
    doc_title = title or filename

    llm_factory = get_llm_factory()
    chain = RAGChain(llm_factory, rag_client)
    embeddings_config = (
        get_rag_embeddings_config(agent_config_dict) if agent_config_dict else None
    )
    if embeddings_config is None:
        embeddings_config = EmbeddingsConfig(
            provider="openai", model="text-embedding-3-small", dimensions=1536
        )

    embedding: list[float] = []
    embedding_failed = False
    embeddings = None
    try:
        org_id = await fetch_agent_organization_id(agent_id)
        embeddings = await chain._get_embeddings(embeddings_config, org_id=org_id)
        embedding = await embeddings.aembed_query(text_content)
    except Exception as e:
        embedding_failed = True
        logger.error(
            f"Embedding generation failed for document {doc_id} — saving without embeddings: {e}",
            exc_info=True,
        )

    index_name = f"agent_{agent_id}_documents"
    await rag_client.index_document(
        index_name,
        agent_id,
        doc_id,
        doc_title,
        text_content,
        embedding,
        folder_id=folder_id,
        file_type=file_type,
        file_url=file_url,
        original_filename=filename,
        file_size=len(content),
    )

    if not embedding_failed and embeddings is not None:
        await _rebuild_chunks_for_postgres_document(
            agent_id,
            doc_id,
            text_content,
            rag_client,
            embeddings,
            agent_config_dict,
        )

    image_processor = get_image_processor_service()
    if file_type == "image" and embeddings is not None:
        image_docs = await rag_client.list_image_documents_with_embeddings(agent_id)
        SIM_THRESHOLD = 0.85
        groups: list[list[dict]] = []
        used: set[str] = set()

        for doc in image_docs:
            if doc["document_id"] in used:
                continue
            group = [doc]
            used.add(doc["document_id"])
            for other in image_docs:
                if other["document_id"] in used:
                    continue
                if not other.get("embedding"):
                    continue
                sim = cosine_similarity(doc["embedding"], other["embedding"])
                if sim >= SIM_THRESHOLD:
                    group.append(other)
                    used.add(other["document_id"])
            if len(group) >= 2:
                groups.append(group)

        for group in groups:
            try:
                descriptions = [
                    {"id": d["document_id"], "description": d["content"]} for d in group
                ]
                additions = await image_processor.describe_images_comparatively(
                    descriptions, agent_id, agent_config_dict
                )
                for d in group:
                    add = additions.get(d["document_id"], "")
                    if add:
                        new_content = f"{d['content']} {add}".strip()
                        new_emb = await embeddings.aembed_query(new_content)
                        await rag_client.update_document_content(
                            agent_id, d["document_id"], new_content, new_emb
                        )
                        await _rebuild_chunks_for_postgres_document(
                            agent_id,
                            d["document_id"],
                            new_content,
                            rag_client,
                            embeddings,
                            agent_config_dict,
                        )
            except Exception as e:
                logger.warning(f"Comparative description failed for group: {e}")

    folder_id_str: Optional[str] = str(folder_id) if folder_id else None
    result: dict[str, Any] = {
        "document_id": doc_id,
        "title": doc_title,
        "file_type": file_type,
        "file_url": file_url,
        "original_filename": filename,
        "file_size": len(content),
        "folder_id": folder_id_str,
        "embedding_failed": embedding_failed,
    }
    if embedding_failed:
        result["warning"] = (
            "Document saved, but embedding generation failed. "
            "This file will not appear in semantic search results. "
            "Check your AI provider quota and re-upload to fix."
        )
    return result


def new_rag_document_id() -> str:
    return str(uuid.uuid4())
