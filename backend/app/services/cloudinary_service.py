"""Cloudinary storage backend."""

import logging
import uuid
from io import BytesIO
from typing import Optional

from app.config import Settings, get_settings
from app.services.storage_service import StorageService, StorageServiceError

logger = logging.getLogger(__name__)


# Backward-compatible alias so existing imports of CloudinaryServiceError keep working
CloudinaryServiceError = StorageServiceError


class CloudinaryService(StorageService):
    """StorageService backed by Cloudinary CDN."""

    def __init__(self, settings: Settings):
        self.settings = settings

    def _ensure_configured(self) -> None:
        if not all([
            self.settings.cloudinary_cloud_name,
            self.settings.cloudinary_api_key,
            self.settings.cloudinary_api_secret,
        ]):
            raise StorageServiceError(
                "Cloudinary is not configured. Set CLOUDINARY_CLOUD_NAME, "
                "CLOUDINARY_API_KEY, and CLOUDINARY_API_SECRET."
            )

    def _configure(self) -> None:
        import cloudinary
        cloudinary.config(
            cloud_name=self.settings.cloudinary_cloud_name,
            api_key=self.settings.cloudinary_api_key,
            api_secret=self.settings.cloudinary_api_secret,
        )

    def upload_file(
        self,
        file_bytes: bytes,
        filename: str,
        agent_id: str,
        folder_path: str = "",
        document_id: Optional[str] = None,
    ) -> str:
        """Upload a RAG document to Cloudinary. Returns the secure URL."""
        self._ensure_configured()
        self._configure()

        import cloudinary.uploader

        base_folder = self.settings.cloudinary_folder.strip("/")
        path_parts = [base_folder, agent_id]
        if folder_path:
            path_parts.append(folder_path.strip("/"))
        folder = "/".join(path_parts)

        ext = ("." + filename.rsplit(".", 1)[-1].lower()) if "." in filename else ""
        public_id = f"{folder}/{document_id or str(uuid.uuid4())}{ext}"

        image_extensions = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp", ".svg"}
        resource_type = "image" if ext.lower() in image_extensions else "raw"

        try:
            result = cloudinary.uploader.upload(
                BytesIO(file_bytes),
                public_id=public_id,
                resource_type=resource_type,
                overwrite=True,
            )
            url = result.get("secure_url") or result.get("url", "")
            if not url:
                raise StorageServiceError("Cloudinary upload succeeded but no URL returned")
            return url
        except StorageServiceError:
            raise
        except Exception as e:
            logger.error(f"Cloudinary upload failed: {e}", exc_info=True)
            raise StorageServiceError(f"Failed to upload file to Cloudinary: {e}") from e

    def upload_chat_media(
        self,
        file_bytes: bytes,
        filename: str,
        mimetype: str = "application/octet-stream",
    ) -> str:
        """Upload chat media to Cloudinary. Returns the secure URL."""
        self._ensure_configured()
        self._configure()

        import cloudinary.uploader

        base_folder = self.settings.cloudinary_folder.strip("/")
        folder = f"{base_folder}/chat-media"

        ext = ("." + filename.rsplit(".", 1)[-1].lower()) if "." in filename else ""
        public_id = f"{folder}/{uuid.uuid4()}{ext}"

        image_mimetypes = {"image/jpeg", "image/png", "image/gif", "image/webp", "image/bmp", "image/svg+xml"}
        video_mimetypes = {"video/mp4", "video/webm", "video/ogg", "video/quicktime"}
        if mimetype in image_mimetypes:
            resource_type = "image"
        elif mimetype in video_mimetypes:
            resource_type = "video"
        else:
            resource_type = "raw"

        try:
            result = cloudinary.uploader.upload(
                BytesIO(file_bytes),
                public_id=public_id,
                resource_type=resource_type,
                overwrite=False,
            )
            url = result.get("secure_url") or result.get("url", "")
            if not url:
                raise StorageServiceError("Cloudinary upload succeeded but no URL returned")
            return url
        except StorageServiceError:
            raise
        except Exception as e:
            logger.error(f"Cloudinary chat-media upload failed: {e}", exc_info=True)
            raise StorageServiceError(f"Failed to upload chat media to Cloudinary: {e}") from e

    def delete_by_url(self, file_url: str) -> bool:
        """Delete a Cloudinary file by its public URL.

        Parses the Cloudinary URL to extract public_id and resource_type,
        then calls the Cloudinary destroy API.
        """
        if "cloudinary.com" not in file_url or "/upload/" not in file_url:
            logger.warning(f"URL is not a Cloudinary URL, skipping delete: {file_url}")
            return False

        self._ensure_configured()
        self._configure()

        import cloudinary.uploader

        # Extract public_id: strip version segment (v1234567890/) if present
        suffix = file_url.split("/upload/")[1]
        parts = suffix.split("/")
        if parts and parts[0].startswith("v") and parts[0][1:].isdigit():
            parts = parts[1:]
        path = "/".join(parts)

        # Determine resource_type from extension
        ext = path.rsplit(".", 1)[-1].lower() if "." in path else ""
        image_exts = {"jpg", "jpeg", "png", "gif", "webp", "bmp", "svg"}
        video_exts = {"mp4", "webm", "mov", "avi", "ogg"}
        if ext in image_exts:
            resource_type = "image"
            public_id = path.rsplit(".", 1)[0]
        elif ext in video_exts:
            resource_type = "video"
            public_id = path.rsplit(".", 1)[0]
        else:
            resource_type = "raw"
            public_id = path  # raw resources keep the extension in public_id

        try:
            result = cloudinary.uploader.destroy(public_id, resource_type=resource_type)
            return result.get("result") == "ok"
        except Exception as e:
            logger.error(f"Cloudinary delete failed for {public_id}: {e}", exc_info=True)
            raise StorageServiceError(f"Failed to delete file from Cloudinary: {e}") from e


def get_cloudinary_service() -> CloudinaryService:
    """Get CloudinaryService instance (for backward compatibility)."""
    return CloudinaryService(get_settings())
