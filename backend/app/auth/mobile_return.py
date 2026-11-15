"""Allowlisted OAuth return URLs and one-time codes for Capacitor deep links."""

from __future__ import annotations

import base64
import hashlib
import re
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

# RFC 7636: code_verifier 43–128; S256 challenge is base64url(SHA256) without padding.
_CHALLENGE_RE = re.compile(r"^[A-Za-z0-9_-]{43}$")
_VERIFIER_RE = re.compile(r"^[A-Za-z0-9._~-]{43,128}$")


@dataclass(frozen=True)
class AuthCodeRecord:
    session_jwt: str
    expires_at: float
    code_challenge: str | None


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


def is_valid_code_challenge(challenge: str | None) -> bool:
    return bool(challenge and _CHALLENGE_RE.fullmatch(challenge))


def is_valid_code_verifier(verifier: str | None) -> bool:
    return bool(verifier and _VERIFIER_RE.fullmatch(verifier))


def pkce_challenge_s256(code_verifier: str) -> str:
    digest = hashlib.sha256(code_verifier.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")


def issue_auth_code(
    session_jwt: str, *, code_challenge: str | None = None
) -> str:
    code = secrets.token_urlsafe(32)
    with _LOCK:
        _CODES[code] = AuthCodeRecord(
            session_jwt=session_jwt,
            expires_at=time.time() + _CODE_TTL_SECONDS,
            code_challenge=code_challenge,
        )
    return code


def consume_auth_code(
    code: str, *, code_verifier: str | None = None
) -> str | None:
    """Return session JWT when code is valid.

    When the issued code was bound to a PKCE challenge, ``code_verifier`` must
    match. A wrong verifier does **not** consume the code (legitimate app can
    retry); expiry still cleans it up.
    """
    now = time.time()
    with _LOCK:
        expired = [k for k, v in _CODES.items() if v.expires_at <= now]
        for key in expired:
            del _CODES[key]
        record = _CODES.get(code)
        if record is None or record.expires_at <= now:
            _CODES.pop(code, None)
            return None
        if record.code_challenge:
            if not is_valid_code_verifier(code_verifier):
                return None
            assert code_verifier is not None
            if not secrets.compare_digest(
                pkce_challenge_s256(code_verifier), record.code_challenge
            ):
                return None
        del _CODES[code]
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
