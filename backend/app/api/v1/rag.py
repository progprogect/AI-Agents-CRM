"""RAG API endpoints - folders and documents management."""

import logging
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Body, Depends, File, Form, HTTPException, Query, UploadFile, status
from pydantic import BaseModel, Field

from app.api.auth import require_admin
from app.config import get_settings
from app.dependencies import CommonDependencies
from app.services.cloudinary_browse import (
    MAX_IMPORT_BATCH,
    build_secure_url,
    download_url_bytes,
    normalize_public_id_prefix,
    public_id_allowed,
    search_resources_by_prefix,
    serialize_search_hit,
)
from app.services.rag_indexing import (
    index_rag_document_core,
    new_rag_document_id,
)
from app.services.storage_service import StorageServiceError, get_storage_service
from app.storage.postgres_rag import PostgresRAGClient, get_postgres_rag_client
from app.storage.postgres_rag_folders import PostgresRAGFolders, get_postgres_rag_folders

logger = logging.getLogger(__name__)

router = APIRouter()

# Max upload size per RAG file (PDF, images, text)
MAX_FILE_SIZE = 50 * 1024 * 1024


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


def _ensure_cloudinary_storage() -> None:
    backend = (get_settings().storage_backend or "cloudinary").lower()
    if backend != "cloudinary":
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail="Cloudinary import is only available when STORAGE_BACKEND=cloudinary",
        )


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
    doc_id = new_rag_document_id()
    fid = UUID(folder_id) if folder_id else None

    folder_path = ""
    storage_svc = get_storage_service()
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

    core = await index_rag_document_core(
        agent_id=agent_id,
        agent_config_dict=agent_config_dict,
        folder_id=fid,
        doc_id=doc_id,
        filename=filename,
        content=content,
        file_url=file_url,
        title=title,
        rag_client=rag_client,
    )

    response = {
        "document_id": core["document_id"],
        "title": core["title"],
        "file_type": core["file_type"],
        "file_url": core["file_url"],
        "original_filename": core["original_filename"],
        "file_size": core["file_size"],
        "folder_id": folder_id,
    }
    if core.get("warning"):
        response["warning"] = core["warning"]
    return response


class CloudinaryImportItem(BaseModel):
    """Single asset to import from Cloudinary into RAG."""

    public_id: str = Field(..., min_length=1)
    resource_type: str = Field(..., description="Cloudinary resource_type: image or raw")
    format: Optional[str] = None


class CloudinaryImportRequest(BaseModel):
    items: list[CloudinaryImportItem] = Field(..., min_length=1, max_length=MAX_IMPORT_BATCH)
    folder_id: Optional[str] = None
    allowed_prefix: Optional[str] = Field(
        None,
        description="Only public_ids under this prefix are accepted (default: rag/{agent_id})",
    )


@router.get("/{agent_id}/rag/cloudinary/resources")
async def list_cloudinary_rag_resources(
    agent_id: str,
    prefix: Optional[str] = Query(
        None,
        description="public_id prefix (folder path). Defaults to CLOUDINARY_FOLDER/agent_id",
    ),
    max_results: int = Query(30, ge=1, le=100),
    next_cursor: Optional[str] = Query(None),
    deps: CommonDependencies = Depends(),
    _admin: str = require_admin(),
):
    """Search Cloudinary assets by public_id prefix (Admin Search API)."""
    _ensure_postgres()
    await _ensure_agent_exists(deps, agent_id)
    _ensure_cloudinary_storage()

    settings = get_settings()
    default_prefix = normalize_public_id_prefix(settings, agent_id)
    p = (prefix or default_prefix).strip().strip("/")

    try:
        raw = search_resources_by_prefix(p, max_results, next_cursor)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e
    except Exception as e:
        logger.exception("Cloudinary search failed: %s", e)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Cloudinary search failed",
        ) from e

    resources = []
    for hit in raw.get("resources") or []:
        ser = serialize_search_hit(hit)
        if ser.get("resource_type") == "video":
            continue
        resources.append(ser)

    return {
        "resources": resources,
        "next_cursor": raw.get("next_cursor"),
        "default_prefix": default_prefix,
    }


@router.post("/{agent_id}/rag/documents/import-from-cloudinary")
async def import_rag_documents_from_cloudinary(
    agent_id: str,
    body: CloudinaryImportRequest,
    deps: CommonDependencies = Depends(),
    _admin: str = require_admin(),
):
    """Download existing Cloudinary files and index them into RAG (no re-upload)."""
    _ensure_postgres()
    agent = await _ensure_agent_exists(deps, agent_id)
    agent_config_dict = agent.get("config", {}) if agent else {}
    _ensure_cloudinary_storage()

    settings = get_settings()
    allowed_prefix = (body.allowed_prefix or normalize_public_id_prefix(settings, agent_id)).strip().strip(
        "/"
    )
    fid = UUID(body.folder_id) if body.folder_id else None
    rag_client = get_postgres_rag_client()

    results: list[dict] = []

    for item in body.items:
        pid = item.public_id.strip()
        rt = item.resource_type.strip().lower()
        if rt == "video":
            results.append(
                {
                    "public_id": pid,
                    "status": "error",
                    "message": "Video import is not supported in v1",
                }
            )
            continue
        if rt not in ("image", "raw"):
            results.append(
                {
                    "public_id": pid,
                    "status": "error",
                    "message": "resource_type must be image or raw",
                }
            )
            continue
        if not public_id_allowed(pid, allowed_prefix):
            results.append(
                {
                    "public_id": pid,
                    "status": "error",
                    "message": f"public_id must start with prefix {allowed_prefix}",
                }
            )
            continue

        try:
            file_url = build_secure_url(pid, rt, format=item.format)
        except Exception as e:
            logger.warning("build_secure_url failed for %s: %s", pid, e)
            results.append(
                {
                    "public_id": pid,
                    "status": "error",
                    "message": "Could not build URL for asset",
                }
            )
            continue

        existing = await rag_client.get_document_id_by_file_url(agent_id, file_url)
        if existing:
            results.append(
                {
                    "public_id": pid,
                    "status": "duplicate",
                    "document_id": existing,
                    "message": "Already indexed for this agent",
                }
            )
            continue

        try:
            content = await download_url_bytes(file_url, MAX_FILE_SIZE)
        except Exception as e:
            logger.warning("Download failed for %s: %s", pid, e)
            results.append(
                {
                    "public_id": pid,
                    "status": "error",
                    "message": str(e) or "Download failed",
                }
            )
            continue

        filename = pid.rsplit("/", 1)[-1] if "/" in pid else pid
        if not filename:
            filename = "file"

        doc_id = new_rag_document_id()
        try:
            core = await index_rag_document_core(
                agent_id=agent_id,
                agent_config_dict=agent_config_dict,
                folder_id=fid,
                doc_id=doc_id,
                filename=filename,
                content=content,
                file_url=file_url,
                title=None,
                rag_client=rag_client,
            )
            results.append(
                {
                    "public_id": pid,
                    "status": "ok",
                    "document_id": core["document_id"],
                    "title": core["title"],
                    "file_type": core["file_type"],
                    "file_url": core["file_url"],
                }
            )
            if core.get("warning"):
                results[-1]["warning"] = core["warning"]
        except Exception as e:
            logger.exception("Index failed for %s: %s", pid, e)
            results.append(
                {
                    "public_id": pid,
                    "status": "error",
                    "message": str(e) or "Indexing failed",
                }
            )

    return {"results": results, "allowed_prefix": allowed_prefix}


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
