from __future__ import annotations

from functools import lru_cache

from app.auth.settings import get_auth_settings
from app.learner.attempts import LearningAttemptRepository
from app.learner.empathy import EmpathyEngine, get_default_empathy
from app.learner.profiles import LearnerProfileRepository
from app.learner.pronunciation import PronunciationEngine, get_default_pa
from app.learner.rate_limit import PaRateLimiter
from app.learner.srs import SrsRepository


@lru_cache
def get_learner_profile_repository() -> LearnerProfileRepository:
    return LearnerProfileRepository(get_auth_settings().database_path)


@lru_cache
def get_learning_attempt_repository() -> LearningAttemptRepository:
    return LearningAttemptRepository(get_auth_settings().database_path)


@lru_cache
def get_pa_rate_limiter() -> PaRateLimiter:
    settings = get_auth_settings()
    return PaRateLimiter(settings.database_path, daily_limit=settings.pa_daily_limit)


@lru_cache
def get_srs_repository() -> SrsRepository:
    return SrsRepository(get_auth_settings().database_path)


def get_pronunciation_engine() -> PronunciationEngine:
    settings = get_auth_settings()
    return get_default_pa(
        use_azure=settings.use_azure_pa,
        key=settings.azure_speech_key,
        region=settings.azure_speech_region,
    )


def get_empathy_engine() -> EmpathyEngine:
    settings = get_auth_settings()
    return get_default_empathy(
        use_gemini=settings.use_gemini_empathy,
        api_key=settings.gemini_api_key,
    )


def clear_learner_caches() -> None:
    get_learner_profile_repository.cache_clear()
    get_learning_attempt_repository.cache_clear()
    get_pa_rate_limiter.cache_clear()
    get_srs_repository.cache_clear()
