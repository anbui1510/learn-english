from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from pydantic import BaseModel, Field

from app.auth.deps import get_current_user, require_editor
from app.auth.settings import get_auth_settings
from app.cases.repository import CaseRecord
from app.cases.service import get_case_repository
from app.storage.factory import get_storage
from app.users.repository import UserRecord

router = APIRouter(prefix="/editor", tags=["editor"])

PDF_MIME = "application/pdf"


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
    pdf_object_key: str | None = None
    pdf_byte_size: int | None = None
    created_at: str
    updated_at: str


class DownloadUrlOut(BaseModel):
    url: str
    expires_in: int


def _case_out(case: CaseRecord) -> CaseOut:
    return CaseOut(
        id=case.id,
        owner_user_id=case.owner_user_id,
        title=case.title,
        status=case.status,
        isbn=case.isbn,
        edition=case.edition,
        pdf_object_key=case.pdf_object_key,
        pdf_byte_size=case.pdf_byte_size,
        created_at=case.created_at,
        updated_at=case.updated_at,
    )


def _can_access_case(user: UserRecord, case: CaseRecord) -> bool:
    return user.role == "admin" or case.owner_user_id == user.id


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


@router.post("/cases/upload", response_model=CaseOut, status_code=201)
async def upload_case_pdf(
    user: Annotated[UserRecord, Depends(require_editor)],
    title: Annotated[str, Form(min_length=1)],
    isbn: Annotated[str, Form(min_length=1)],
    edition: Annotated[str, Form(min_length=1)],
    file: Annotated[UploadFile, File()],
) -> CaseOut:
    settings = get_auth_settings()
    content_type = (file.content_type or "").split(";")[0].strip().lower()
    filename = (file.filename or "").lower()
    if content_type != PDF_MIME and not filename.endswith(".pdf"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only application/pdf uploads are allowed",
        )

    data = await file.read()
    if not data:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Empty PDF upload",
        )
    if len(data) > settings.pdf_max_bytes:
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail=f"PDF exceeds max size of {settings.pdf_max_bytes} bytes",
        )

    object_key = f"cases/{user.id}/{uuid.uuid4().hex}.pdf"
    stored = get_storage().put(object_key, data, content_type=PDF_MIME)
    case = get_case_repository().create_case(
        owner=user,
        title=title,
        isbn=isbn.strip(),
        edition=edition.strip(),
        pdf_object_key=stored.key,
        pdf_content_type=stored.content_type,
        pdf_byte_size=stored.size,
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


@router.get("/cases/{case_id}/download-url", response_model=DownloadUrlOut)
def case_download_url(
    case_id: int,
    user: Annotated[UserRecord, Depends(require_editor)],
) -> DownloadUrlOut:
    settings = get_auth_settings()
    case = get_case_repository().get_by_id(case_id)
    if case is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Case not found")
    if not _can_access_case(user, case):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not allowed to download this case PDF",
        )
    if not case.pdf_object_key:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Case has no PDF object",
        )
    ttl = settings.signed_url_ttl_seconds
    url = get_storage().signed_url(case.pdf_object_key, expires_in=ttl)
    return DownloadUrlOut(url=url, expires_in=ttl)


@router.get("/cases/{case_id}/pdf")
def stream_case_pdf(
    case_id: int,
    user: Annotated[UserRecord, Depends(get_current_user)],
):
    """Session-authenticated PDF stream for owner/admin (learners 403)."""
    from fastapi.responses import Response

    if user.role not in {"editor", "admin"}:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Editor role required",
        )
    case = get_case_repository().get_by_id(case_id)
    if case is None or not case.pdf_object_key:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Case PDF not found")
    if not _can_access_case(user, case):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not allowed to download this case PDF",
        )
    data = get_storage().get(case.pdf_object_key)
    return Response(
        content=data,
        media_type=case.pdf_content_type or PDF_MIME,
        headers={
            "Content-Disposition": f'inline; filename="case-{case.id}.pdf"',
        },
    )
