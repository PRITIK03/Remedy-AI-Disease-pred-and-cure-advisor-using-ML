"""Storage module factory and exports."""

from __future__ import annotations

from functools import lru_cache

from backend.app.core.config import get_settings
from backend.app.core.logging import get_logger
from backend.app.storage.base import (
    StorageError,
    StorageFileNotFoundError,
    StorageProvider,
)
from backend.app.storage.local import LocalStorageProvider

logger = get_logger("backend.storage")


@lru_cache(maxsize=1)
def get_storage_provider() -> StorageProvider:
    """Return the configured storage provider singleton.

    `STORAGE_BACKEND` selects the implementation: `local` (default, for
    development) or `s3` (any S3-compatible endpoint). The S3 import is local
    so a local-only deployment never needs boto3 installed.
    """
    settings = get_settings()
    backend = settings.storage_backend
    if backend == "local":
        return LocalStorageProvider()
    if backend == "s3":
        from backend.app.storage.s3 import S3StorageProvider

        return S3StorageProvider()
    # validate_production() rejects unknown backends in production; this is a
    # last-resort guard so a typo never silently falls back to local disk.
    raise StorageError(f"Unknown STORAGE_BACKEND '{backend}'.")


def storage_backend_name() -> str:
    """Active backend name, for health reporting (never a secret)."""
    return get_settings().storage_backend


__all__ = [
    "StorageError",
    "StorageFileNotFoundError",
    "StorageProvider",
    "LocalStorageProvider",
    "get_storage_provider",
    "storage_backend_name",
]
