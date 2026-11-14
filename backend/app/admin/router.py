from __future__ import annotations

from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from app.auth.deps import require_admin
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
