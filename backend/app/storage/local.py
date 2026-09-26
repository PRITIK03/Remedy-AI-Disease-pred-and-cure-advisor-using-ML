"""Local filesystem storage provider with path traversal protections."""

from __future__ import annotations

from pathlib import Path

from backend.app.core.config import get_settings
from backend.app.storage.base import (
    StorageError,
    StorageFileNotFoundError,
    StorageProvider,
)


class LocalStorageProvider(StorageProvider):
    """Stores files on the local filesystem anchored to a root base directory."""

    def __init__(self, base_dir: Path | str | None = None) -> None:
        if base_dir is None:
            settings = get_settings()
            self.base_dir = Path(settings.reports_storage_dir).resolve()
        else:
            self.base_dir = Path(base_dir).resolve()

        self.base_dir.mkdir(parents=True, exist_ok=True)

    def _resolve_safe_path(self, storage_key: str) -> Path:
        """Resolve path and verify it stays strictly inside self.base_dir (no traversal)."""
        # Strip leading slashes to prevent absolute path hijacking
        sanitized_key = storage_key.lstrip("/\\")
        target_path = (self.base_dir / sanitized_key).resolve()
        try:
            target_path.relative_to(self.base_dir)
        except ValueError as exc:
            raise StorageError(f"Path traversal detected: {storage_key}") from exc
        return target_path

    def save(self, storage_key: str, data: bytes) -> str:
        target_path = self._resolve_safe_path(storage_key)
        target_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            target_path.write_bytes(data)
        except OSError as exc:
            raise StorageError(f"Failed to write file to local storage: {exc}") from exc
        return str(target_path)

    def get(self, storage_key: str) -> bytes:
        target_path = self._resolve_safe_path(storage_key)
        if not target_path.is_file():
            raise StorageFileNotFoundError(f"File not found: {storage_key}")
        try:
            return target_path.read_bytes()
        except OSError as exc:
            raise StorageError(f"Failed to read file from local storage: {exc}") from exc

    def delete(self, storage_key: str) -> bool:
        target_path = self._resolve_safe_path(storage_key)
        if target_path.is_file():
            try:
                target_path.unlink()
                return True
            except OSError as exc:
                raise StorageError(f"Failed to delete file from local storage: {exc}") from exc
        return False

    def exists(self, storage_key: str) -> bool:
        target_path = self._resolve_safe_path(storage_key)
        return target_path.is_file()
