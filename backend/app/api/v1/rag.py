"""RAG API endpoints - folders and documents management."""

import logging
import uuid
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Body, Depends, File, Form, HTTPException, Query, UploadFile, status

from app.api.auth import require_admin
from app.config import get_settings
from app.dependencies import CommonDependencies
from app.services.storage_service import StorageServiceError, get_storage_service
from app.services.image_processor_service import get_image_processor_service
from app.storage.postgres_rag import PostgresRAGClient, get_postgres_rag_client
from app.storage.postgres_rag_folders import PostgresRAGFolders, get_postgres_rag_folders

logger = logging.getLogger(__name__)

router = APIRouter()

# Max file size 10MB
MAX_FILE_SIZE = 10 * 1024 * 1024
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp"}
TEXT_EXTENSIONS = {".txt", ".md", ".json"}
PDF_EXTENSIONS = {".pdf"}


def _ensure_postgres() -> None:
    """Ensure we're using PostgreSQL backend."""
    if get_settings().database_backend != "postgres":
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail="RAG folders and documents are only supported with PostgreSQL backend",
        )


async def _ensure_agent_exists(deps: CommonDependencies, agent_id: str) -> dict | None:
    """Ensure agent exists. Returns agent dict or None if not found."""
    agent = await deps.dynamodb.get_agent(agent_id)
    if not agent:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Agent '{agent_id}' not found",
        )
    return agent


# --- Folders ---


@router.get("/{agent_id}/rag/folders")
async def list_rag_folders(
    agent_id: str,
    deps: CommonDependencies = Depends(),
    _admin: str = require_admin(),
):
    """List RAG folders for agent (flat list, build tree on client)."""
    _ensure_postgres()
    await _ensure_agent_exists(deps, agent_id)
    folders = get_postgres_rag_folders()
    items = await folders.list_folders(agent_id)
    # Serialize UUIDs
    return [{"id": str(r["id"]), "agent_id": r["agent_id"], "parent_id": str(r["parent_id"]) if r.get("parent_id") else None, "name": r["name"], "created_at": r["created_at"].isoformat() if r.get("created_at") else None, "updated_at": r["updated_at"].isoformat() if r.get("updated_at") else None} for r in items]


@router.post("/{agent_id}/rag/folders", status_code=status.HTTP_201_CREATED)
async def create_rag_folder(
    agent_id: str,
    name: str = Form(...),
    parent_id: Optional[str] = Form(None),
    deps: CommonDependencies = Depends(),
    _admin: str = require_admin(),
):
    """Create RAG folder."""
    _ensure_postgres()
    await _ensure_agent_exists(deps, agent_id)
    pid = UUID(parent_id) if parent_id else None
    folders = get_postgres_rag_folders()
    folder = await folders.create_folder(agent_id, name, pid)
    if not folder:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Folder '{name}' already exists",
        )
    return {
        "id": str(folder["id"]),
        "agent_id": folder["agent_id"],
        "parent_id": str(folder["parent_id"]) if folder.get("parent_id") else None,
        "name": folder["name"],
        "created_at": folder["created_at"].isoformat() if folder.get("created_at") else None,
        "updated_at": folder["updated_at"].isoformat() if folder.get("updated_at") else None,
    }


@router.patch("/{agent_id}/rag/folders/{folder_id}")
async def update_rag_folder(
    agent_id: str,
    folder_id: str,
    name: str = Body(..., embed=True),
    deps: CommonDependencies = Depends(),
    _admin: str = require_admin(),
):
    """Rename RAG folder."""
    _ensure_postgres()
    await _ensure_agent_exists(deps, agent_id)
    try:
        fid = UUID(folder_id)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid folder_id")
    folders = get_postgres_rag_folders()
    ok = await folders.rename_folder(fid, name)
    if not ok:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Folder not found")
    return {"message": "Folder renamed"}


@router.delete("/{agent_id}/rag/folders/{folder_id}")
async def delete_rag_folder(
    agent_id: str,
    folder_id: str,
    deps: CommonDependencies = Depends(),
    _admin: str = require_admin(),
):
    """Delete RAG folder (cascade)."""
    _ensure_postgres()
    await _ensure_agent_exists(deps, agent_id)
    try:
        fid = UUID(folder_id)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid folder_id")
    folders = get_postgres_rag_folders()
    await folders.delete_folder(fid)
    return {"message": "Folder deleted"}


# --- Documents ---


@router.get("/{agent_id}/rag/documents")
async def list_rag_documents(
    agent_id: str,
    folder_id: Optional[str] = Query(None),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    deps: CommonDependencies = Depends(),
    _admin: str = require_admin(),
):
    """List RAG documents for agent."""
    _ensure_postgres()
    await _ensure_agent_exists(deps, agent_id)
    fid = UUID(folder_id) if folder_id else None
    rag = get_postgres_rag_client()
    items = await rag.list_documents(agent_id, fid, limit, offset)
    return [
        {
            "document_id": r["document_id"],
            "title": r.get("title", ""),
            "file_type": r.get("file_type", "text"),
            "file_url": r.get("file_url"),
            "original_filename": r.get("original_filename"),
            "file_size": r.get("file_size"),
            "folder_id": str(r["folder_id"]) if r.get("folder_id") else None,
            "created_at": r["created_at"].isoformat() if r.get("created_at") else None,
            "updated_at": r["updated_at"].isoformat() if r.get("updated_at") else None,
        }
        for r in items
    ]


