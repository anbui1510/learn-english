from __future__ import annotations

import uuid
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from pydantic import BaseModel, Field

from app.auth.deps import require_learner_access
from app.auth.settings import get_auth_settings
from app.cases.service import get_case_repository
from app.dialogues.service import get_dialogue_repository
from app.facts.service import get_fact_repository
from app.learner.profiles import CefrPackage
from app.learner.service import (
    get_learner_profile_repository,
    get_learning_attempt_repository,
)
from app.learner.shadowing import build_shadowing_cards
from app.speech.service import get_utterance_repository
from app.speech.synthesize import synthesize_dialogue
from app.storage.factory import get_storage
from app.users.repository import UserRecord

router = APIRouter(prefix="/learner", tags=["learner"])


class PublishedCaseOut(BaseModel):
    id: int
    title: str
    isbn: str | None
    edition: str | None
    published_at: str | None


class ProfileOut(BaseModel):
    user_id: int
    lessons_per_week: int
    cefr_package: str
    path_months: int


class ProfilePatchIn(BaseModel):
    lessons_per_week: int | None = Field(default=None, ge=1, le=14)
    cefr_package: CefrPackage | None = None
    path_months: int | None = Field(default=None, ge=6, le=6)


class PlaylistItemOut(BaseModel):
    line_index: int
    speaker: str
    voice: str
    text: str
    text_vi: str | None = None
    audio_url: str
    duration_ms: int
    timestamps: list[dict[str, Any]]
    fact_ids: list[str]


class LessonOut(BaseModel):
    case_id: int
    dialogue_id: int
    title: str
    context: str
    cefr_level: str
    isbn: str | None
    edition: str | None
    citation_pages: list[int]
    lines: list[dict[str, Any]]
    playlist: list[PlaylistItemOut]


class ShadowingOut(BaseModel):
    dialogue_id: int
    cards: list[dict[str, Any]]


class CompletionIn(BaseModel):
    dialogue_id: int


class CompletionOut(BaseModel):
    id: int
    case_id: int
    dialogue_id: int
    completed_at: str


class AttemptOut(BaseModel):
    id: int
    case_id: int
    dialogue_id: int
    mode: str
    audio_object_key: str
    created_at: str


@router.get("/cases", response_model=list[PublishedCaseOut])
def list_published_cases(
    _user: Annotated[UserRecord, Depends(require_learner_access)],
) -> list[PublishedCaseOut]:
    return [
        PublishedCaseOut(
            id=case.id,
            title=case.title,
            isbn=case.isbn,
            edition=case.edition,
            published_at=case.published_at,
        )
        for case in get_case_repository().list_published()
    ]


class LearnerDialogueOut(BaseModel):
    id: int
    case_id: int
    context: str
    cefr_level: str


@router.get("/cases/{case_id}/dialogues", response_model=list[LearnerDialogueOut])
def list_published_case_dialogues(
    case_id: int,
    _user: Annotated[UserRecord, Depends(require_learner_access)],
) -> list[LearnerDialogueOut]:
    case = get_case_repository().get_by_id(case_id)
    if case is None or case.status != "published":
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Published case not found"
        )
    return [
        LearnerDialogueOut(
            id=item.id,
            case_id=item.case_id,
            context=item.context,
            cefr_level=item.cefr_level,
        )
        for item in get_dialogue_repository().list_for_case(case_id)
    ]


@router.get("/profile", response_model=ProfileOut)
def get_profile(
    user: Annotated[UserRecord, Depends(require_learner_access)],
) -> ProfileOut:
    profile = get_learner_profile_repository().get_or_create(user.id)
    return ProfileOut(
        user_id=profile.user_id,
        lessons_per_week=profile.lessons_per_week,
        cefr_package=profile.cefr_package,
        path_months=profile.path_months,
    )


@router.patch("/profile", response_model=ProfileOut)
def patch_profile(
    body: ProfilePatchIn,
    user: Annotated[UserRecord, Depends(require_learner_access)],
) -> ProfileOut:
    try:
        profile = get_learner_profile_repository().update(
            user.id,
            lessons_per_week=body.lessons_per_week,
            cefr_package=body.cefr_package,
            path_months=body.path_months,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
        ) from exc
    return ProfileOut(
        user_id=profile.user_id,
        lessons_per_week=profile.lessons_per_week,
        cefr_package=profile.cefr_package,
        path_months=profile.path_months,
    )


