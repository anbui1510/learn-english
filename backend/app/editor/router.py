from __future__ import annotations

import uuid
from typing import Annotated, Any, Literal

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
from jsonschema.exceptions import ValidationError
from pydantic import BaseModel, Field

from app.auth.deps import get_current_user, require_editor
from app.auth.settings import get_auth_settings
from app.cases.access import PDF_MIME, can_access_case
from app.cases.repository import CaseRecord
from app.cases.service import get_case_repository
from app.dialogues.generate import GenerateError, generate_for_case
from app.dialogues.generator import CONTEXTS, CefrLevel, DialogueContext
from app.dialogues.generator import get_default_generator
from app.dialogues.repository import DialogueRecord
from app.dialogues.service import get_dialogue_repository
from app.facts.extract import background_extract
from app.facts.repository import FactRecord, FactStatus
from app.facts.service import get_fact_repository
from app.speech.service import get_utterance_repository
from app.speech.synthesize import synthesize_dialogue
from app.storage.factory import get_storage
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
    book_source_id: int | None = None


class CaseOut(BaseModel):
    id: int
    owner_user_id: int
    title: str
    status: str
    isbn: str | None
    edition: str | None
    book_source_id: int | None = None
    book_source_slug: str | None = None
    pdf_object_key: str | None = None
    pdf_byte_size: int | None = None
    extract_status: str = "none"
    extract_error: str | None = None
    extract_started_at: str | None = None
    extract_finished_at: str | None = None
    published_at: str | None = None
    published_by_user_id: int | None = None
    module_slug: str | None = None
    unlock_cme_points: int = 0
    unlock_rank: str | None = None
    unlock_requires_case_id: int | None = None
    unlock_requires_streak_days: int = 0
    created_at: str
    updated_at: str


class BookSourceOut(BaseModel):
    id: int
    slug: str
    title: str
    publisher: str | None = None
    default_isbn: str | None = None
    notes: str | None = None


class CaseProgressionIn(BaseModel):
    module_slug: str | None = None
    unlock_cme_points: int | None = Field(default=None, ge=0)
    unlock_rank: str | None = None
    unlock_requires_case_id: int | None = None
    clear_unlock_requires_case: bool = False
    unlock_requires_streak_days: int | None = Field(default=None, ge=0, le=30)


class FactPatchIn(BaseModel):
    status: FactStatus | None = None
    source_quote: str | None = Field(default=None, min_length=1)
    atomic_fact: str | None = Field(default=None, min_length=1)
    category: str | None = Field(default=None, min_length=1)


class GenerateDialoguesIn(BaseModel):
    contexts: list[DialogueContext] = Field(min_length=1, max_length=3)
    cefr_level: CefrLevel = "B1"
    include_vi: bool = False
    session_kind: Literal["standard", "presentation"] = "standard"
    target_seconds: float | None = Field(default=None, ge=60, le=1200)


class DialogueOut(BaseModel):
    id: int
    case_id: int
    context: str
    cefr_level: str
    estimated_seconds: float
    duration_warning: bool
    lines: list[dict[str, Any]]
    created_at: str


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
    from app.books.service import get_book_source_repository

    slug = None
    if case.book_source_id is not None:
        source = get_book_source_repository().get(case.book_source_id)
        slug = source.slug if source else None
    return CaseOut(
        id=case.id,
        owner_user_id=case.owner_user_id,
        title=case.title,
        status=case.status,
        isbn=case.isbn,
        edition=case.edition,
        book_source_id=case.book_source_id,
        book_source_slug=slug,
        pdf_object_key=case.pdf_object_key,
        pdf_byte_size=case.pdf_byte_size,
        extract_status=case.extract_status,
        extract_error=case.extract_error,
        extract_started_at=case.extract_started_at,
        extract_finished_at=case.extract_finished_at,
        published_at=case.published_at,
        published_by_user_id=case.published_by_user_id,
        module_slug=case.module_slug,
        unlock_cme_points=case.unlock_cme_points,
        unlock_rank=case.unlock_rank,
        unlock_requires_case_id=case.unlock_requires_case_id,
        unlock_requires_streak_days=case.unlock_requires_streak_days,
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


def _dialogue_out(record: DialogueRecord) -> DialogueOut:
    return DialogueOut(
        id=record.id,
        case_id=record.case_id,
        context=record.context,
        cefr_level=record.cefr_level,
        estimated_seconds=record.estimated_seconds,
        duration_warning=record.duration_warning,
        lines=list(record.payload.get("lines") or []),
        created_at=record.created_at,
    )


def _require_case_access(user: UserRecord, case_id: int) -> CaseRecord:
    case = get_case_repository().get_by_id(case_id)
    if case is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Case not found")
    if not can_access_case(user, case):
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


def _require_book_source(book_source_id: int | None) -> int | None:
    if book_source_id is None:
        return None
    from app.books.service import get_book_source_repository

    if get_book_source_repository().get(book_source_id) is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Unknown book_source_id",
        )
    return book_source_id


