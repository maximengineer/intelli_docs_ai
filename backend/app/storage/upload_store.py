from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

from app.core.settings import get_settings


@dataclass(frozen=True)
class StoredUpload:
    content_hash: str
    storage_key: str
    path: Path


class LocalUploadStore:
    """Durable local file store for Docker/local document processing."""

    def __init__(self, root: Path | None = None) -> None:
        settings = get_settings()
        configured_root = root or Path(settings.upload_storage_dir)
        if not configured_root.is_absolute():
            configured_root = Path(__file__).resolve().parents[3] / configured_root
        self.root = configured_root

    def put(self, *, filename: str, content: bytes) -> StoredUpload:
        del filename
        content_hash = hashlib.sha256(content).hexdigest()
        storage_key = content_hash
        path = self._path_for_key(storage_key)
        path.parent.mkdir(parents=True, exist_ok=True)
        if not path.exists():
            path.write_bytes(content)
        return StoredUpload(content_hash=content_hash, storage_key=storage_key, path=path)

    def get(self, storage_key: str) -> bytes:
        return self._path_for_key(storage_key).read_bytes()

    def delete(self, storage_key: str) -> None:
        self._path_for_key(storage_key).unlink(missing_ok=True)

    def _path_for_key(self, storage_key: str) -> Path:
        if "/" in storage_key or "\\" in storage_key or storage_key.startswith("."):
            raise ValueError("Invalid upload storage key.")
        return self.root / storage_key


def get_upload_store() -> LocalUploadStore:
    return LocalUploadStore()
