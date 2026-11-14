"""RBAC role matrix for editor-only APIs (US-G1-003).

Matrix (GET /editor/ping):
| role      | expected |
|-----------|----------|
| anonymous | 401      |
| learner   | 403      |
| editor    | 200      |
| admin     | 200      |
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.auth.jwt_tokens import create_session_token
from app.auth.settings import AuthSettings, get_auth_settings
from app.main import create_app
from app.users.roles import parse_role
from app.users.service import bootstrap_admin_emails, get_user_repository


@pytest.fixture
def auth_settings(auth_env: str) -> AuthSettings:
    return get_auth_settings()


@pytest.fixture
def client(auth_settings: AuthSettings) -> TestClient:
    return TestClient(create_app(auth_settings))


def _login(client: TestClient, settings: AuthSettings, *, sub: str, email: str, role: str):
    repo = get_user_repository()
    user = repo.upsert_google_user(
        google_sub=sub,
        email=email,
        name=email.split("@")[0],
        bootstrap_admin_emails=bootstrap_admin_emails(),
    )
    if user.role != role:
        # Force role for matrix rows when bootstrap did not already set it.
        admin = repo.upsert_google_user(
            google_sub="matrix-admin",
            email="admin@example.com",
            name="Admin",
            bootstrap_admin_emails=bootstrap_admin_emails(),
        )
        user = repo.set_role(
            user_id=user.id,
            new_role=parse_role(role),
            actor_user_id=admin.id,
        )
    token = create_session_token(
        settings=settings,
        sub=user.google_sub,
        email=user.email,
        name=user.name,
        role=user.role,
    )
    client.cookies.set(settings.cookie_name, token)
    return user


def test_rbac_matrix_anonymous_401(client: TestClient) -> None:
    assert client.get("/editor/ping").status_code == 401


def test_rbac_matrix_learner_403(
    client: TestClient, auth_settings: AuthSettings
) -> None:
    _login(
        client,
        auth_settings,
        sub="sub-learner",
        email="learner@example.com",
        role="learner",
    )
    response = client.get("/editor/ping")
    assert response.status_code == 403
    assert "editor" in response.json()["detail"].lower()


def test_rbac_matrix_editor_200(
    client: TestClient, auth_settings: AuthSettings
) -> None:
    user = _login(
        client,
        auth_settings,
        sub="sub-editor",
        email="editor@example.com",
        role="editor",
    )
    response = client.get("/editor/ping")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["role"] == "editor"
    assert body["user_id"] == user.id


def test_rbac_matrix_admin_200(
    client: TestClient, auth_settings: AuthSettings
) -> None:
    user = _login(
        client,
        auth_settings,
        sub="sub-admin",
        email="admin@example.com",
        role="admin",
    )
    response = client.get("/editor/ping")
    assert response.status_code == 200
    assert response.json()["role"] == "admin"
    assert response.json()["user_id"] == user.id
