from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from app.auth.jwt_tokens import create_session_token
from app.auth.oauth import reset_oauth_registration
from app.auth.settings import AuthSettings, clear_auth_settings_cache
from app.main import create_app
from app.users.service import clear_user_repository_cache


@pytest.fixture
def unconfigured_client(
    tmp_db_path: str, monkeypatch: pytest.MonkeyPatch
) -> TestClient:
    monkeypatch.delenv("GOOGLE_CLIENT_ID", raising=False)
    monkeypatch.delenv("GOOGLE_CLIENT_SECRET", raising=False)
    monkeypatch.delenv("JWT_SECRET", raising=False)
    monkeypatch.delenv("SESSION_SECRET", raising=False)
    clear_auth_settings_cache()
    clear_user_repository_cache()
    reset_oauth_registration()
    return TestClient(create_app())


def test_login_fails_closed_without_oauth_config(unconfigured_client: TestClient) -> None:
    response = unconfigured_client.get("/auth/google/login", follow_redirects=False)
    assert response.status_code == 503
    assert "not configured" in response.json()["detail"].lower()


def test_me_anonymous_returns_401(client: TestClient) -> None:
    response = client.get("/auth/me")
    assert response.status_code == 401


def test_logout_clears_session(client: TestClient, auth_settings: AuthSettings) -> None:
    token = create_session_token(
        settings=auth_settings,
        sub="google-sub-1",
        email="resident@example.com",
        name="Resident",
        role="learner",
    )
    client.cookies.set(auth_settings.cookie_name, token)

    me_before = client.get("/auth/me")
    assert me_before.status_code == 200
    body = me_before.json()
    assert body["email"] == "resident@example.com"
    assert body["role"] == "learner"

    logout = client.post("/auth/logout")
    assert logout.status_code == 200
    assert logout.json()["status"] == "logged_out"

    client.cookies.clear()
    me_after = client.get("/auth/me")
    assert me_after.status_code == 401


def test_callback_sets_httpOnly_cookie_and_redirects(
    client: TestClient,
    auth_settings: AuthSettings,
) -> None:
    from app.auth.oauth import ensure_google_client, oauth

    assert ensure_google_client(auth_settings)
    fake_token = {
        "userinfo": {
            "sub": "google-sub-42",
            "email": "learner@example.com",
            "name": "Learner",
        }
    }

    with patch.object(
        oauth.google,
        "authorize_access_token",
        new=AsyncMock(return_value=fake_token),
    ):
        response = client.get("/auth/google/callback", follow_redirects=False)

    assert response.status_code == 302
    assert response.headers["location"] == auth_settings.frontend_origin

    set_cookie = response.headers.get("set-cookie", "")
    assert f"{auth_settings.cookie_name}=" in set_cookie
    assert "HttpOnly" in set_cookie
    assert "samesite=lax" in set_cookie.lower()

    client.cookies.set(
        auth_settings.cookie_name,
        response.cookies[auth_settings.cookie_name],
    )
    me = client.get("/auth/me")
    assert me.status_code == 200
    body = me.json()
    assert body["sub"] == "google-sub-42"
    assert body["email"] == "learner@example.com"
    assert body["name"] == "Learner"
    assert body["role"] == "learner"


def test_login_redirects_to_google_when_configured(client: TestClient) -> None:
    async def fake_create_authorization_url(self, redirect_uri, **kwargs):  # noqa: ANN001
        return {
            "url": (
                "https://accounts.google.com/o/oauth2/v2/auth"
                f"?client_id=test-client-id&redirect_uri={redirect_uri}"
            ),
            "state": "test-state",
        }

    with patch(
        "authlib.integrations.starlette_client.StarletteOAuth2App.create_authorization_url",
        new=fake_create_authorization_url,
    ):
        response = client.get("/auth/google/login", follow_redirects=False)

    assert response.status_code in {302, 307}
    location = response.headers.get("location", "")
    assert "accounts.google.com" in location
