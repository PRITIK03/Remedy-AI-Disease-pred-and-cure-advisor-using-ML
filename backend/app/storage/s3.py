"""S3-compatible object storage provider (Phase 9).

Implements the existing `StorageProvider` interface, so `STORAGE_BACKEND=s3`
swaps storage without touching the API, the report service, or the DB models.
Works with AWS S3, MinIO, Cloudflare R2, Backblaze B2, and any other
S3-compatible endpoint.

Design notes
------------
* **No document is uploaded by this module** — it only performs the object
  operations the report service already needs (put/get/delete/exists).
* **Server-side encryption** is supported and should be used for real medical
  documents; the key id is configuration, never a hardcoded value.
* **No public access**: the bucket policy stays private and reads go through
  short-lived presigned URLs, never public object links.
* `boto3` is imported lazily so the development (local) path never pays the
  dependency cost and the package stays optional.
"""

from __future__ import annotations

from typing import Any

from backend.app.core.config import get_settings
from backend.app.core.logging import get_logger
from backend.app.storage.base import (
    StorageError,
    StorageFileNotFoundError,
    StorageProvider,
)

logger = get_logger("backend.storage.s3")

_NOT_FOUND_CODES = {"404", "NoSuchKey", "NotFound"}


class S3StorageProvider(StorageProvider):
    """Stores uploaded reports in an S3-compatible bucket."""

    def __init__(self, client: Any | None = None, bucket: str | None = None) -> None:
        settings = get_settings()
        self.bucket = bucket or settings.s3_bucket
        if not self.bucket:
            raise StorageError("S3 storage requires S3_BUCKET to be set.")
        self.presigned_expiry = settings.s3_presigned_expiry_seconds
        self._client = client or self._build_client(settings)

    # ------------------------------------------------------------------ #
    @staticmethod
    def _build_client(settings) -> Any:
        try:
            import boto3
            from botocore.config import Config
        except ImportError as exc:  # pragma: no cover - dependency guard
            raise StorageError(
                "boto3 is required for STORAGE_BACKEND=s3 (pip install boto3)."
            ) from exc

        # An empty access/secret pair means "use the ambient IAM role or
        # workload identity" — the recommended production configuration.
        static_creds = bool(
            settings.s3_access_key_id and settings.s3_secret_access_key
        )
        if static_creds and not settings.s3_endpoint_url:
            logger.warning(
                "S3 static credentials configured; prefer an IAM role or "
                "workload identity where possible."
            )

        session_kwargs: dict[str, Any] = {"region_name": settings.s3_region}
        if static_creds:
            session_kwargs["aws_access_key_id"] = settings.s3_access_key_id
            session_kwargs["aws_secret_access_key"] = settings.s3_secret_access_key

        config = Config(
            signature_version="s3v4",
            s3={"addressing_style": settings.s3_addressing_style},
            connect_timeout=settings.s3_connect_timeout_seconds,
            read_timeout=settings.s3_read_timeout_seconds,
            retries={"max_attempts": 3, "mode": "standard"},
        )
        return boto3.client(
            "s3",
            endpoint_url=settings.s3_endpoint_url or None,
            use_ssl=settings.s3_use_ssl,
            config=config,
            **session_kwargs,
        )

    # ------------------------------------------------------------------ #
    @staticmethod
    def _normalize_key(storage_key: str) -> str:
        """Normalize to a relative object key (mirrors the local traversal guard)."""
        key = storage_key.replace("\\", "/").lstrip("/")
        if not key or ".." in key.split("/"):
            raise StorageError(f"Rejected storage key: {storage_key}")
        return key

    def _encryption_args(self) -> dict[str, str]:
        settings = get_settings()
        if not settings.s3_server_side_encryption:
            return {}
        args: dict[str, str] = {
            "ServerSideEncryption": settings.s3_server_side_encryption,
        }
        if settings.s3_kms_key_id and settings.s3_server_side_encryption == "aws:kms":
            args["SSEKMSKeyId"] = settings.s3_kms_key_id
        return args

    @staticmethod
    def _error_code(exc: Exception) -> str:
        """Best-effort extraction of an S3 error code from any exception shape."""
        response = getattr(exc, "response", None)
        if not isinstance(response, dict):
            return type(exc).__name__
        error = response.get("Error")
        if not isinstance(error, dict):
            return type(exc).__name__
        return str(error.get("Code") or type(exc).__name__)

    # ------------------------------------------------------------------ #
    # StorageProvider interface
    # ------------------------------------------------------------------ #
    def save(self, storage_key: str, data: bytes) -> str:
        key = self._normalize_key(storage_key)
        try:
            self._client.put_object(
                Bucket=self.bucket,
                Key=key,
                Body=data,
                ContentType="application/octet-stream",
                **self._encryption_args(),
            )
        except Exception as exc:  # noqa: BLE001 - mapped to a domain error
            # Never log the object body, only the key and the error type.
            logger.error("S3 put_object failed for key %s: %s", key, type(exc).__name__)
            raise StorageError("Failed to write the object to S3 storage.") from exc
        return f"s3://{self.bucket}/{key}"

    def get(self, storage_key: str) -> bytes:
        key = self._normalize_key(storage_key)
        try:
            response = self._client.get_object(Bucket=self.bucket, Key=key)
            return response["Body"].read()
        except Exception as exc:  # noqa: BLE001
            if self._error_code(exc) in _NOT_FOUND_CODES:
                raise StorageFileNotFoundError("File not found in storage.") from exc
            logger.error("S3 get_object failed for key %s: %s", key, type(exc).__name__)
            raise StorageError("Failed to read the object from S3 storage.") from exc

    def delete(self, storage_key: str) -> bool:
        key = self._normalize_key(storage_key)
        if not self.exists(storage_key):
            return False
        try:
            self._client.delete_object(Bucket=self.bucket, Key=key)
            return True
        except Exception as exc:  # noqa: BLE001
            logger.error(
                "S3 delete_object failed for key %s: %s", key, type(exc).__name__
            )
            raise StorageError("Failed to delete the object from S3 storage.") from exc

    def exists(self, storage_key: str) -> bool:
        key = self._normalize_key(storage_key)
        try:
            self._client.head_object(Bucket=self.bucket, Key=key)
            return True
        except Exception as exc:  # noqa: BLE001
            if self._error_code(exc) in _NOT_FOUND_CODES | {"403"}:
                return False
            logger.error(
                "S3 head_object failed for key %s: %s", key, type(exc).__name__
            )
            raise StorageError("Failed to check the object in S3 storage.") from exc

    # ------------------------------------------------------------------ #
    def presigned_url(self, storage_key: str) -> str:
        """Short-lived read URL, used instead of a public object link."""
        key = self._normalize_key(storage_key)
        return self._client.generate_presigned_url(
            "get_object",
            Params={"Bucket": self.bucket, "Key": key},
            ExpiresIn=self.presigned_expiry,
        )


__all__ = ["S3StorageProvider"]
