"""Amazon S3 storage backend.

Used when STORAGE_BACKEND=s3 (AWS deployments).
boto3 is already a project dependency (used for DynamoDB/Secrets Manager).

Required config:
    STORAGE_BACKEND=s3
    S3_BUCKET_NAME=your-media-bucket
    S3_REGION=us-east-1          (defaults to AWS_REGION)
    S3_PUBLIC_URL_PREFIX=...     (optional: CloudFront or custom domain)

If S3_PUBLIC_URL_PREFIX is not set, files are served directly from S3:
    https://{bucket}.s3.{region}.amazonaws.com/{key}

On ECS, the task role must have:
    s3:PutObject, s3:DeleteObject on the bucket ARN.
The bucket must allow public GetObject (see infra/s3.tf).
"""

import logging
import uuid
from typing import Optional
from urllib.parse import urlparse

from app.services.storage_service import StorageService, StorageServiceError

logger = logging.getLogger(__name__)

# Extension → Content-Type mapping for correct Content-Type headers in S3
_EXT_TO_MIMETYPE: dict[str, str] = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".gif": "image/gif",
    ".webp": "image/webp",
    ".bmp": "image/bmp",
    ".svg": "image/svg+xml",
    ".mp4": "video/mp4",
    ".webm": "video/webm",
    ".mov": "video/quicktime",
    ".avi": "video/x-msvideo",
    ".mp3": "audio/mpeg",
    ".ogg": "audio/ogg",
    ".wav": "audio/wav",
    ".pdf": "application/pdf",
    ".doc": "application/msword",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".txt": "text/plain",
}


class S3StorageService(StorageService):
    """StorageService backed by Amazon S3."""

    def __init__(self, settings) -> None:
        self.settings = settings

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _get_client(self):
        try:
            import boto3
        except ImportError:
            raise StorageServiceError("boto3 is required for S3 storage.")

        region = getattr(self.settings, "s3_region", None) or getattr(self.settings, "aws_region", "us-east-1")
        return boto3.client("s3", region_name=region)

    def _get_bucket(self) -> str:
        bucket = getattr(self.settings, "s3_bucket_name", None)
        if not bucket:
            raise StorageServiceError(
                "S3_BUCKET_NAME is not configured. "
                "Set STORAGE_BACKEND=s3 and S3_BUCKET_NAME=your-bucket-name."
            )
        return bucket

    def _public_url(self, key: str) -> str:
        prefix = (getattr(self.settings, "s3_public_url_prefix", None) or "").rstrip("/")
        if prefix:
            return f"{prefix}/{key}"
        region = getattr(self.settings, "s3_region", None) or getattr(self.settings, "aws_region", "us-east-1")
        return f"https://{self._get_bucket()}.s3.{region}.amazonaws.com/{key}"

    def _key_from_url(self, url: str) -> Optional[str]:
        """Extract the S3 object key from a public URL."""
        prefix = (getattr(self.settings, "s3_public_url_prefix", None) or "").rstrip("/")
        if prefix and url.startswith(prefix + "/"):
            return url[len(prefix) + 1:]
        # Direct S3 URL: https://bucket.s3.region.amazonaws.com/key
        parsed = urlparse(url)
        if "amazonaws.com" in parsed.netloc:
            return parsed.path.lstrip("/")
        return None

    def _upload(self, file_bytes: bytes, key: str, mimetype: str) -> str:
        client = self._get_client()
        bucket = self._get_bucket()
        try:
            client.put_object(
                Bucket=bucket,
                Key=key,
                Body=file_bytes,
                ContentType=mimetype,
            )
            return self._public_url(key)
        except Exception as e:
            logger.error(f"S3 upload failed (key={key}): {e}", exc_info=True)
            raise StorageServiceError(f"S3 upload failed: {e}") from e

    # ── StorageService interface ──────────────────────────────────────────────

    def upload_file(
        self,
        file_bytes: bytes,
        filename: str,
        agent_id: str,
        folder_path: str = "",
        document_id: Optional[str] = None,
    ) -> str:
        """Upload a RAG document to S3. Returns the public URL."""
        ext = ("." + filename.rsplit(".", 1)[-1].lower()) if "." in filename else ""
        folder_parts = ["rag", agent_id]
        if folder_path:
            folder_parts.append(folder_path.strip("/"))
        prefix = "/".join(folder_parts)
        key = f"{prefix}/{document_id or str(uuid.uuid4())}{ext}"

        mimetype = _EXT_TO_MIMETYPE.get(ext.lower(), "application/octet-stream")
        url = self._upload(file_bytes, key, mimetype)
        logger.info(f"S3 RAG file uploaded: bucket={self._get_bucket()} key={key}")
        return url

    def upload_chat_media(
        self,
        file_bytes: bytes,
        filename: str,
        mimetype: str = "application/octet-stream",
    ) -> str:
        """Upload chat media (image/video/audio/document) to S3. Returns the public URL."""
        ext = ("." + filename.rsplit(".", 1)[-1].lower()) if "." in filename else ""
        key = f"chat-media/{uuid.uuid4()}{ext}"
        url = self._upload(file_bytes, key, mimetype)
        logger.info(f"S3 chat media uploaded: bucket={self._get_bucket()} key={key}")
        return url

    def delete_by_url(self, file_url: str) -> bool:
        """Delete an S3 object by its public URL."""
        key = self._key_from_url(file_url)
        if not key:
            logger.warning(f"Cannot extract S3 key from URL (not an S3 URL?): {file_url}")
            return False

        client = self._get_client()
        bucket = self._get_bucket()
        try:
            client.delete_object(Bucket=bucket, Key=key)
            logger.info(f"S3 object deleted: bucket={bucket} key={key}")
            return True
        except Exception as e:
            logger.error(f"S3 delete failed (key={key}): {e}", exc_info=True)
            raise StorageServiceError(f"S3 delete failed: {e}") from e
