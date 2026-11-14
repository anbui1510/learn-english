from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.responses import RedirectResponse

from app.auth.deps import get_current_user
from app.auth.jwt_tokens import (
    clear_session_cookie,
    create_session_token,
    set_session_cookie,
)
from app.auth.oauth import ensure_google_client, oauth
from app.auth.settings import get_auth_settings
from app.users.repository import UserRecord
from app.users.service import bootstrap_admin_emails, get_user_repository

router = APIRouter(prefix="/auth", tags=["auth"])


@router.get("/google/login")
async def google_login(request: Request) -> RedirectResponse:
    settings = get_auth_settings()
    if not ensure_google_client(settings):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Google OAuth is not configured",
        )
    return await oauth.google.authorize_redirect(request, settings.google_redirect_uri)


@router.get("/google/callback")
async def google_callback(request: Request) -> RedirectResponse:
    settings = get_auth_settings()
    if not ensure_google_client(settings):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Google OAuth is not configured",
        )

    try:
        token = await oauth.google.authorize_access_token(request)
    except Exception as exc:  # Authlib raises assorted OAuth errors
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Google OAuth callback failed",
        ) from exc

    userinfo = token.get("userinfo") or {}
    sub = userinfo.get("sub")
    email = userinfo.get("email")
    if not sub or not email:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Google account did not return email identity",
        )

    user = get_user_repository().upsert_google_user(
        google_sub=sub,
        email=email,
        name=userinfo.get("name"),
        bootstrap_admin_emails=bootstrap_admin_emails(),
    )
    session_jwt = create_session_token(
        settings=settings,
        sub=user.google_sub,
        email=user.email,
        name=user.name,
        role=user.role,
    )
    response = RedirectResponse(url=settings.frontend_origin, status_code=302)
    set_session_cookie(response, settings, session_jwt)
    return response


@router.get("/me")
async def me(
    user: Annotated[UserRecord, Depends(get_current_user)],
) -> dict[str, str | int | None]:
    return {
        "id": user.id,
        "sub": user.google_sub,
        "email": user.email,
        "name": user.name,
        "role": user.role,
    }


@router.post("/logout")
async def logout(response: Response) -> dict[str, str]:
    settings = get_auth_settings()
    clear_session_cookie(response, settings)
    return {"status": "logged_out"}
