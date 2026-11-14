from __future__ import annotations

import pytest

from app.auth.oauth import reset_oauth_registration
from app.auth.settings import clear_auth_settings_cache
from app.users.service import clear_user_repository_cache


@pytest.fixture(autouse=True)
def _reset_caches() -> None:
    clear_auth_settings_cache()
    clear_user_repository_cache()
    reset_oauth_registration()
    yield
    clear_auth_settings_cache()
    clear_user_repository_cache()
    reset_oauth_registration()


@pytest.fixture
def tmp_db_path(tmp_path, monkeypatch: pytest.MonkeyPatch) -> str:
    db_path = str(tmp_path / "test.sqlite3")
    monkeypatch.setenv("DATABASE_PATH", db_path)
    clear_auth_settings_cache()
    clear_user_repository_cache()
    reset_oauth_registration()
    return db_path


@pytest.fixture
def auth_env(tmp_db_path: str, monkeypatch: pytest.MonkeyPatch) -> str:
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "test-client-id")
    monkeypatch.setenv("GOOGLE_CLIENT_SECRET", "test-client-secret")
    monkeypatch.setenv(
        "GOOGLE_REDIRECT_URI",
        "http://127.0.0.1:8000/auth/google/callback",
    )
    monkeypatch.setenv("JWT_SECRET", "test-jwt-secret-at-least-32-chars!!")
    monkeypatch.setenv("SESSION_SECRET", "test-session-secret")
    monkeypatch.setenv("FRONTEND_ORIGIN", "http://127.0.0.1:5173")
    monkeypatch.setenv("COOKIE_NAME", "le_session")
    monkeypatch.setenv("COOKIE_SECURE", "false")
    monkeypatch.setenv("BOOTSTRAP_ADMIN_EMAILS", "admin@example.com")
    clear_auth_settings_cache()
    clear_user_repository_cache()
    return tmp_db_path
