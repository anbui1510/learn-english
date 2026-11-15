from __future__ import annotations

from functools import lru_cache

from app.auth.settings import get_auth_settings
from app.facts.repository import FactRepository


@lru_cache
def get_fact_repository() -> FactRepository:
    return FactRepository(get_auth_settings().database_path)


def clear_fact_repository_cache() -> None:
    get_fact_repository.cache_clear()