@router.get("/book-sources", response_model=list[BookSourceOut])
def list_book_sources_for_editor(
    _: Annotated[UserRecord, Depends(require_editor)],
) -> list[BookSourceOut]:
    from app.books.service import get_book_source_repository

    return [
        BookSourceOut(
            id=s.id,
            slug=s.slug,
            title=s.title,
            publisher=s.publisher,
            default_isbn=s.default_isbn,
            notes=s.notes,
        )
        for s in get_book_source_repository().list_sources()
    ]


@router.post("/cases", response_model=CaseOut, status_code=201)
def create_case(
    body: CaseCreateIn,
    user: Annotated[UserRecord, Depends(require_editor)],
) -> CaseOut:
    book_source_id = _require_book_source(body.book_source_id)
    case = get_case_repository().create_case(
        owner=user,
        title=body.title,
        isbn=body.isbn,
        edition=body.edition,
        book_source_id=book_source_id,
    )
    return _case_out(case)


@router.post("/cases/upload", response_model=CaseOut, status_code=201)
async def upload_case_pdf(
    user: Annotated[UserRecord, Depends(require_editor)],
    title: Annotated[str, Form(min_length=1)],
    isbn: Annotated[str, Form(min_length=1)],
    edition: Annotated[str, Form(min_length=1)],
    file: Annotated[UploadFile, File()],
    book_source_id: Annotated[int | None, Form()] = None,
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
        book_source_id=_require_book_source(book_source_id),
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


@router.patch("/cases/{case_id}/progression", response_model=CaseOut)
def patch_case_progression(
    case_id: int,
    body: CaseProgressionIn,
    user: Annotated[UserRecord, Depends(require_editor)],
) -> CaseOut:
    from app.learner.progression import RANK_LADDER, would_create_unlock_cycle

    case = _require_case_access(user, case_id)
    if body.unlock_rank is not None and body.unlock_rank not in {
        rid for rid, _, _ in RANK_LADDER
    }:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Unknown unlock_rank",
        )
    if body.unlock_requires_case_id is not None:
        prereq = get_case_repository().get_by_id(body.unlock_requires_case_id)
        if prereq is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Prerequisite case not found",
            )
    edges = get_case_repository().unlock_edges()
    next_req = (
        None
        if body.clear_unlock_requires_case
        else (
            body.unlock_requires_case_id
            if body.unlock_requires_case_id is not None
            else case.unlock_requires_case_id
        )
    )
    if would_create_unlock_cycle(
        case_id=case_id,
        requires_case_id=next_req,
        edges=edges,
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Unlock prerequisite would create a cycle",
        )
    updated = get_case_repository().set_progression(
        case_id=case_id,
        module_slug=body.module_slug,
        unlock_cme_points=body.unlock_cme_points,
        unlock_rank=body.unlock_rank,
        unlock_requires_case_id=body.unlock_requires_case_id,
        clear_unlock_requires_case=body.clear_unlock_requires_case,
        unlock_requires_streak_days=body.unlock_requires_streak_days,
    )
    return _case_out(updated)


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
        "rejected",
    }:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="status must be needs_review, verified, or rejected",
        )
    facts = get_fact_repository().list_for_case(
        case_id,
        status=status_filter,
        category=category,
    )
    return [_fact_out(fact) for fact in facts]