def _require_published_dialogue(dialogue_id: int):
    dialogue = get_dialogue_repository().get_by_id(dialogue_id)
    if dialogue is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Dialogue not found")
    case = get_case_repository().get_by_id(dialogue.case_id)
    if case is None or case.status != "published":
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Published case not found for dialogue",
        )
    return case, dialogue


@router.get("/dialogues/{dialogue_id}/lesson", response_model=LessonOut)
def get_lesson(
    dialogue_id: int,
    _user: Annotated[UserRecord, Depends(require_learner_access)],
) -> LessonOut:
    settings = get_auth_settings()
    case, dialogue = _require_published_dialogue(dialogue_id)
    utterances = get_utterance_repository().list_for_dialogue(dialogue_id)
    if not utterances:
        # Lazy synthesize on first learner open (MVP convenience).
        utterances = synthesize_dialogue(
            dialogue=dialogue,
            utterances=get_utterance_repository(),
            storage=get_storage(),
        )
    lines = list(dialogue.payload.get("lines") or [])
    pages: list[int] = []
    for fact in get_fact_repository().list_for_case(case.id, status="verified"):
        pages.append(fact.page)
    playlist: list[PlaylistItemOut] = []
    for utt in utterances:
        line = lines[utt.line_index] if utt.line_index < len(lines) else {}
        playlist.append(
            PlaylistItemOut(
                line_index=utt.line_index,
                speaker=utt.speaker,
                voice=utt.voice,
                text=str(line.get("text") or ""),
                text_vi=line.get("text_vi"),
                audio_url=get_storage().signed_url(
                    utt.object_key, expires_in=settings.signed_url_ttl_seconds
                ),
                duration_ms=utt.duration_ms,
                timestamps=utt.timestamps,
                fact_ids=list(line.get("fact_ids") or []),
            )
        )
    return LessonOut(
        case_id=case.id,
        dialogue_id=dialogue.id,
        title=case.title,
        context=dialogue.context,
        cefr_level=dialogue.cefr_level,
        isbn=case.isbn,
        edition=case.edition,
        citation_pages=sorted(set(pages)),
        lines=lines,
        playlist=playlist,
    )


@router.get("/dialogues/{dialogue_id}/shadowing", response_model=ShadowingOut)
def get_shadowing(
    dialogue_id: int,
    _user: Annotated[UserRecord, Depends(require_learner_access)],
) -> ShadowingOut:
    _, dialogue = _require_published_dialogue(dialogue_id)
    lines = list(dialogue.payload.get("lines") or [])
    cards = build_shadowing_cards(lines, target=10)
    assert len(cards) == 10
    return ShadowingOut(dialogue_id=dialogue_id, cards=cards)


@router.post("/completions", response_model=CompletionOut)
def complete_lesson(
    body: CompletionIn,
    user: Annotated[UserRecord, Depends(require_learner_access)],
) -> CompletionOut:
    case, dialogue = _require_published_dialogue(body.dialogue_id)
    row = get_learner_profile_repository().mark_complete(
        user_id=user.id, case_id=case.id, dialogue_id=dialogue.id
    )
    return CompletionOut(
        id=row.id,
        case_id=row.case_id,
        dialogue_id=row.dialogue_id,
        completed_at=row.completed_at,
    )


@router.post("/attempts/audio", response_model=AttemptOut, status_code=201)
async def upload_attempt_audio(
    user: Annotated[UserRecord, Depends(require_learner_access)],
    dialogue_id: Annotated[int, Form()],
    mode: Annotated[Literal["shadowing", "role_play"], Form()],
    file: Annotated[UploadFile, File()],
) -> AttemptOut:
    case, dialogue = _require_published_dialogue(dialogue_id)
    data = await file.read()
    if not data:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Empty audio upload"
        )
    content_type = (file.content_type or "application/octet-stream").split(";")[0]
    key = f"attempts/{user.id}/{dialogue.id}/{uuid.uuid4().hex}"
    stored = get_storage().put(key, data, content_type=content_type)
    attempt = get_learning_attempt_repository().create(
        user_id=user.id,
        case_id=case.id,
        dialogue_id=dialogue.id,
        mode=mode,
        audio_object_key=stored.key,
        audio_content_type=stored.content_type,
    )
    return AttemptOut(
        id=attempt.id,
        case_id=attempt.case_id,
        dialogue_id=attempt.dialogue_id,
        mode=attempt.mode,
        audio_object_key=attempt.audio_object_key,
        created_at=attempt.created_at,
    )
