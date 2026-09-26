"""Storage module factory and exports."""

from __future__ import annotations

from functools import lru_cache

from backend.app.core.config import get_settings
from backend.app.storage.base import (
    StorageError,
    StorageFileNotFoundError,
    StorageProvider,
)
from backend.app.storage.local import LocalStorageProvider


@lru_cache(maxsize=1)
def get_storage_provider() -> StorageProvider:
    """Return configured storage provider singleton."""
    settings = get_settings()
    if settings.storage_backend == "local":
        return LocalStorageProvider()
    # Can be extended for "s3", "gcs", etc.
    return LocalStorageProvider()


__all__ = [
    "StorageError",
    "StorageFileNotFoundError",
    "StorageProvider",
    "LocalStorageProvider",
    "get_storage_provider",
]
