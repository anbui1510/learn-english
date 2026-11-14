from __future__ import annotations

from functools import lru_cache

from app.auth.settings import get_auth_settings
from app.users.repository import UserRepository


@lru_cache
def get_user_repository() -> UserRepository:
    settings = get_auth_settings()
    return UserRepository(settings.database_path)


def clear_user_repository_cache() -> None:
    get_user_repository.cache_clear()


def bootstrap_admin_emails() -> set[str]:
    settings = get_auth_settings()
    return {
        email.strip().lower()
        for email in settings.bootstrap_admin_emails.split(",")
        if email.strip()
    }
