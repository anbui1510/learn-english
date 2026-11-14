from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.auth.deps import require_editor
from app.cases.repository import CaseRecord
from app.cases.service import get_case_repository
from app.users.repository import UserRecord

router = APIRouter(prefix="/editor", tags=["editor"])


class EditorPingOut(BaseModel):
    status: str
    role: str
    user_id: int


class CaseCreateIn(BaseModel):
    title: str = Field(min_length=1)
    isbn: str | None = None
    edition: str | None = None


class CaseOut(BaseModel):
    id: int
    owner_user_id: int
    title: str
    status: str
    isbn: str | None
    edition: str | None
    created_at: str
    updated_at: str


def _case_out(case: CaseRecord) -> CaseOut:
    return CaseOut(
        id=case.id,
        owner_user_id=case.owner_user_id,
        title=case.title,
        status=case.status,
        isbn=case.isbn,
        edition=case.edition,
        created_at=case.created_at,
        updated_at=case.updated_at,
    )


@router.get("/ping", response_model=EditorPingOut)
def editor_ping(
    user: Annotated[UserRecord, Depends(require_editor)],
) -> EditorPingOut:
    """Lightweight editor-only route for RBAC matrix verification."""
    return EditorPingOut(status="ok", role=user.role, user_id=user.id)


@router.post("/cases", response_model=CaseOut, status_code=201)
def create_case(
    body: CaseCreateIn,
    user: Annotated[UserRecord, Depends(require_editor)],
) -> CaseOut:
    case = get_case_repository().create_case(
        owner=user,
        title=body.title,
        isbn=body.isbn,
        edition=body.edition,
    )
    return _case_out(case)


@router.get("/cases", response_model=list[CaseOut])
def list_my_cases(
    user: Annotated[UserRecord, Depends(require_editor)],
) -> list[CaseOut]:
    return [
        _case_out(case)
        for case in get_case_repository().list_for_owner(user.id)
    ]
