"""Provider-agnostic storage service interface.

Supported backends (configured via STORAGE_BACKEND env var):
  - "cloudinary" (default) — uses Cloudinary CDN
  - "s3"                   — uses Amazon S3 (for AWS deployments)

Usage in endpoints:
    from app.services.storage_service import get_storage_service, StorageServiceError

    svc = get_storage_service()
    url = svc.upload_file(file_bytes, filename, agent_id)
"""

from abc import ABC, abstractmethod
from typing import Optional


class StorageServiceError(Exception):
    """Raised when any storage operation fails."""


class StorageService(ABC):
    """Abstract interface for file storage backends."""

    @abstractmethod
    def upload_file(
        self,
        file_bytes: bytes,
        filename: str,
        agent_id: str,
        folder_path: str = "",
        document_id: Optional[str] = None,
    ) -> str:
        """Upload a RAG document file.

        Path convention: {base_folder}/{agent_id}/{folder_path}/{document_id}.ext

        Returns the public URL of the uploaded file.
        """

    @abstractmethod
    def upload_chat_media(
        self,
        file_bytes: bytes,
        filename: str,
        mimetype: str = "application/octet-stream",
    ) -> str:
        """Upload a chat media file (image/video/audio/document).

        Path convention: {base_folder}/chat-media/{uuid}.ext

        Returns the public URL.
        """

    @abstractmethod
    def delete_by_url(self, file_url: str) -> bool:
        """Delete a file by its public URL.

        Each implementation knows how to parse its own URL format to get the
        storage-specific identifier (Cloudinary public_id or S3 key).

        Returns True on success, False if the URL format is not recognised.
        Raises StorageServiceError on API / network errors.
        """


def get_storage_service() -> StorageService:
    """Return the configured storage backend instance.

    Reads STORAGE_BACKEND from settings:
      - "cloudinary" (default) → CloudinaryService
      - "s3"                   → S3StorageService
    """
    from app.config import get_settings

    settings = get_settings()
    backend = (getattr(settings, "storage_backend", None) or "cloudinary").lower()

    if backend == "s3":
        from app.services.s3_service import S3StorageService
        return S3StorageService(settings)

    from app.services.cloudinary_service import CloudinaryService
    return CloudinaryService(settings)
