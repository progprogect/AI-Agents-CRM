"""Media upload endpoint — stores chat attachments in Cloudinary."""

import logging
import mimetypes
from typing import Optional

from fastapi import APIRouter, File, HTTPException, UploadFile, status
from pydantic import BaseModel

from app.api.auth import require_admin
from app.services.storage_service import StorageServiceError, get_storage_service

logger = logging.getLogger(__name__)

router = APIRouter()

# 20 MB limit for chat media uploads
MAX_FILE_SIZE = 20 * 1024 * 1024

ALLOWED_MIME_TYPES = {
    # Images
    "image/jpeg", "image/png", "image/gif", "image/webp", "image/bmp",
    # Video
    "video/mp4", "video/webm", "video/ogg", "video/quicktime",
    # Audio
    "audio/mpeg", "audio/ogg", "audio/wav", "audio/webm",
    # Documents
    "application/pdf",
    "application/msword",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}


class MediaUploadResponse(BaseModel):
    url: str
    media_type: str   # "image" | "video" | "audio" | "document"
    filename: str
    size_bytes: int


def _classify_mimetype(mimetype: str) -> str:
    if mimetype.startswith("image/"):
        return "image"
    if mimetype.startswith("video/"):
        return "video"
    if mimetype.startswith("audio/"):
        return "audio"
    return "document"


def store_chat_media_bytes(
    file_bytes: bytes,
    filename: str,
    content_type: Optional[str] = None,
) -> MediaUploadResponse:
    """Validate size/type, upload to chat CDN. Raises HTTPException on failure."""
    if len(file_bytes) > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File too large. Maximum size is {MAX_FILE_SIZE // (1024 * 1024)} MB.",
        )

    mimetype = (content_type or "").strip()
    if not mimetype or mimetype == "application/octet-stream":
        guessed, _ = mimetypes.guess_type(filename)
        mimetype = guessed or "application/octet-stream"

    if mimetype not in ALLOWED_MIME_TYPES:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=f"Unsupported file type: {mimetype}. Allowed: images, video, audio, PDF, Word.",
        )

    try:
        svc = get_storage_service()
        url = svc.upload_chat_media(file_bytes, filename, mimetype)
    except StorageServiceError as e:
        logger.error(f"Media upload failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Media upload failed: {e}",
        )

    media_type = _classify_mimetype(mimetype)
    logger.info(
        "Chat media stored: %s (%s, %s bytes) → %s",
        filename,
        media_type,
        len(file_bytes),
        url,
    )
    return MediaUploadResponse(
        url=url,
        media_type=media_type,
        filename=filename,
        size_bytes=len(file_bytes),
    )


@router.post(
    "/media/upload",
    response_model=MediaUploadResponse,
    status_code=status.HTTP_201_CREATED,
)
async def upload_chat_media(
    file: UploadFile = File(...),
    _admin: str = require_admin(),
):
    """Upload a chat media file (image / video / audio / document) to Cloudinary.

    Returns the public Cloudinary URL that can be included in admin messages
    or displayed in conversation view.

    - Max file size: 20 MB
    - Allowed: images, videos, audio, PDF, Word documents
    """
    file_bytes = await file.read()
    filename = file.filename or "upload"
    return store_chat_media_bytes(file_bytes, filename, file.content_type)
