from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Literal

from dotenv import load_dotenv

_ENV_FILE = Path(__file__).resolve().parents[2] / ".env"
load_dotenv(_ENV_FILE)

_DEFAULT_DB = Path(__file__).resolve().parents[2] / "data" / "learn_english.sqlite3"
_DEFAULT_STORAGE = Path(__file__).resolve().parents[2] / "data" / "objects"

SameSite = Literal["lax", "strict", "none"]


@dataclass(frozen=True)
class AuthSettings:
    google_client_id: str
    google_client_secret: str
    google_redirect_uri: str
    jwt_secret: str
    session_secret: str
    frontend_origin: str
    frontend_origins: tuple[str, ...]
    mobile_auth_return_uris: tuple[str, ...]
    cookie_name: str
    cookie_secure: bool
    cookie_max_age: int
    cookie_samesite: SameSite
    database_path: str
    bootstrap_admin_emails: str
    storage_root: str
    gcs_bucket: str
    gcs_location: str
    api_public_base_url: str
    pdf_max_bytes: int
    signed_url_ttl_seconds: int
    gemini_api_key: str
    use_edge_tts: bool
    azure_speech_key: str
    azure_speech_region: str
    use_azure_pa: bool
    pa_daily_limit: int
    pa_cost_per_score_usd: float
    use_gemini_empathy: bool
    elevenlabs_api_key: str
    elevenlabs_voice_id: str
    tts_provider_default: str

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


def _parse_samesite(value: str) -> SameSite:
    normalized = value.lower()
    if normalized == "strict":
        return "strict"
    if normalized == "none":
        return "none"
    return "lax"


def _parse_origins(value: str) -> tuple[str, ...]:
    parts = [p.strip() for p in value.split(",") if p.strip()]
    # Always include primary FRONTEND_ORIGIN when list is built from env later.
    return tuple(dict.fromkeys(parts))


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
        frontend_origin=(
            primary := _env("FRONTEND_ORIGIN", "http://127.0.0.1:5173")
        ),
        frontend_origins=tuple(
            dict.fromkeys(
                [
                    primary,
                    *_parse_origins(
                        _env(
                            "FRONTEND_ORIGINS",
                            # Capacitor Android: https://localhost; iOS: capacitor://localhost
                            "http://localhost:5173,https://localhost,"
                            "capacitor://localhost,ionic://localhost",
                        )
                    ),
                ]
            )
        ),
        mobile_auth_return_uris=_parse_origins(
            _env(
                "MOBILE_AUTH_RETURN_URIS",
                "https://localhost/,com.learnenglish.app://auth/callback",
            )
        ),
        cookie_name=_env("COOKIE_NAME", "le_session"),
        cookie_secure=_env("COOKIE_SECURE", "false").lower() in {"1", "true", "yes"},
        cookie_max_age=int(_env("COOKIE_MAX_AGE", "86400")),
        cookie_samesite=_parse_samesite(_env("COOKIE_SAMESITE", "lax")),
        database_path=_env("DATABASE_PATH", str(_DEFAULT_DB)),
        bootstrap_admin_emails=_env("BOOTSTRAP_ADMIN_EMAILS"),
        storage_root=_env("STORAGE_ROOT", str(_DEFAULT_STORAGE)),
        gcs_bucket=_env("GCS_BUCKET"),
        gcs_location=_env("GCS_LOCATION", "asia-southeast1"),
        api_public_base_url=_env("API_PUBLIC_BASE_URL", "http://127.0.0.1:8000"),
        pdf_max_bytes=int(_env("PDF_MAX_BYTES", str(25 * 1024 * 1024))),
        signed_url_ttl_seconds=int(_env("SIGNED_URL_TTL_SECONDS", "300")),
        gemini_api_key=_env("GEMINI_API_KEY"),
        use_edge_tts=_env("USE_EDGE_TTS", "false").lower() in {"1", "true", "yes"},
        azure_speech_key=_env("AZURE_SPEECH_KEY"),
        azure_speech_region=_env("AZURE_SPEECH_REGION", "eastasia"),
        use_azure_pa=_env("USE_AZURE_PA", "false").lower() in {"1", "true", "yes"},
        pa_daily_limit=int(_env("PA_DAILY_LIMIT", "50")),
        pa_cost_per_score_usd=float(_env("PA_COST_PER_SCORE_USD", "0.0")),
        use_gemini_empathy=_env("USE_GEMINI_EMPATHY", "false").lower()
        in {"1", "true", "yes"},
        elevenlabs_api_key=_env("ELEVENLABS_API_KEY"),
        elevenlabs_voice_id=_env(
            "ELEVENLABS_VOICE_ID", "21m00Tcm4TlvDq8ikWAM"
        ),
        tts_provider_default=_env("TTS_PROVIDER", "synthetic").lower(),
    )


def clear_auth_settings_cache() -> None:
    get_auth_settings.cache_clear()
