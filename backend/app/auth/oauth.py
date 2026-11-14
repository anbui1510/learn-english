from __future__ import annotations

from authlib.integrations.starlette_client import OAuth

from app.auth.settings import AuthSettings

oauth = OAuth()
_registered_for: tuple[str, str] | None = None


def ensure_google_client(settings: AuthSettings) -> bool:
    """Register Google OIDC client when credentials are present. Returns True if ready."""
    global _registered_for

    if not settings.oauth_configured:
        return False

    fingerprint = (settings.google_client_id, settings.google_client_secret)
    if _registered_for != fingerprint:
        oauth.register(
            name="google",
            client_id=settings.google_client_id,
            client_secret=settings.google_client_secret,
            server_metadata_url=(
                "https://accounts.google.com/.well-known/openid-configuration"
            ),
            client_kwargs={"scope": "openid email profile"},
            overwrite=True,
        )
        _registered_for = fingerprint
    return True


def reset_oauth_registration() -> None:
    global _registered_for
    _registered_for = None
