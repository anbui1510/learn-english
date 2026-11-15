"""Object storage adapters for PDF (and later audio) blobs."""

from app.storage.base import ObjectStorage, StoredObject
from app.storage.factory import clear_storage_cache, get_storage

__all__ = [
    "ObjectStorage",
    "StoredObject",
    "clear_storage_cache",
    "get_storage",
]
