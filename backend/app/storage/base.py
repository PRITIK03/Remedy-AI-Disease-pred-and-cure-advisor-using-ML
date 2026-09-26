"""Storage abstraction for reports and multimodal documents (Phase 7).

Decouples file storage from API and database models so backend storage can be
local filesystem, in-memory (for tests), or an object store (e.g. S3).
"""

from __future__ import annotations

from abc import ABC, abstractmethod


class StorageError(Exception):
    """Base storage error."""


class StorageFileNotFoundError(StorageError):
    """File not found in storage."""


class StorageProvider(ABC):
    """Abstract storage provider for report uploads."""

    @abstractmethod
    def save(self, storage_key: str, data: bytes) -> str:
        """Save raw bytes under the given storage key and return the resolved locator."""

    @abstractmethod
    def get(self, storage_key: str) -> bytes:
        """Retrieve bytes associated with the storage key."""

    @abstractmethod
    def delete(self, storage_key: str) -> bool:
        """Delete file associated with the storage key if it exists."""

    @abstractmethod
    def exists(self, storage_key: str) -> bool:
        """Check if file exists."""
