from __future__ import annotations

from functools import lru_cache

from app.auth.settings import get_auth_settings
from app.books.repository import BookSourceRepository


@lru_cache
def get_book_source_repository() -> BookSourceRepository:
    return BookSourceRepository(get_auth_settings().database_path)
