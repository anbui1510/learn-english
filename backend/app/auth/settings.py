from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv

_ENV_FILE = Path(__file__).resolve().parents[2] / ".env"
load_dotenv(_ENV_FILE)

_DEFAULT_DB = Path(__file__).resolve().parents[2] / "data" / "learn_english.sqlite3"


@dataclass(frozen=True)
class AuthSettings:
    google_client_id: str
    google_client_secret: str
    google_redirect_uri: str
    jwt_secret: str
    session_secret: str
    frontend_origin: str
    cookie_name: str
    cookie_secure: bool
    cookie_max_age: int
    cookie_samesite: str
    database_path: str
    bootstrap_admin_emails: str

    @property
    def oauth_configured(self) -> bool:
        return bool(
            self.google_client_id
            and self.google_client_secret
            and self.jwt_secret
            and self.session_secret
        )


def _env(name: str, default: str = "") -> str:
    return os.getenv(name, default).strip()


@lru_cache
def get_auth_settings() -> AuthSettings:
    return AuthSettings(
        google_client_id=_env("GOOGLE_CLIENT_ID"),
        google_client_secret=_env("GOOGLE_CLIENT_SECRET"),
        google_redirect_uri=_env(
            "GOOGLE_REDIRECT_URI",
            "http://127.0.0.1:8000/auth/google/callback",
        ),
        jwt_secret=_env("JWT_SECRET"),
        session_secret=_env("SESSION_SECRET") or _env("JWT_SECRET"),
        frontend_origin=_env("FRONTEND_ORIGIN", "http://127.0.0.1:5173"),
        cookie_name=_env("COOKIE_NAME", "le_session"),
        cookie_secure=_env("COOKIE_SECURE", "false").lower() in {"1", "true", "yes"},
        cookie_max_age=int(_env("COOKIE_MAX_AGE", "86400")),
        cookie_samesite=_env("COOKIE_SAMESITE", "lax").lower(),
        database_path=_env("DATABASE_PATH", str(_DEFAULT_DB)),
        bootstrap_admin_emails=_env("BOOTSTRAP_ADMIN_EMAILS"),
    )


def clear_auth_settings_cache() -> None:
    get_auth_settings.cache_clear()
