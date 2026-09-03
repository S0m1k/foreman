"""File storage: local filesystem for dev, S3/MinIO for docker-compose.

Layout mirrors the spec:
    projects/{project_id}/documents/{document_id}.pdf
    projects/{project_id}/pages/{document_id}/p{n}.png
    projects/{project_id}/crops/{finding_id}_{side}.png
"""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Protocol

from .settings import settings


class Storage(Protocol):
    def save(self, key: str, data: bytes) -> str: ...
    def save_file(self, key: str, source_path: str) -> str: ...
    def read(self, key: str) -> bytes: ...
    def local_path(self, key: str) -> str:
        """A filesystem path for libraries that need one (PyMuPDF)."""
        ...


class LocalStorage:
    def __init__(self, root: Path) -> None:
        self._root = root

    def _resolve(self, key: str) -> Path:
        path = (self._root / key).resolve()
        if not str(path).startswith(str(self._root.resolve())):
            raise ValueError(f"storage key escapes root: {key!r}")
        return path

    def save(self, key: str, data: bytes) -> str:
        path = self._resolve(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return key

    def save_file(self, key: str, source_path: str) -> str:
        path = self._resolve(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source_path, path)
        return key

    def read(self, key: str) -> bytes:
        return self._resolve(key).read_bytes()

    def local_path(self, key: str) -> str:
        return str(self._resolve(key))


class S3Storage:
    def __init__(self) -> None:
        import boto3

        self._client = boto3.client(
            "s3",
            endpoint_url=settings.s3_endpoint_url,
            aws_access_key_id=settings.s3_access_key,
            aws_secret_access_key=settings.s3_secret_key,
        )
        self._bucket = settings.s3_bucket
        self._cache = Path(settings.storage_dir) / "_s3cache"
        self._cache.mkdir(parents=True, exist_ok=True)
        self._ensure_bucket()

    def _ensure_bucket(self) -> None:
        try:
            self._client.head_bucket(Bucket=self._bucket)
        except Exception:
            self._client.create_bucket(Bucket=self._bucket)

    def save(self, key: str, data: bytes) -> str:
        self._client.put_object(Bucket=self._bucket, Key=key, Body=data)
        return key

    def save_file(self, key: str, source_path: str) -> str:
        self._client.upload_file(source_path, self._bucket, key)
        return key

    def read(self, key: str) -> bytes:
        response = self._client.get_object(Bucket=self._bucket, Key=key)
        return response["Body"].read()

    def local_path(self, key: str) -> str:
        cached = self._cache / key
        if not cached.exists():
            cached.parent.mkdir(parents=True, exist_ok=True)
            cached.write_bytes(self.read(key))
        return str(cached)


def document_key(project_id: str, document_id: str) -> str:
    return f"projects/{project_id}/documents/{document_id}.pdf"


def page_image_key(project_id: str, document_id: str, page_number: int) -> str:
    return f"projects/{project_id}/pages/{document_id}/p{page_number}.png"


def crop_key(project_id: str, finding_id: str, side: str) -> str:
    return f"projects/{project_id}/crops/{finding_id}_{side}.png"


_storage: Storage | None = None


def get_storage() -> Storage:
    global _storage
    if _storage is None:
        if settings.storage_backend == "s3":
            _storage = S3Storage()
        else:
            _storage = LocalStorage(settings.storage_path)
    return _storage
