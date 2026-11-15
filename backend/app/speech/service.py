from __future__ import annotations

from functools import lru_cache

from app.auth.settings import get_auth_settings
from app.speech.repository import UtteranceRepository


@lru_cache
def get_utterance_repository() -> UtteranceRepository:
    return UtteranceRepository(get_auth_settings().database_path)


def clear_utterance_repository_cache() -> None:
    get_utterance_repository.cache_clear()
