from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.auth.jwt_tokens import create_session_token
from app.auth.oauth import reset_oauth_registration
from app.auth.settings import AuthSettings, clear_auth_settings_cache, get_auth_settings
from app.cases.service import clear_case_repository_cache
from app.main import create_app
from app.storage.factory import clear_storage_cache
from app.users.repository import UserRecord
from app.users.roles import Role
from app.users.service import bootstrap_admin_emails, clear_user_repository_cache, get_user_repository


def _clear_all_caches() -> None:
    clear_auth_settings_cache()
    clear_user_repository_cache()
    clear_case_repository_cache()
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


def seed_admin_editor_learner(
    _auth_settings: AuthSettings,
) -> tuple[UserRecord, UserRecord, UserRecord]:
    """Create bootstrap admin, an editor, and a learner for integration tests."""
    repo = get_user_repository()
    admin = repo.upsert_google_user(
        google_sub="sub-admin",
        email="admin@example.com",
        name="Admin",
        bootstrap_admin_emails=bootstrap_admin_emails(),
    )
    learner = repo.upsert_google_user(
        google_sub="sub-learner",
        email="learner@example.com",
        name="Learner",
        bootstrap_admin_emails=bootstrap_admin_emails(),
    )
    editor = repo.upsert_google_user(
        google_sub="sub-editor",
        email="editor@example.com",
        name="Editor",
        bootstrap_admin_emails=bootstrap_admin_emails(),
    )
    editor = repo.set_role(
        user_id=editor.id, new_role="editor", actor_user_id=admin.id
    )
    return admin, editor, learner


MINIMAL_PDF = b"%PDF-1.4\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF\n"
