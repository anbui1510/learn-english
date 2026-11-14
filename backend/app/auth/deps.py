from __future__ import annotations

from typing import Annotated

from fastapi import Depends, HTTPException, Request, status

from app.auth.jwt_tokens import current_identity_from_request
from app.auth.settings import AuthSettings, get_auth_settings
from app.users.repository import UserRecord
from app.users.service import bootstrap_admin_emails, get_user_repository


def get_settings() -> AuthSettings:
    return get_auth_settings()


def get_current_user(
    request: Request,
    settings: Annotated[AuthSettings, Depends(get_settings)],
) -> UserRecord:
    identity = current_identity_from_request(request, settings)
    repo = get_user_repository()
    user = repo.get_by_google_sub(identity["sub"])
    if user is None:
        # Session exists but DB was reset — re-upsert from JWT identity.
        user = repo.upsert_google_user(
            google_sub=identity["sub"],
            email=identity["email"],
            name=identity.get("name"),
            bootstrap_admin_emails=bootstrap_admin_emails(),
        )
    return user


def require_admin(
    user: Annotated[UserRecord, Depends(get_current_user)],
) -> UserRecord:
    if user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin role required",
        )
    return user


def require_editor(
    user: Annotated[UserRecord, Depends(get_current_user)],
) -> UserRecord:
    """Editor-only routes: editors and admins allowed; learners get 403."""
    if user.role not in {"editor", "admin"}:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Editor role required",
        )
    return user
