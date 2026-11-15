from __future__ import annotations

from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from app.auth.mobile_return import clear_auth_codes
from app.auth.oauth import ensure_google_client, oauth
from app.auth.settings import AuthSettings


def test_callback_redirects_to_allowlisted_https_localhost(
    client: TestClient,
    auth_settings: AuthSettings,
) -> None:
    assert ensure_google_client(auth_settings)
    fake_token = {
        "userinfo": {
            "sub": "google-sub-mobile",
            "email": "mobile@example.com",
            "name": "Mobile",
        }
    }

    with patch.object(
        oauth.google,
        "authorize_access_token",
        new=AsyncMock(return_value=fake_token),
    ):
        # Seed session return_to via login first.
        async def fake_create_authorization_url(self, redirect_uri, **kwargs):  # noqa: ANN001
            return {
                "url": f"https://accounts.google.com/o/oauth2/v2/auth?redirect_uri={redirect_uri}",
                "state": "test-state",
            }

        with patch(
            "authlib.integrations.starlette_client.StarletteOAuth2App.create_authorization_url",
            new=fake_create_authorization_url,
        ):
            login = client.get(
                "/auth/google/login",
                params={"return_to": "https://localhost/"},
                follow_redirects=False,
            )
            assert login.status_code in {302, 307}

        response = client.get("/auth/google/callback", follow_redirects=False)

    assert response.status_code == 302
    assert response.headers["location"] == "https://localhost/"
    assert f"{auth_settings.cookie_name}=" in response.headers.get("set-cookie", "")


def test_callback_rejects_unallowlisted_return_to_uses_frontend_origin(
    client: TestClient,
    auth_settings: AuthSettings,
) -> None:
    assert ensure_google_client(auth_settings)
    fake_token = {
        "userinfo": {
            "sub": "google-sub-evil",
            "email": "evil@example.com",
            "name": "Evil",
        }
    }

    async def fake_create_authorization_url(self, redirect_uri, **kwargs):  # noqa: ANN001
        return {
            "url": f"https://accounts.google.com/o/oauth2/v2/auth?redirect_uri={redirect_uri}",
            "state": "test-state",
        }

    with patch(
        "authlib.integrations.starlette_client.StarletteOAuth2App.create_authorization_url",
        new=fake_create_authorization_url,
    ):
        client.get(
            "/auth/google/login",
            params={"return_to": "https://evil.example/phish"},
            follow_redirects=False,
        )

    with patch.object(
        oauth.google,
        "authorize_access_token",
        new=AsyncMock(return_value=fake_token),
    ):
        response = client.get("/auth/google/callback", follow_redirects=False)

    assert response.status_code == 302
    assert response.headers["location"] == auth_settings.frontend_origin


def test_custom_scheme_return_issues_code_and_exchange_sets_cookie(
    client: TestClient,
    auth_settings: AuthSettings,
) -> None:
    clear_auth_codes()
    assert ensure_google_client(auth_settings)
    fake_token = {
        "userinfo": {
            "sub": "google-sub-deeplink",
            "email": "deeplink@example.com",
            "name": "Deep",
        }
    }
    return_to = "com.learnenglish.app://auth/callback"

    async def fake_create_authorization_url(self, redirect_uri, **kwargs):  # noqa: ANN001
        return {
            "url": f"https://accounts.google.com/o/oauth2/v2/auth?redirect_uri={redirect_uri}",
            "state": "test-state",
        }

    with patch(
        "authlib.integrations.starlette_client.StarletteOAuth2App.create_authorization_url",
        new=fake_create_authorization_url,
    ):
        client.get(
            "/auth/google/login",
            params={"return_to": return_to},
            follow_redirects=False,
        )

    with patch.object(
        oauth.google,
        "authorize_access_token",
        new=AsyncMock(return_value=fake_token),
    ):
        response = client.get("/auth/google/callback", follow_redirects=False)

    assert response.status_code == 302
    location = response.headers["location"]
    assert location.startswith(return_to)
    assert "code=" in location
    code = location.split("code=", 1)[1].split("&", 1)[0]

    exchange = client.post("/auth/exchange", json={"code": code})
    assert exchange.status_code == 200
    assert exchange.json()["status"] == "ok"
    set_cookie = exchange.headers.get("set-cookie", "")
    assert f"{auth_settings.cookie_name}=" in set_cookie

    me = client.get("/auth/me")
    assert me.status_code == 200
    assert me.json()["email"] == "deeplink@example.com"

    # One-time use.
    again = client.post("/auth/exchange", json={"code": code})
    assert again.status_code == 400


def test_exchange_rejects_unknown_code(client: TestClient) -> None:
    response = client.post("/auth/exchange", json={"code": "not-a-real-code"})
    assert response.status_code == 400
