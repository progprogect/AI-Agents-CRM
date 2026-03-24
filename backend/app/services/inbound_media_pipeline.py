"""Inbound user media: download, persist to CDN, vision text for chat (Twilio WhatsApp first)."""

import logging
import mimetypes
import uuid
from dataclasses import dataclass
from typing import Any, Optional

import httpx

from app.services.image_processor_service import get_image_processor_service
from app.services.storage_service import StorageServiceError, get_storage_service

logger = logging.getLogger(__name__)

# Aligned with backend/app/api/v1/media.py MAX_FILE_SIZE for chat uploads
INBOUND_IMAGE_MAX_BYTES = 20 * 1024 * 1024

DOWNLOAD_TIMEOUT_SEC = 60.0

_ALLOWED_IMAGE_MIMES = frozenset(
    {
        "image/jpeg",
        "image/png",
        "image/gif",
        "image/webp",
        "image/bmp",
    }
)


@dataclass(frozen=True)
class PreparedInboundImage:
    """Public CDN URL plus vision summary for agent context."""

    public_url: str
    summary: str


def compose_user_message_for_agent(caption: str, image_summary: str) -> str:
    """Build text passed to AgentService when user sent an image (+ optional caption)."""
    cap = (caption or "").strip()
    summ = (image_summary or "").strip()
    block = f"[User sent an image. Description: {summ}]"
    if cap:
        return f"{cap}\n\n{block}"
    return block


def _normalize_image_mimetype(hint: str, response_ct: str) -> Optional[str]:
    raw = (response_ct or "").split(";")[0].strip().lower()
    if raw in _ALLOWED_IMAGE_MIMES:
        return raw
    h = (hint or "").split(";")[0].strip().lower()
    if h in _ALLOWED_IMAGE_MIMES:
        return h
    if raw.startswith("image/") or h.startswith("image/"):
        # Unknown image/* subtype — still allow common safe path via hint
        return h if h.startswith("image/") else (raw if raw.startswith("image/") else None)
    return None


def _filename_for_mimetype(mimetype: str) -> str:
    ext = mimetypes.guess_extension(mimetype, strict=False) or ".jpg"
    return f"inbound-{uuid.uuid4().hex}{ext}"


async def prepare_inbound_image_for_chat(
    *,
    download_url: str,
    http_basic_auth: tuple[str, str] | None,
    content_type_hint: str,
    agent_id: str,
    agent_config: dict[str, Any],
) -> PreparedInboundImage | None:
    """Download image, upload to chat CDN, run vision. Returns None on any failure (fail-open for caller)."""
    url = (download_url or "").strip()
    if not url:
        return None

    auth: httpx.Auth | None = None
    if http_basic_auth is not None:
        user, password = http_basic_auth
        if not user or not password:
            return None
        auth = (user, password)

    try:
        async with httpx.AsyncClient(
            timeout=DOWNLOAD_TIMEOUT_SEC,
            follow_redirects=True,
        ) as client:
            async with client.stream("GET", url, auth=auth) as resp:
                if resp.status_code >= 400:
                    logger.warning(
                        "Inbound image download failed: status=%s url=%s",
                        resp.status_code,
                        url[:120],
                    )
                    return None
                mimetype = _normalize_image_mimetype(
                    content_type_hint,
                    resp.headers.get("content-type", ""),
                )
                if not mimetype:
                    logger.warning("Inbound image rejected: unsupported content-type")
                    return None
                chunks: list[bytes] = []
                total = 0
                async for chunk in resp.aiter_bytes():
                    total += len(chunk)
                    if total > INBOUND_IMAGE_MAX_BYTES:
                        logger.warning("Inbound image too large (> %s bytes)", INBOUND_IMAGE_MAX_BYTES)
                        return None
                    chunks.append(chunk)
                data = b"".join(chunks)
    except httpx.RequestError as exc:
        logger.warning("Inbound image download error: %s", exc, exc_info=True)
        return None

    if not data:
        return None

    filename = _filename_for_mimetype(mimetype)
    try:
        storage = get_storage_service()
        public_url = storage.upload_chat_media(data, filename, mimetype)
    except StorageServiceError as exc:
        logger.error("Inbound image CDN upload failed: %s", exc, exc_info=True)
        return None

    try:
        processor = get_image_processor_service()
        summary = await processor.describe_image_for_chat_context(
            public_url,
            agent_id=agent_id,
            agent_config=agent_config,
        )
    except Exception:
        logger.warning("Inbound image vision failed after CDN upload; url=%s", public_url[:80])
        return None

    summary = (summary or "").strip()
    if not summary:
        return None

    return PreparedInboundImage(public_url=public_url, summary=summary)