@router.patch("/cases/{case_id}/facts/{fact_id}", response_model=FactOut)
def patch_case_fact(
    case_id: int,
    fact_id: int,
    body: FactPatchIn,
    user: Annotated[UserRecord, Depends(require_editor)],
) -> FactOut:
    _require_case_access(user, case_id)
    if (
        body.status is None
        and body.source_quote is None
        and body.atomic_fact is None
        and body.category is None
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="At least one field is required",
        )
    facts = get_fact_repository()
    existing = facts.get_by_id(fact_id)
    if existing is None or existing.case_id != case_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Fact not found")
    try:
        updated = facts.update_fact(
            fact_id=fact_id,
            actor_user_id=user.id,
            status=body.status,
            source_quote=body.source_quote,
            atomic_fact=body.atomic_fact,
            category=body.category,
        )
    except ValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=exc.message,
        ) from exc
    return _fact_out(updated)


@router.post("/cases/{case_id}/publish", response_model=CaseOut)
def publish_case(
    case_id: int,
    user: Annotated[UserRecord, Depends(require_editor)],
) -> CaseOut:
    _require_case_access(user, case_id)
    counts = get_fact_repository().count_by_status(case_id)
    needs_review = counts.get("needs_review", 0)
    verified = counts.get("verified", 0)
    if needs_review > 0:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Cannot publish while {needs_review} fact(s) still need review",
        )
    if verified < 1:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Cannot publish without at least one verified fact",
        )
    published = get_case_repository().publish(case_id=case_id, publisher=user)
    return _case_out(published)


@router.post(
    "/cases/{case_id}/generate-dialogues",
    response_model=list[DialogueOut],
)
def generate_dialogues(
    case_id: int,
    body: GenerateDialoguesIn,
    user: Annotated[UserRecord, Depends(require_editor)],
) -> list[DialogueOut]:
    case = _require_case_access(user, case_id)
    if case.status != "published":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Case must be published before generate-dialogues",
        )
    # Deduplicate while preserving order
    seen: set[str] = set()
    contexts: list[DialogueContext] = []
    for ctx in body.contexts:
        if ctx in CONTEXTS and ctx not in seen:
            seen.add(ctx)
            contexts.append(ctx)
    if not contexts:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Select at least one valid context",
        )
    settings = get_auth_settings()
    try:
        created = generate_for_case(
            case=case,
            contexts=contexts,
            cefr_level=body.cefr_level,
            include_vi=body.include_vi,
            facts=get_fact_repository(),
            dialogues=get_dialogue_repository(),
            generator=get_default_generator(settings.gemini_api_key),
            session_kind=body.session_kind,
            target_seconds=body.target_seconds,
        )
    except GenerateError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc
    except ValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=exc.message,
        ) from exc
    return [_dialogue_out(item) for item in created]


@router.get("/cases/{case_id}/dialogues", response_model=list[DialogueOut])
def list_case_dialogues(
    case_id: int,
    user: Annotated[UserRecord, Depends(require_editor)],
) -> list[DialogueOut]:
    _require_case_access(user, case_id)
    return [
        _dialogue_out(item)
        for item in get_dialogue_repository().list_for_case(case_id)
    ]


class UtteranceOut(BaseModel):
    id: int
    dialogue_id: int
    line_index: int
    speaker: str
    voice: str
    object_key: str
    duration_ms: int
    timestamps: list[dict[str, Any]]


@router.post(
    "/cases/{case_id}/dialogues/{dialogue_id}/synthesize",
    response_model=list[UtteranceOut],
)
def synthesize_case_dialogue(
    case_id: int,
    dialogue_id: int,
    user: Annotated[UserRecord, Depends(require_editor)],
) -> list[UtteranceOut]:
    _require_case_access(user, case_id)
    dialogue = get_dialogue_repository().get_by_id(dialogue_id)
    if dialogue is None or dialogue.case_id != case_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Dialogue not found"
        )
    try:
        created = synthesize_dialogue(
            dialogue=dialogue,
            utterances=get_utterance_repository(),
            storage=get_storage(),
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
        ) from exc
    return [
        UtteranceOut(
            id=item.id,
            dialogue_id=item.dialogue_id,
            line_index=item.line_index,
            speaker=item.speaker,
            voice=item.voice,
            object_key=item.object_key,
            duration_ms=item.duration_ms,
            timestamps=item.timestamps,
        )
        for item in created
    ]


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
    if not can_access_case(user, case):
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
