from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import jwt
from fastapi import HTTPException, Request, Response, status

from app.auth.settings import AuthSettings
from app.users.roles import Role


def create_session_token(
    *,
    settings: AuthSettings,
    sub: str,
    email: str,
    name: str | None = None,
    role: Role | None = None,
) -> str:
    now = datetime.now(UTC)
    payload: dict[str, Any] = {
        "sub": sub,
        "email": email,
        "iat": now,
        "exp": now + timedelta(seconds=settings.cookie_max_age),
    }
    if name:
        payload["name"] = name
    if role:
        payload["role"] = role
    return jwt.encode(payload, settings.jwt_secret, algorithm="HS256")


def decode_session_token(token: str, settings: AuthSettings) -> dict[str, Any]:
    try:
        return jwt.decode(token, settings.jwt_secret, algorithms=["HS256"])
    except jwt.PyJWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired session",
        ) from exc


def set_session_cookie(response: Response, settings: AuthSettings, token: str) -> None:
    response.set_cookie(
        key=settings.cookie_name,
        value=token,
        max_age=settings.cookie_max_age,
        httponly=True,
        secure=settings.cookie_secure,
        samesite=settings.cookie_samesite,  # type: ignore[arg-type]
        path="/",
    )


def clear_session_cookie(response: Response, settings: AuthSettings) -> None:
    response.delete_cookie(
        key=settings.cookie_name,
        path="/",
        secure=settings.cookie_secure,
        httponly=True,
        samesite=settings.cookie_samesite,  # type: ignore[arg-type]
    )


def current_identity_from_request(
    request: Request, settings: AuthSettings
) -> dict[str, Any]:
    token = request.cookies.get(settings.cookie_name)
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
        )
    claims = decode_session_token(token, settings)
    email = claims.get("email")
    sub = claims.get("sub")
    if not email or not sub:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid session payload",
        )
    return {
        "sub": sub,
        "email": email,
        "name": claims.get("name"),
        "role": claims.get("role"),
    }


# Back-compat alias used by older tests / callers
def current_user_from_request(request: Request, settings: AuthSettings) -> dict[str, Any]:
    return current_identity_from_request(request, settings)
