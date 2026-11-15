from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    File,
    Form,
    HTTPException,
    Query,
    UploadFile,
    status,
)
from pydantic import BaseModel, Field

from app.auth.deps import get_current_user, require_editor
from app.auth.settings import get_auth_settings
from app.cases.repository import CaseRecord
from app.cases.service import get_case_repository
from app.facts.extract import background_extract
from app.facts.repository import FactRecord
from app.facts.service import get_fact_repository
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
    extract_status: str = "none"
    extract_error: str | None = None
    extract_started_at: str | None = None
    extract_finished_at: str | None = None
    created_at: str
    updated_at: str


class DownloadUrlOut(BaseModel):
    url: str
    expires_in: int


class ExtractStartOut(BaseModel):
    case_id: int
    extract_status: str
    message: str


class FactOut(BaseModel):
    id: int
    case_id: int
    source_quote: str
    atomic_fact: str
    category: str
    status: str
    page: int
    chapter: str | None = None
    section: str | None = None
    isbn: str
    edition: str
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
        pdf_object_key=case.pdf_object_key,
        pdf_byte_size=case.pdf_byte_size,
        extract_status=case.extract_status,
        extract_error=case.extract_error,
        extract_started_at=case.extract_started_at,
        extract_finished_at=case.extract_finished_at,
        created_at=case.created_at,
        updated_at=case.updated_at,
    )


def _fact_out(fact: FactRecord) -> FactOut:
    return FactOut(
        id=fact.id,
        case_id=fact.case_id,
        source_quote=fact.source_quote,
        atomic_fact=fact.atomic_fact,
        category=fact.category,
        status=fact.status,
        page=fact.page,
        chapter=fact.chapter,
        section=fact.section,
        isbn=fact.isbn,
        edition=fact.edition,
        created_at=fact.created_at,
        updated_at=fact.updated_at,
    )


def _can_access_case(user: UserRecord, case: CaseRecord) -> bool:
    return user.role == "admin" or case.owner_user_id == user.id


def _require_case_access(user: UserRecord, case_id: int) -> CaseRecord:
    case = get_case_repository().get_by_id(case_id)
    if case is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Case not found")
    if not _can_access_case(user, case):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not allowed to access this case",
        )
    return case


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


@router.get("/cases/{case_id}", response_model=CaseOut)
def get_case(
    case_id: int,
    user: Annotated[UserRecord, Depends(require_editor)],
) -> CaseOut:
    return _case_out(_require_case_access(user, case_id))


@router.post("/cases/{case_id}/extract", response_model=ExtractStartOut)
def start_extract(
    case_id: int,
    background_tasks: BackgroundTasks,
    user: Annotated[UserRecord, Depends(require_editor)],
) -> ExtractStartOut:
    case = _require_case_access(user, case_id)
    if not case.pdf_object_key:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Case has no PDF object",
        )
    if not case.isbn or not case.edition:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Case ISBN and edition are required before extract",
        )
    if case.extract_status in {"queued", "running"}:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Extract already {case.extract_status}",
        )

    updated = get_case_repository().set_extract_status(
        case_id, status="queued", error=None
    )
    background_tasks.add_task(background_extract, case_id)
    return ExtractStartOut(
        case_id=updated.id,
        extract_status=updated.extract_status,
        message="Extraction queued",
    )


@router.get("/cases/{case_id}/facts", response_model=list[FactOut])
def list_case_facts(
    case_id: int,
    user: Annotated[UserRecord, Depends(require_editor)],
    status_filter: Annotated[str | None, Query(alias="status")] = None,
    category: Annotated[str | None, Query()] = None,
) -> list[FactOut]:
    _require_case_access(user, case_id)
    if status_filter is not None and status_filter not in {
        "needs_review",
        "verified",
    }:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="status must be needs_review or verified",
        )
    facts = get_fact_repository().list_for_case(
        case_id,
        status=status_filter,
        category=category,
    )
    return [_fact_out(fact) for fact in facts]


@router.get("/cases/{case_id}/download-url", response_model=DownloadUrlOut)
def case_download_url(
    case_id: int,
    user: Annotated[UserRecord, Depends(require_editor)],
) -> DownloadUrlOut:
    settings = get_auth_settings()
    case = _require_case_access(user, case_id)
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
