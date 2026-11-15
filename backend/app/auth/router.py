from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field

from app.auth.deps import get_current_user
from app.auth.jwt_tokens import (
    clear_session_cookie,
    create_session_token,
    current_identity_from_request,
    set_session_cookie,
)
from app.auth.mobile_return import (
    append_query_param,
    consume_auth_code,
    is_allowed_return_to,
    issue_auth_code,
    needs_auth_code_handoff,
    resolve_post_auth_redirect,
)
from app.auth.oauth import ensure_google_client, oauth
from app.auth.settings import get_auth_settings
from app.users.repository import UserRecord
from app.users.service import bootstrap_admin_emails, get_user_repository

router = APIRouter(prefix="/auth", tags=["auth"])

_SESSION_RETURN_KEY = "oauth_return_to"


class ExchangeBody(BaseModel):
    code: str = Field(min_length=8, max_length=256)


@router.get("/google/login")
async def google_login(
    request: Request,
    return_to: str | None = None,
) -> RedirectResponse:
    settings = get_auth_settings()
    if not ensure_google_client(settings):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Google OAuth is not configured",
        )
    if return_to and is_allowed_return_to(settings, return_to):
        request.session[_SESSION_RETURN_KEY] = return_to.strip()
    else:
        request.session.pop(_SESSION_RETURN_KEY, None)
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
    return_to = request.session.pop(_SESSION_RETURN_KEY, None)
    redirect_url = resolve_post_auth_redirect(settings, return_to)

    if needs_auth_code_handoff(redirect_url):
        code = issue_auth_code(session_jwt)
        redirect_url = append_query_param(redirect_url, "code", code)
        return RedirectResponse(url=redirect_url, status_code=302)

    response = RedirectResponse(url=redirect_url, status_code=302)
    set_session_cookie(response, settings, session_jwt)
    return response


@router.post("/exchange")
async def exchange_auth_code(body: ExchangeBody, response: Response) -> dict[str, str]:
    settings = get_auth_settings()
    session_jwt = consume_auth_code(body.code.strip())
    if not session_jwt:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired auth code",
        )
    set_session_cookie(response, settings, session_jwt)
    return {"status": "ok"}


@router.get("/me")
async def me(
    request: Request,
    response: Response,
    user: Annotated[UserRecord, Depends(get_current_user)],
) -> dict[str, str | int | None]:
    settings = get_auth_settings()
    identity = current_identity_from_request(request, settings)
    # DB is source of truth; refresh cookie when JWT role claim is stale.
    if identity.get("role") != user.role:
        token = create_session_token(
            settings=settings,
            sub=user.google_sub,
            email=user.email,
            name=user.name,
            role=user.role,
        )
        set_session_cookie(response, settings, token)

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
