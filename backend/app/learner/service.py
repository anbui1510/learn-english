from __future__ import annotations

from functools import lru_cache

from app.auth.settings import get_auth_settings
from app.learner.attempts import LearningAttemptRepository
from app.learner.profiles import LearnerProfileRepository


@lru_cache
def get_learner_profile_repository() -> LearnerProfileRepository:
    return LearnerProfileRepository(get_auth_settings().database_path)


@lru_cache
def get_learning_attempt_repository() -> LearningAttemptRepository:
    return LearningAttemptRepository(get_auth_settings().database_path)


def clear_learner_caches() -> None:
    get_learner_profile_repository.cache_clear()
    get_learning_attempt_repository.cache_clear()
