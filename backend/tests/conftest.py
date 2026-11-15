from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.auth.jwt_tokens import create_session_token
from app.auth.oauth import reset_oauth_registration
from app.auth.settings import AuthSettings, clear_auth_settings_cache, get_auth_settings
from app.cases.service import clear_case_repository_cache
from app.dialogues.service import clear_dialogue_repository_cache
from app.facts.service import clear_fact_repository_cache
from app.learner.service import clear_learner_caches
from app.main import create_app
from app.speech.service import clear_utterance_repository_cache
from app.storage.factory import clear_storage_cache
from app.users.repository import UserRecord
from app.users.roles import Role
from app.users.service import clear_user_repository_cache


def _clear_all_caches() -> None:
    clear_auth_settings_cache()
    clear_user_repository_cache()
    clear_case_repository_cache()
    clear_fact_repository_cache()
    clear_dialogue_repository_cache()
    clear_utterance_repository_cache()
    clear_learner_caches()
    clear_storage_cache()
    reset_oauth_registration()


@pytest.fixture(autouse=True)
def _reset_caches() -> None:
    _clear_all_caches()
    yield
    _clear_all_caches()


@pytest.fixture
def tmp_db_path(tmp_path, monkeypatch: pytest.MonkeyPatch) -> str:
    db_path = str(tmp_path / "test.sqlite3")
    storage_root = str(tmp_path / "objects")
    monkeypatch.setenv("DATABASE_PATH", db_path)
    monkeypatch.setenv("STORAGE_ROOT", storage_root)
    monkeypatch.delenv("GCS_BUCKET", raising=False)
    _clear_all_caches()
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
    monkeypatch.setenv("API_PUBLIC_BASE_URL", "http://testserver")
    monkeypatch.setenv("PDF_MAX_BYTES", str(1024 * 1024))
    monkeypatch.setenv("SIGNED_URL_TTL_SECONDS", "300")
    _clear_all_caches()
    return tmp_db_path


@pytest.fixture
def auth_settings(auth_env: str) -> AuthSettings:
    return get_auth_settings()


@pytest.fixture
def client(auth_settings: AuthSettings) -> TestClient:
    return TestClient(create_app(auth_settings))


def set_session_cookie(
    client: TestClient,
    settings: AuthSettings,
    user: UserRecord,
    *,
    role_override: Role | None = None,
) -> None:
    """Attach an httpOnly session cookie for the given user (tests)."""
    token = create_session_token(
        settings=settings,
        sub=user.google_sub,
        email=user.email,
        name=user.name,
        role=role_override if role_override is not None else user.role,
    )
    client.cookies.set(settings.cookie_name, token)
