"""Cloudinary service for RAG file storage."""

import logging
import uuid
from io import BytesIO
from typing import Optional

from app.config import Settings, get_settings

logger = logging.getLogger(__name__)


class CloudinaryServiceError(Exception):
    """Cloudinary service error."""

    pass


class CloudinaryService:
    """Service for uploading and deleting files in Cloudinary."""

    def __init__(self, settings: Settings):
        self.settings = settings

    def _ensure_configured(self) -> None:
        """Ensure Cloudinary is configured."""
        if not all([
            self.settings.cloudinary_cloud_name,
            self.settings.cloudinary_api_key,
            self.settings.cloudinary_api_secret,
        ]):
            raise CloudinaryServiceError(
                "Cloudinary is not configured. Set CLOUDINARY_CLOUD_NAME, "
                "CLOUDINARY_API_KEY, CLOUDINARY_API_SECRET."
            )

    def upload_file(
        self,
        file_bytes: bytes,
        filename: str,
        agent_id: str,
        folder_path: str = "",
        document_id: Optional[str] = None,
    ) -> str:
        """
        Upload file to Cloudinary.

        Path: {CLOUDINARY_FOLDER}/{agent_id}/{folder_path}/{document_id}.ext

        Returns the secure URL of the uploaded file.
        """
        self._ensure_configured()

        import cloudinary
        import cloudinary.uploader

        cloudinary.config(
            cloud_name=self.settings.cloudinary_cloud_name,
            api_key=self.settings.cloudinary_api_key,
            api_secret=self.settings.cloudinary_api_secret,
        )

        base_folder = self.settings.cloudinary_folder.strip("/")
        path_parts = [base_folder, agent_id]
        if folder_path:
            path_parts.append(folder_path.strip("/"))
        folder = "/".join(path_parts)

        ext = ""
        if "." in filename:
            ext = "." + filename.rsplit(".", 1)[-1].lower()
        public_id = f"{folder}/{document_id or str(uuid.uuid4())}{ext}"

        # Determine resource_type: image for images, raw for others
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
                raise CloudinaryServiceError("Upload succeeded but no URL returned")
            return url
        except Exception as e:
            logger.error(f"Cloudinary upload failed: {e}", exc_info=True)
            raise CloudinaryServiceError(f"Failed to upload file: {e}") from e

    def delete_file(self, public_id: str, resource_type: str = "image") -> bool:
        """
        Delete file from Cloudinary by public_id.

        resource_type: "image" for images, "raw" for PDFs and other files.

        Returns True if deleted successfully.
        """
        self._ensure_configured()

        import cloudinary
        import cloudinary.uploader

        cloudinary.config(
            cloud_name=self.settings.cloudinary_cloud_name,
            api_key=self.settings.cloudinary_api_key,
            api_secret=self.settings.cloudinary_api_secret,
        )

        try:
            result = cloudinary.uploader.destroy(public_id, resource_type=resource_type)
            return result.get("result") == "ok"
        except Exception as e:
            logger.error(f"Cloudinary delete failed for {public_id}: {e}", exc_info=True)
            raise CloudinaryServiceError(f"Failed to delete file: {e}") from e


def get_cloudinary_service() -> CloudinaryService:
    """Get Cloudinary service instance."""
    return CloudinaryService(get_settings())