@router.post("/{agent_id}/rag/documents", status_code=status.HTTP_201_CREATED)
async def upload_rag_document(
    agent_id: str,
    file: UploadFile = File(...),
    folder_id: Optional[str] = Form(None),
    title: Optional[str] = Form(None),
    deps: CommonDependencies = Depends(),
    _admin: str = require_admin(),
):
    """Upload RAG document (file → Cloudinary, process, index)."""
    _ensure_postgres()
    agent = await _ensure_agent_exists(deps, agent_id)
    agent_config_dict = agent.get("config", {}) if agent else {}

    content = await file.read()
    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File too large (max {MAX_FILE_SIZE // (1024*1024)}MB)",
        )

    filename = file.filename or "unnamed"
    ext = "." + filename.rsplit(".", 1)[-1].lower() if "." in filename else ""

    # Determine file type
    if ext in IMAGE_EXTENSIONS:
        file_type = "image"
    elif ext in PDF_EXTENSIONS:
        file_type = "pdf"
    elif ext in TEXT_EXTENSIONS:
        file_type = "text"
    else:
        file_type = "raw"

    doc_id = str(uuid.uuid4())
    fid = UUID(folder_id) if folder_id else None

    folder_path = ""
    storage_svc = get_storage_service()
    image_processor = get_image_processor_service()
    rag_client = get_postgres_rag_client()

    try:
        file_url = storage_svc.upload_file(
            content, filename, agent_id, folder_path, doc_id
        )
    except StorageServiceError as e:
        logger.warning(f"Storage service not configured or upload failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="File upload service is not configured",
        ) from e

    # Extract content by type
    text_content = ""
    if file_type == "image":
        try:
            text_content = await image_processor.describe_image(file_url, agent_id, agent_config_dict)
        except Exception as e:
            logger.error(f"Image description failed: {e}", exc_info=True)
            text_content = f"Image: {filename}"
    elif file_type == "pdf":
        try:
            import PyPDF2
            from io import BytesIO
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

    doc_title = title or filename

    # Get embeddings and index
    from app.chains.rag_chain import RAGChain
    from app.services.llm_factory import get_llm_factory
    from app.utils.llm_provider import get_rag_embeddings_config

    llm_factory = get_llm_factory()
    chain = RAGChain(llm_factory, rag_client)
    embeddings_config = get_rag_embeddings_config(agent_config_dict) if agent_config_dict else None
    if embeddings_config is None:
        from app.models.agent_config import EmbeddingsConfig
        embeddings_config = EmbeddingsConfig(provider="openai", model="text-embedding-3-small", dimensions=1536)

    embedding: list[float] = []
    embedding_failed = False
    try:
        embeddings = await chain._get_embeddings(embeddings_config)
        embedding = await embeddings.aembed_query(text_content)
    except Exception as e:
        # Graceful degradation: save document without vector embeddings.
        # It will appear in the UI but won't be found via semantic search.
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
        folder_id=fid,
        file_type=file_type,
        file_url=file_url,
        original_filename=filename,
        file_size=len(content),
    )

    # Similarity detection for images: find similar, run comparative, update
    if file_type == "image":
        from app.storage.postgres_rag import cosine_similarity

        image_docs = await rag_client.list_image_documents_with_embeddings(agent_id)
        # Build similarity groups (threshold 0.85)
        SIM_THRESHOLD = 0.85
        groups: list[list[dict]] = []
        used = set()

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
                descriptions = [{"id": d["document_id"], "description": d["content"]} for d in group]
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
            except Exception as e:
                logger.warning(f"Comparative description failed for group: {e}")

    response = {
        "document_id": doc_id,
        "title": doc_title,
        "file_type": file_type,
        "file_url": file_url,
        "original_filename": filename,
        "file_size": len(content),
        "folder_id": folder_id,
    }
    if embedding_failed:
        response["warning"] = (
            "Document saved, but embedding generation failed. "
            "This file will not appear in semantic search results. "
            "Check your AI provider quota and re-upload to fix."
        )
    return response


@router.patch("/{agent_id}/rag/documents/{document_id}")
async def update_rag_document(
    agent_id: str,
    document_id: str,
    title: Optional[str] = Body(None, embed=True),
    folder_id: Optional[str] = Body(None, embed=True),
    deps: CommonDependencies = Depends(),
    _admin: str = require_admin(),
):
    """Update RAG document (rename, move)."""
    _ensure_postgres()
    await _ensure_agent_exists(deps, agent_id)
    fid = UUID(folder_id) if folder_id else None
    rag = get_postgres_rag_client()
    ok = await rag.update_document(agent_id, document_id, title=title, folder_id=fid)
    if not ok:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")
    return {"message": "Document updated"}


@router.delete("/{agent_id}/rag/documents/{document_id}")
async def delete_rag_document(
    agent_id: str,
    document_id: str,
    deps: CommonDependencies = Depends(),
    _admin: str = require_admin(),
):
    """Delete RAG document (and Cloudinary file if applicable)."""
    _ensure_postgres()
    await _ensure_agent_exists(deps, agent_id)
    rag = get_postgres_rag_client()
    doc = await rag.get_document(agent_id, document_id)
    if not doc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")
    # Delete from storage if we have a file_url
    if doc.get("file_url"):
        try:
            storage_svc = get_storage_service()
            storage_svc.delete_by_url(doc["file_url"])
        except StorageServiceError as e:
            logger.warning(f"Storage delete failed (non-fatal): {e}")
        except Exception as e:
            logger.warning(f"Storage delete error (non-fatal): {e}")
    await rag.delete_document(agent_id, document_id)
    return {"message": "Document deleted"}
