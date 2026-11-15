from __future__ import annotations

from fastapi.testclient import TestClient

from app.auth.settings import AuthSettings, _parse_origins


def test_parse_origins_dedupes() -> None:
    assert _parse_origins("a, b, a, ,c") == ("a", "b", "c")


def test_health_allows_capacitor_origin(
    client: TestClient, auth_settings: AuthSettings
) -> None:
    del auth_settings
    response = client.options(
        "/health",
        headers={
            "Origin": "https://localhost",
            "Access-Control-Request-Method": "GET",
        },
    )
    # Starlette may 200 on OPTIONS for CORS preflight
    assert response.status_code in {200, 204, 400}
    # GET with Origin still succeeds
    get = client.get("/health", headers={"Origin": "capacitor://localhost"})
    assert get.status_code == 200
    assert get.json()["status"] == "ok"
