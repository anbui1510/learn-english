from __future__ import annotations

import sqlite3
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field

from app.auth.deps import require_admin
from app.learner.service import get_pa_rate_limiter
from app.users.repository import UserRecord
from app.users.roles import ROLES, Role, parse_role
from app.users.service import get_user_repository

router = APIRouter(prefix="/admin", tags=["admin"])


class UserOut(BaseModel):
    id: int
    email: str
    name: str | None
    role: Role
    google_sub: str


class RoleUpdate(BaseModel):
    role: Literal["admin", "editor", "learner"] = Field(
        description="Role to assign"
    )


class RoleAuditOut(BaseModel):
    id: int
    user_id: int
    actor_user_id: int | None
    old_role: str | None
    new_role: str
    created_at: str


def _to_out(user: UserRecord) -> UserOut:
    return UserOut(
        id=user.id,
        email=user.email,
        name=user.name,
        role=user.role,
        google_sub=user.google_sub,
    )


@router.get("/users", response_model=list[UserOut])
def list_users(
    _: Annotated[UserRecord, Depends(require_admin)],
) -> list[UserOut]:
    return [_to_out(u) for u in get_user_repository().list_users()]


@router.patch("/users/{user_id}/role", response_model=UserOut)
def assign_role(
    user_id: int,
    body: RoleUpdate,
    admin: Annotated[UserRecord, Depends(require_admin)],
) -> UserOut:
    try:
        role = parse_role(body.role)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"role must be one of {list(ROLES)}",
        ) from exc

    repo = get_user_repository()
    try:
        updated = repo.set_role(
            user_id=user_id,
            new_role=role,
            actor_user_id=admin.id,
        )
    except KeyError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        ) from exc
    return _to_out(updated)


class PaUsageOut(BaseModel):
    user_id: int
    email: str | None
    usage_day: str
    score_count: int
    estimated_cost_usd: float


@router.get("/pa-usage", response_model=list[PaUsageOut])
def pa_usage_report(
    _: Annotated[UserRecord, Depends(require_admin)],
    days: Annotated[int, Query(ge=1, le=90)] = 14,
) -> list[PaUsageOut]:
    """Daily pronunciation score calls per user (Azure cost control log)."""
    rows = get_pa_rate_limiter().usage_report(days=days)
    return [
        PaUsageOut(
            user_id=row.user_id,
            email=row.email,
            usage_day=row.usage_day,
            score_count=row.score_count,
            estimated_cost_usd=row.estimated_cost_usd,
        )
        for row in rows
    ]


class BookSourceOut(BaseModel):
    id: int
    slug: str
    title: str
    publisher: str | None = None
    default_isbn: str | None = None
    notes: str | None = None
    created_at: str
    updated_at: str


class BookSourceCreateIn(BaseModel):
    slug: str = Field(min_length=1, max_length=80)
    title: str = Field(min_length=1, max_length=200)
    publisher: str | None = None
    default_isbn: str | None = None
    notes: str | None = None


class BookSourcePatchIn(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    publisher: str | None = None
    default_isbn: str | None = None
    notes: str | None = None
    clear_publisher: bool = False
    clear_default_isbn: bool = False
    clear_notes: bool = False


def _book_out(source) -> BookSourceOut:
    return BookSourceOut(
        id=source.id,
        slug=source.slug,
        title=source.title,
        publisher=source.publisher,
        default_isbn=source.default_isbn,
        notes=source.notes,
        created_at=source.created_at,
        updated_at=source.updated_at,
    )


class TtsSettingsOut(BaseModel):
    provider: Literal["synthetic", "edge", "azure", "elevenlabs"]
    premium_enabled: bool
    updated_at: str | None = None
    notes: str = (
        "Premium providers (azure/elevenlabs) require premium_enabled=true "
        "and matching API keys in env."
    )


class TtsSettingsPatchIn(BaseModel):
    provider: Literal["synthetic", "edge", "azure", "elevenlabs"] | None = None
    premium_enabled: bool | None = None


@router.get("/tts-settings", response_model=TtsSettingsOut)
def get_tts_settings(
    _: Annotated[UserRecord, Depends(require_admin)],
) -> TtsSettingsOut:
    from app.org_settings.service import get_tts_org_settings

    settings = get_tts_org_settings()
    return TtsSettingsOut(
        provider=settings.provider,  # type: ignore[arg-type]
        premium_enabled=settings.premium_enabled,
        updated_at=settings.updated_at,
    )


@router.patch("/tts-settings", response_model=TtsSettingsOut)
def patch_tts_settings(
    body: TtsSettingsPatchIn,
    _: Annotated[UserRecord, Depends(require_admin)],
) -> TtsSettingsOut:
    from app.org_settings.service import get_org_settings_repository

    try:
        updated = get_org_settings_repository().set_tts(
            provider=body.provider,
            premium_enabled=body.premium_enabled,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
        ) from exc
    return TtsSettingsOut(
        provider=updated.provider,  # type: ignore[arg-type]
        premium_enabled=updated.premium_enabled,
        updated_at=updated.updated_at,
    )


@router.get("/book-sources", response_model=list[BookSourceOut])
def list_book_sources(
    _: Annotated[UserRecord, Depends(require_admin)],
) -> list[BookSourceOut]:
    from app.books.service import get_book_source_repository

    return [_book_out(s) for s in get_book_source_repository().list_sources()]


@router.post("/book-sources", response_model=BookSourceOut, status_code=201)
def create_book_source(
    body: BookSourceCreateIn,
    _: Annotated[UserRecord, Depends(require_admin)],
) -> BookSourceOut:
    from app.books.service import get_book_source_repository

    try:
        created = get_book_source_repository().create(
            slug=body.slug,
            title=body.title,
            publisher=body.publisher,
            default_isbn=body.default_isbn,
            notes=body.notes,
        )
    except sqlite3.IntegrityError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Book source slug already exists",
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
        ) from exc
    return _book_out(created)


@router.patch("/book-sources/{source_id}", response_model=BookSourceOut)
def patch_book_source(
    source_id: int,
    body: BookSourcePatchIn,
    _: Annotated[UserRecord, Depends(require_admin)],
) -> BookSourceOut:
    from app.books.service import get_book_source_repository

    try:
        updated = get_book_source_repository().update(
            source_id,
            title=body.title,
            publisher=body.publisher,
            default_isbn=body.default_isbn,
            notes=body.notes,
            clear_publisher=body.clear_publisher,
            clear_default_isbn=body.clear_default_isbn,
            clear_notes=body.clear_notes,
        )
    except KeyError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Book source not found"
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
        ) from exc
    return _book_out(updated)


@router.get("/users/{user_id}/role-audit", response_model=list[RoleAuditOut])
def role_audit(
    user_id: int,
    _: Annotated[UserRecord, Depends(require_admin)],
) -> list[RoleAuditOut]:
    repo = get_user_repository()
    if repo.get_by_id(user_id) is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )
    return [
        RoleAuditOut(
            id=row.id,
            user_id=row.user_id,
            actor_user_id=row.actor_user_id,
            old_role=row.old_role,
            new_role=row.new_role,
            created_at=row.created_at,
        )
        for row in repo.list_role_audit(user_id)
    ]
