from __future__ import annotations

from functools import lru_cache

from app.auth.settings import get_auth_settings
from app.dialogues.repository import DialogueRepository


@lru_cache
def get_dialogue_repository() -> DialogueRepository:
    return DialogueRepository(get_auth_settings().database_path)


def clear_dialogue_repository_cache() -> None:
    get_dialogue_repository.cache_clear()
