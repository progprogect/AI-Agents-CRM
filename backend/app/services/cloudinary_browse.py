"""Cloudinary Admin Search + signed URL helpers for RAG import."""

import logging
from typing import Any, Optional

import httpx

from app.config import Settings, get_settings

logger = logging.getLogger(__name__)

MAX_IMPORT_BATCH = 20


def _configure_cloudinary(settings: Settings) -> None:
    import cloudinary

    if not all(
        [
            settings.cloudinary_cloud_name,
            settings.cloudinary_api_key,
            settings.cloudinary_api_secret,
        ]
    ):
        raise RuntimeError("Cloudinary is not configured")
    cloudinary.config(
        cloud_name=settings.cloudinary_cloud_name,
        api_key=settings.cloudinary_api_key,
        api_secret=settings.cloudinary_api_secret,
    )


def search_resources_by_prefix(
    prefix: str,
    max_results: int,
    next_cursor: Optional[str] = None,
) -> dict[str, Any]:
    """Search assets whose public_id starts with prefix (folder-style path)."""
    import cloudinary.search

    settings = get_settings()
    _configure_cloudinary(settings)

    p = prefix.strip().strip("/")
    if not p:
        raise ValueError("prefix is required")

    # Wildcard prefix on public_id (folder paths use / in public_id).
    # Exclude video in the query so each page returns up to max_results *importable*
    # assets; filtering videos only in Python used to shrink pages (many videos → few rows).
    expr = f"public_id:{p}* AND (resource_type:image OR resource_type:raw)"

    q = cloudinary.search.Search().expression(expr).max_results(min(max_results, 100))
    if next_cursor:
        q = q.next_cursor(next_cursor)
    return q.execute()


def build_secure_url(
    public_id: str,
    resource_type: str,
    format: Optional[str] = None,
) -> str:
    """Build HTTPS URL for an existing Cloudinary asset."""
    import cloudinary.utils

    settings = get_settings()
    _configure_cloudinary(settings)

    kwargs: dict[str, Any] = {"secure": True, "resource_type": resource_type}
    if format:
        kwargs["format"] = format
    url, _ = cloudinary.utils.cloudinary_url(public_id, **kwargs)
    if not url:
        raise RuntimeError("cloudinary_url returned empty")
    return url


def normalize_public_id_prefix(settings: Settings, agent_id: str) -> str:
    """Default prefix matching upload_file layout: {CLOUDINARY_FOLDER}/{agent_id}."""
    base = (settings.cloudinary_folder or "rag").strip("/")
    return f"{base}/{agent_id}"


def public_id_allowed(public_id: str, allowed_prefix: str) -> bool:
    """Reject imports outside the chosen folder prefix (security)."""
    ap = allowed_prefix.strip().strip("/")
    pid = public_id.strip()
    if not ap:
        return False
    return pid == ap or pid.startswith(ap + "/")


async def download_url_bytes(url: str, max_bytes: int) -> bytes:
    """Download remote file with size cap (same order of magnitude as RAG upload)."""
    timeout = httpx.Timeout(120.0, connect=30.0)
    async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
        async with client.stream("GET", url) as resp:
            resp.raise_for_status()
            chunks: list[bytes] = []
            total = 0
            async for chunk in resp.aiter_bytes(65536):
                total += len(chunk)
                if total > max_bytes:
                    raise ValueError(f"Download exceeds max size ({max_bytes} bytes)")
                chunks.append(chunk)
            return b"".join(chunks)


def serialize_search_hit(r: dict[str, Any]) -> dict[str, Any]:
    """Normalize Cloudinary search resource for API JSON."""
    return {
        "public_id": r.get("public_id", ""),
        "resource_type": r.get("resource_type", ""),
        "format": r.get("format"),
        "bytes": r.get("bytes"),
        "created_at": r.get("created_at"),
        "secure_url": r.get("secure_url"),
        "width": r.get("width"),
        "height": r.get("height"),
    }
