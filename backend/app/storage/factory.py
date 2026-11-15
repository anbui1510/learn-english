from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from app.auth.settings import get_auth_settings
from app.storage.base import ObjectStorage
from app.storage.gcs import GcsStorage
from app.storage.local import LocalFilesystemStorage


@lru_cache
def get_storage() -> ObjectStorage:
    settings = get_auth_settings()
    if settings.gcs_bucket:
        return GcsStorage(settings.gcs_bucket, location=settings.gcs_location or None)
    root = Path(settings.storage_root)
    return LocalFilesystemStorage(
        root,
        signing_secret=settings.jwt_secret or settings.session_secret or "dev-storage",
        public_base_url=settings.api_public_base_url,
    )


def clear_storage_cache() -> None:
    get_storage.cache_clear()
