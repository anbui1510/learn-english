from __future__ import annotations

from functools import lru_cache

from app.auth.settings import get_auth_settings
from app.cases.repository import CaseRepository


@lru_cache
def get_case_repository() -> CaseRepository:
    settings = get_auth_settings()
    return CaseRepository(settings.database_path)


def clear_case_repository_cache() -> None:
    get_case_repository.cache_clear()
