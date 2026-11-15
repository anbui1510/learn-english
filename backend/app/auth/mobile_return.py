"""Allowlisted OAuth return URLs and one-time codes for Capacitor deep links."""

from __future__ import annotations

import secrets
import time
from dataclasses import dataclass
from threading import Lock
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from app.auth.settings import AuthSettings

_DEFAULT_MOBILE_RETURN_URIS = (
    "https://localhost/",
    "https://localhost",
    "capacitor://localhost/",
    "capacitor://localhost",
    "com.learnenglish.app://auth/callback",
)


@dataclass(frozen=True)
class AuthCodeRecord:
    session_jwt: str
    expires_at: float


_CODES: dict[str, AuthCodeRecord] = {}
_LOCK = Lock()
_CODE_TTL_SECONDS = 120


def mobile_return_allowlist(settings: AuthSettings) -> tuple[str, ...]:
    return tuple(
        dict.fromkeys(
            [
                *settings.frontend_origins,
                *settings.mobile_auth_return_uris,
                *_DEFAULT_MOBILE_RETURN_URIS,
            ]
        )
    )


def _normalize_for_compare(url: str) -> str:
    parts = urlsplit(url.strip())
    path = parts.path or "/"
    if path != "/" and path.endswith("/"):
        path = path.rstrip("/")
    # Drop query/fragment for allowlist membership.
    return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), path, "", ""))


def is_allowed_return_to(settings: AuthSettings, return_to: str | None) -> bool:
    if not return_to or not return_to.strip():
        return False
    candidate = _normalize_for_compare(return_to)
    allowed = {_normalize_for_compare(u) for u in mobile_return_allowlist(settings)}
    return candidate in allowed


def resolve_post_auth_redirect(
    settings: AuthSettings, return_to: str | None
) -> str:
    if return_to and is_allowed_return_to(settings, return_to):
        return return_to.strip()
    return settings.frontend_origin


def needs_auth_code_handoff(return_to: str) -> bool:
    """Custom schemes (and non-http(s)) cannot receive Set-Cookie; use a code."""
    scheme = urlsplit(return_to).scheme.lower()
    return scheme not in {"http", "https"}


def issue_auth_code(session_jwt: str) -> str:
    code = secrets.token_urlsafe(32)
    with _LOCK:
        _CODES[code] = AuthCodeRecord(
            session_jwt=session_jwt,
            expires_at=time.time() + _CODE_TTL_SECONDS,
        )
    return code


def consume_auth_code(code: str) -> str | None:
    now = time.time()
    with _LOCK:
        # Opportunistic cleanup.
        expired = [k for k, v in _CODES.items() if v.expires_at <= now]
        for key in expired:
            del _CODES[key]
        record = _CODES.pop(code, None)
    if record is None or record.expires_at <= now:
        return None
    return record.session_jwt


def append_query_param(url: str, key: str, value: str) -> str:
    parts = urlsplit(url)
    query = dict(parse_qsl(parts.query, keep_blank_values=True))
    query[key] = value
    return urlunsplit(
        (parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment)
    )


def clear_auth_codes() -> None:
    with _LOCK:
        _CODES.clear()
