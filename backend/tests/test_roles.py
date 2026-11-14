from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.auth.jwt_tokens import create_session_token
from app.auth.settings import AuthSettings, get_auth_settings
from app.main import create_app
from app.users.service import bootstrap_admin_emails, get_user_repository


@pytest.fixture
def auth_settings(auth_env: str) -> AuthSettings:
    return get_auth_settings()


@pytest.fixture
def client(auth_settings: AuthSettings) -> TestClient:
    return TestClient(create_app(auth_settings))


def _session_for(client: TestClient, settings: AuthSettings, user) -> None:  # noqa: ANN001
    token = create_session_token(
        settings=settings,
        sub=user.google_sub,
        email=user.email,
        name=user.name,
        role=user.role,
    )
    client.cookies.set(settings.cookie_name, token)


def test_bootstrap_admin_and_default_learner(auth_settings: AuthSettings) -> None:
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
    assert admin.role == "admin"
    assert learner.role == "learner"


def test_admin_assigns_editor_not_admin(
    client: TestClient, auth_settings: AuthSettings
) -> None:
    repo = get_user_repository()
    admin = repo.upsert_google_user(
        google_sub="sub-admin",
        email="admin@example.com",
        name="Admin",
        bootstrap_admin_emails=bootstrap_admin_emails(),
    )
    target = repo.upsert_google_user(
        google_sub="sub-target",
        email="doctor@example.com",
        name="Doctor",
        bootstrap_admin_emails=bootstrap_admin_emails(),
    )
    assert target.role == "learner"

    _session_for(client, auth_settings, admin)
    response = client.patch(
        f"/admin/users/{target.id}/role",
        json={"role": "editor"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["role"] == "editor"
    assert body["email"] == "doctor@example.com"
    assert body["role"] != "admin"

    refreshed = repo.get_by_id(target.id)
    assert refreshed is not None
    assert refreshed.role == "editor"

    audit = client.get(f"/admin/users/{target.id}/role-audit")
    assert audit.status_code == 200
    rows = audit.json()
    assert any(
        row["old_role"] == "learner"
        and row["new_role"] == "editor"
        and row["actor_user_id"] == admin.id
        for row in rows
    )

    # Target session sees editor from DB (source of truth)
    _session_for(client, auth_settings, refreshed)
    me = client.get("/auth/me")
    assert me.status_code == 200
    assert me.json()["role"] == "editor"
    assert me.json()["role"] != "admin"


def test_non_admin_cannot_assign_roles(
    client: TestClient, auth_settings: AuthSettings
) -> None:
    repo = get_user_repository()
    learner = repo.upsert_google_user(
        google_sub="sub-learner",
        email="learner@example.com",
        name="Learner",
        bootstrap_admin_emails=bootstrap_admin_emails(),
    )
    target = repo.upsert_google_user(
        google_sub="sub-target",
        email="other@example.com",
        name="Other",
        bootstrap_admin_emails=bootstrap_admin_emails(),
    )

    _session_for(client, auth_settings, learner)
    forbidden = client.patch(
        f"/admin/users/{target.id}/role",
        json={"role": "editor"},
    )
    assert forbidden.status_code == 403

    listed = client.get("/admin/users")
    assert listed.status_code == 403

    still = repo.get_by_id(target.id)
    assert still is not None
    assert still.role == "learner"


def test_editor_is_not_admin(client: TestClient, auth_settings: AuthSettings) -> None:
    repo = get_user_repository()
    admin = repo.upsert_google_user(
        google_sub="sub-admin",
        email="admin@example.com",
        name="Admin",
        bootstrap_admin_emails=bootstrap_admin_emails(),
    )
    editor = repo.upsert_google_user(
        google_sub="sub-editor",
        email="editor@example.com",
        name="Editor",
        bootstrap_admin_emails=bootstrap_admin_emails(),
    )
    _session_for(client, auth_settings, admin)
    client.patch(f"/admin/users/{editor.id}/role", json={"role": "editor"})
    editor = repo.get_by_id(editor.id)
    assert editor is not None
    assert editor.role == "editor"

    _session_for(client, auth_settings, editor)
    assert client.get("/admin/users").status_code == 403
    me = client.get("/auth/me")
    assert me.json()["role"] == "editor"
