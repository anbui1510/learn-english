from __future__ import annotations

import uuid
from typing import Annotated, Any, Literal

from datetime import date, timedelta

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from pydantic import BaseModel, Field

from app.auth.deps import require_learner_access
from app.auth.settings import get_auth_settings
from app.cases.service import get_case_repository
from app.dialogues.service import get_dialogue_repository
from app.facts.service import get_fact_repository
from app.learner.profiles import CefrPackage
from app.learner.empathy import empathy_to_dict
from app.learner.progression import (
    ROLEPLAY_PA_THRESHOLD,
    evaluate_unlock,
    progression_snapshot,
    rank_for_completions,
)
from app.learner.pronunciation import result_to_dict
from app.learner.service import (
    get_empathy_engine,
    get_learner_profile_repository,
    get_learning_attempt_repository,
    get_pa_rate_limiter,
    get_progression_repository,
    get_pronunciation_engine,
    get_srs_repository,
)
from app.learner.shadowing import build_shadowing_cards
from app.learner.skill_tree import build_skill_tree, tree_to_dict
from app.learner.streak import completion_days, current_streak
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
    module_slug: str | None = None
    unlocked: bool = True
    unlock_reason: str | None = None


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
    session_kind: Literal["standard", "presentation"] = "standard"
    target_seconds: float | None = None
    estimated_seconds: float = 0.0


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
    cme_awarded: int = 0
    rank_id: str | None = None
    rank_label: str | None = None
    certificate: dict[str, Any] | None = None


class WordScoreOut(BaseModel):
    word: str
    accuracy: float
    band: Literal["green", "yellow", "red"]


class ScoreOut(BaseModel):
    engine: str
    pronunciation: float
    completeness: float
    prosody: float
    words: list[WordScoreOut]
    stress_hint: str | None = None


class EmpathyOut(BaseModel):
    engine: str
    score: float
    rubric: dict[str, float]
    feedback: str
    disclaimer: str
    coaching_tip: str | None = None
    sample_phrase: str | None = None


class EmpathySampleIn(BaseModel):
    text: str = Field(min_length=1, max_length=500)


class EmpathySampleOut(BaseModel):
    text: str
    audio_url: str
    duration_ms: int


class AttemptOut(BaseModel):
    id: int
    case_id: int
    dialogue_id: int
    mode: str
    audio_object_key: str
    created_at: str
    line_index: int | None = None
    reference_text: str | None = None
    response_mode: str = "read_along"
    score: ScoreOut | None = None
    empathy: EmpathyOut | None = None
    scored_at: str | None = None
    pa_usage: dict[str, int] | None = None
    srs_enqueued: int = 0


class ScoreAttemptIn(BaseModel):
    line_index: int = Field(default=0, ge=0)


class SrsCardOut(BaseModel):
    id: int
    phrase: str
    band: str
    due_at: str
    source_attempt_id: int | None = None


def _attempt_out(
    attempt,
    *,
    pa_usage: dict[str, int] | None = None,
    srs_enqueued: int = 0,
) -> AttemptOut:
    score = None
    if attempt.score_json:
        score = ScoreOut.model_validate(attempt.score_json)
    empathy = None
    if attempt.empathy_json:
        empathy = EmpathyOut.model_validate(attempt.empathy_json)
    return AttemptOut(
        id=attempt.id,
        case_id=attempt.case_id,
        dialogue_id=attempt.dialogue_id,
        mode=attempt.mode,
        audio_object_key=attempt.audio_object_key,
        created_at=attempt.created_at,
        line_index=attempt.line_index,
        reference_text=attempt.reference_text,
        response_mode=attempt.response_mode,
        score=score,
        empathy=empathy,
        scored_at=attempt.scored_at,
        pa_usage=pa_usage,
        srs_enqueued=srs_enqueued,
    )


def _apply_score_side_effects(
    *,
    user_id: int,
    attempt_id: int,
    score: dict[str, Any],
    response_mode: str,
    reference_text: str,
    audio: bytes,
) -> tuple[dict[str, Any] | None, int]:
    empathy_payload: dict[str, Any] | None = None
    if response_mode == "free_speech":
        empathy_payload = empathy_to_dict(
            get_empathy_engine().score(
                transcript_or_context=reference_text,
                audio_len=len(audio),
            )
        )
    cards = get_srs_repository().enqueue_from_score(
        user_id=user_id,
        attempt_id=attempt_id,
        score=score,
    )
    return empathy_payload, len(cards)


def _line_reference(dialogue, line_index: int) -> tuple[str, list[int] | None]:
    lines = list(dialogue.payload.get("lines") or [])
    if not lines:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Dialogue has no lines to score against",
        )
    if line_index < 0 or line_index >= len(lines):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="line_index out of range",
        )
    line = lines[line_index]
    text = str(line.get("text") or "").strip()
    if not text:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Reference line text is empty",
        )
    raw_stress = line.get("stress_pattern")
    stress: list[int] | None = None
    if isinstance(raw_stress, list) and raw_stress:
        try:
            stress = [int(x) for x in raw_stress]
        except (TypeError, ValueError):
            stress = None
    return text, stress


def _cases_by_module() -> dict[str, list[int]]:
    grouped: dict[str, list[int]] = {}
    for case in get_case_repository().list_published():
        if not case.module_slug:
            continue
        grouped.setdefault(case.module_slug, []).append(case.id)
    return grouped


def _streak_days(user_id: int) -> int:
    stamps = get_learner_profile_repository().completion_timestamps(user_id)
    return current_streak(completion_days(stamps))


def _module_lock_map(user_id: int) -> dict[str, tuple[bool, str | None]]:
    progress = get_progression_repository()
    completed = progress.completed_case_ids(user_id)
    certified = {c.module_slug for c in progress.list_certificates(user_id)}
    nodes = build_skill_tree(
        cases_by_module=_cases_by_module(),
        completed_case_ids=completed,
        certified_modules=certified,
    )

    def walk(items) -> dict[str, tuple[bool, str | None]]:
        mapping: dict[str, tuple[bool, str | None]] = {}
        for node in items:
            mapping[node.slug] = (node.unlocked, node.unlock_reason)
            mapping.update(walk(node.children))
        return mapping

    return walk(nodes)


@router.get("/cases", response_model=list[PublishedCaseOut])
def list_published_cases(
    user: Annotated[UserRecord, Depends(require_learner_access)],
) -> list[PublishedCaseOut]:
    progress = get_progression_repository()
    completed = progress.completed_case_ids(user.id)
    cme_total = progress.cme_total(user.id)
    rank_id, _ = rank_for_completions(len(completed))
    streak = _streak_days(user.id)
    module_locks = _module_lock_map(user.id)
    out: list[PublishedCaseOut] = []
    for case in get_case_repository().list_published():
        decision = evaluate_unlock(
            case=case,
            completed_cases=completed,
            cme_total=cme_total,
            rank_id=rank_id,
            streak_days=streak,
        )
        unlocked = decision.unlocked
        reason = decision.reason
        if case.module_slug and case.module_slug in module_locks:
            mod_ok, mod_reason = module_locks[case.module_slug]
            if not mod_ok:
                unlocked = False
                reason = mod_reason
        out.append(
            PublishedCaseOut(
                id=case.id,
                title=case.title,
                isbn=case.isbn,
                edition=case.edition,
                published_at=case.published_at,
                module_slug=case.module_slug,
                unlocked=unlocked,
                unlock_reason=reason,
            )
        )
    return out


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


def _assert_unlocked(user: UserRecord, case) -> None:
    progress = get_progression_repository()
    completed = progress.completed_case_ids(user.id)
    cme_total = progress.cme_total(user.id)
    rank_id, _ = rank_for_completions(len(completed))
    decision = evaluate_unlock(
        case=case,
        completed_cases=completed,
        cme_total=cme_total,
        rank_id=rank_id,
        streak_days=_streak_days(user.id),
    )
    if not decision.unlocked:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=decision.reason or "Case is locked",
        )
    if case.module_slug:
        mod_ok, mod_reason = _module_lock_map(user.id).get(
            case.module_slug, (True, None)
        )
        if not mod_ok:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=mod_reason or "Module is locked",
            )


@router.get("/dialogues/{dialogue_id}/lesson", response_model=LessonOut)
def get_lesson(
    dialogue_id: int,
    user: Annotated[UserRecord, Depends(require_learner_access)],
) -> LessonOut:
    settings = get_auth_settings()
    case, dialogue = _require_published_dialogue(dialogue_id)
    _assert_unlocked(user, case)
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
    raw_kind = str(dialogue.payload.get("session_kind") or "standard")
    session_kind: Literal["standard", "presentation"] = (
        "presentation" if raw_kind == "presentation" else "standard"
    )
    target = dialogue.payload.get("target_seconds")
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
        session_kind=session_kind,
        target_seconds=float(target) if target is not None else None,
        estimated_seconds=float(dialogue.estimated_seconds),
    )


@router.get("/dialogues/{dialogue_id}/shadowing", response_model=ShadowingOut)
def get_shadowing(
    dialogue_id: int,
    user: Annotated[UserRecord, Depends(require_learner_access)],
) -> ShadowingOut:
    case, dialogue = _require_published_dialogue(dialogue_id)
    _assert_unlocked(user, case)
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
    progress = get_progression_repository()
    completed = progress.completed_case_ids(user.id)
    cme_total = progress.cme_total(user.id)
    rank_id, _ = rank_for_completions(len(completed))
    decision = evaluate_unlock(
        case=case,
        completed_cases=completed,
        cme_total=cme_total,
        rank_id=rank_id,
        streak_days=_streak_days(user.id),
    )
    if not decision.unlocked:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=decision.reason or "Case is locked",
        )
    row = get_learner_profile_repository().mark_complete(
        user_id=user.id, case_id=case.id, dialogue_id=dialogue.id
    )
    roleplay_bonus = False
    for attempt in get_learning_attempt_repository().list_for_user(user.id):
        if (
            attempt.dialogue_id == dialogue.id
            and attempt.mode == "role_play"
            and attempt.score_json
            and float(attempt.score_json.get("pronunciation") or 0)
            >= ROLEPLAY_PA_THRESHOLD
        ):
            roleplay_bonus = True
            break
    awarded = progress.award_lesson_cme(
        user_id=user.id,
        case_id=case.id,
        dialogue_id=dialogue.id,
        roleplay_bonus=roleplay_bonus,
    )
    completed_after = progress.completed_case_ids(user.id)
    new_rank_id, new_rank_label = rank_for_completions(len(completed_after))
    certificate = None
    if case.module_slug:
        issued = progress.issue_module_certificate_if_eligible(
            user_id=user.id,
            module_slug=case.module_slug,
            rank_id=new_rank_id,
        )
        if issued:
            certificate = {
                "id": issued.id,
                "module_slug": issued.module_slug,
                "title": issued.title,
                "cme_points": issued.cme_points,
                "share_slug": issued.share_slug,
                "disclaimer": issued.disclaimer,
            }
    return CompletionOut(
        id=row.id,
        case_id=row.case_id,
        dialogue_id=row.dialogue_id,
        completed_at=row.completed_at,
        cme_awarded=sum(entry.points for entry in awarded),
        rank_id=new_rank_id,
        rank_label=new_rank_label,
        certificate=certificate,
    )


@router.get("/progression")
def get_progression(
    user: Annotated[UserRecord, Depends(require_learner_access)],
) -> dict[str, Any]:
    return progression_snapshot(
        user_id=user.id,
        repo=get_progression_repository(),
        streak_days=_streak_days(user.id),
    )


@router.get("/skill-tree")
def get_skill_tree(
    user: Annotated[UserRecord, Depends(require_learner_access)],
) -> dict[str, Any]:
    progress = get_progression_repository()
    completed = progress.completed_case_ids(user.id)
    certified = {c.module_slug for c in progress.list_certificates(user.id)}
    nodes = build_skill_tree(
        cases_by_module=_cases_by_module(),
        completed_case_ids=completed,
        certified_modules=certified,
    )
    return {"nodes": tree_to_dict(nodes)}


class WordReplayOut(BaseModel):
    dialogue_id: int
    line_index: int
    word: str
    audio_url: str
    start_ms: int
    end_ms: int
    duration_ms: int


@router.get(
    "/dialogues/{dialogue_id}/lines/{line_index}/words/{word}/replay",
    response_model=WordReplayOut,
)
def replay_word_snippet(
    dialogue_id: int,
    line_index: int,
    word: str,
    user: Annotated[UserRecord, Depends(require_learner_access)],
) -> WordReplayOut:
    """Return AI TTS audio URL + word window for red-word tap replay."""
    settings = get_auth_settings()
    case, dialogue = _require_published_dialogue(dialogue_id)
    _assert_unlocked(user, case)
    utterances = get_utterance_repository().list_for_dialogue(dialogue_id)
    if not utterances:
        utterances = synthesize_dialogue(
            dialogue=dialogue,
            utterances=get_utterance_repository(),
            storage=get_storage(),
        )
    match = next((u for u in utterances if u.line_index == line_index), None)
    if match is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Line audio not found"
        )
    needle = word.strip().lower().strip(".,!?;:\"'")
    stamp = None
    for item in match.timestamps:
        token = str(item.get("word") or "").strip().lower().strip(".,!?;:\"'")
        if token == needle:
            stamp = item
            break
    if stamp is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Word timestamp not found on this line",
        )
    start_ms = int(stamp.get("offset_ms") or 0)
    duration_ms = max(int(stamp.get("duration_ms") or 200), 120)
    return WordReplayOut(
        dialogue_id=dialogue_id,
        line_index=line_index,
        word=str(stamp.get("word") or word),
        audio_url=get_storage().signed_url(
            match.object_key, expires_in=settings.signed_url_ttl_seconds
        ),
        start_ms=start_ms,
        end_ms=start_ms + duration_ms,
        duration_ms=duration_ms,
    )


class VideoExportOut(BaseModel):
    id: int
    dialogue_id: int
    case_id: int
    status: str
    download_url: str | None = None
    error: str | None = None
    width: int
    height: int
    engine: str
    created_at: str
    finished_at: str | None = None


def _video_export_out(job) -> VideoExportOut:
    settings = get_auth_settings()
    url = None
    if job.status == "succeeded" and job.object_key:
        url = get_storage().signed_url(
            job.object_key, expires_in=settings.signed_url_ttl_seconds
        )
    return VideoExportOut(
        id=job.id,
        dialogue_id=job.dialogue_id,
        case_id=job.case_id,
        status=job.status,
        download_url=url,
        error=job.error,
        width=job.width,
        height=job.height,
        engine=job.engine,
        created_at=job.created_at,
        finished_at=job.finished_at,
    )


class VideoExportIn(BaseModel):
    engine: Literal["ffmpeg", "remotion"] = "ffmpeg"


@router.post(
    "/dialogues/{dialogue_id}/export-video",
    response_model=VideoExportOut,
    status_code=201,
)
def enqueue_video_export(
    dialogue_id: int,
    user: Annotated[UserRecord, Depends(require_learner_access)],
    body: VideoExportIn | None = None,
) -> VideoExportOut:
    """Queue a 1080p karaoke/shadowing MP4 export (ffmpeg or Remotion)."""
    from app.video.service import get_video_export_repository, run_export_job

    preferred = (body.engine if body else "ffmpeg")
    case, dialogue = _require_published_dialogue(dialogue_id)
    _assert_unlocked(user, case)
    job = get_video_export_repository().create(
        user_id=user.id,
        dialogue_id=dialogue.id,
        case_id=case.id,
        width=1920,
        height=1080,
        engine=preferred,
    )
    # MVP: process inline so CI/demo do not need a worker process.
    finished = run_export_job(job.id, preferred_engine=preferred)
    return _video_export_out(finished)


@router.get("/video-exports/{job_id}", response_model=VideoExportOut)
def get_video_export(
    job_id: int,
    user: Annotated[UserRecord, Depends(require_learner_access)],
) -> VideoExportOut:
    from app.video.service import get_video_export_repository

    job = get_video_export_repository().get(job_id)
    if job is None or job.user_id != user.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Export not found"
        )
    return _video_export_out(job)


@router.post("/empathy/sample-audio", response_model=EmpathySampleOut)
def synthesize_empathy_sample(
    body: EmpathySampleIn,
    user: Annotated[UserRecord, Depends(require_learner_access)],
) -> EmpathySampleOut:
    """TTS a coaching sample phrase so learners can hear calm intonation."""
    del user  # auth gate only
    settings = get_auth_settings()
    from app.speech.tts import get_default_tts

    text = body.text.strip()
    if not text:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Empty sample text"
        )
    tts = get_default_tts(use_edge=settings.use_edge_tts)
    result = tts.synthesize(text=text, speaker="doctor")
    key = f"audio/empathy-samples/{uuid.uuid4().hex}.wav"
    stored = get_storage().put(key, result.audio, content_type=result.content_type)
    return EmpathySampleOut(
        text=text,
        audio_url=get_storage().signed_url(
            stored.key, expires_in=settings.signed_url_ttl_seconds
        ),
        duration_ms=result.duration_ms,
    )


@router.get("/certificates/{share_slug}")
def get_shared_certificate(share_slug: str) -> dict[str, Any]:
    cert = get_progression_repository().get_certificate_by_slug(share_slug)
    if cert is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Certificate not found"
        )
    return {
        "title": cert.title,
        "module_slug": cert.module_slug,
        "cme_points": cert.cme_points,
        "rank_at_issue": cert.rank_at_issue,
        "share_slug": cert.share_slug,
        "disclaimer": cert.disclaimer,
        "created_at": cert.created_at,
    }


@router.post("/attempts/audio", response_model=AttemptOut, status_code=201)
async def upload_attempt_audio(
    user: Annotated[UserRecord, Depends(require_learner_access)],
    dialogue_id: Annotated[int, Form()],
    mode: Annotated[Literal["shadowing", "role_play"], Form()],
    file: Annotated[UploadFile, File()],
    line_index: Annotated[int, Form()] = 0,
    score: Annotated[bool, Form()] = True,
    response_mode: Annotated[
        Literal["read_along", "free_speech"], Form()
    ] = "read_along",
) -> AttemptOut:
    case, dialogue = _require_published_dialogue(dialogue_id)
    data = await file.read()
    if not data:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Empty audio upload"
        )
    reference_text, stress = _line_reference(dialogue, line_index)
    pa_usage: dict[str, int] | None = None
    if score:
        allowed, used, limit = get_pa_rate_limiter().check_and_increment(user.id)
        pa_usage = {"used": used, "limit": limit}
        if not allowed:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Daily pronunciation score limit reached ({limit})",
            )
    content_type = (file.content_type or "application/octet-stream").split(";")[0]
    key = f"attempts/{user.id}/{dialogue.id}/{uuid.uuid4().hex}"
    stored = get_storage().put(key, data, content_type=content_type)
    repo = get_learning_attempt_repository()
    attempt = repo.create(
        user_id=user.id,
        case_id=case.id,
        dialogue_id=dialogue.id,
        mode=mode,
        audio_object_key=stored.key,
        audio_content_type=stored.content_type,
        line_index=line_index,
        reference_text=reference_text,
        response_mode=response_mode,
    )
    srs_enqueued = 0
    if score:
        result = get_pronunciation_engine().assess(
            audio=data,
            reference_text=reference_text,
            cefr_level=dialogue.cefr_level,
            stress_pattern=stress,
        )
        score_payload = result_to_dict(result)
        empathy_payload, srs_enqueued = _apply_score_side_effects(
            user_id=user.id,
            attempt_id=attempt.id,
            score=score_payload,
            response_mode=response_mode,
            reference_text=reference_text,
            audio=data,
        )
        attempt = repo.save_score(
            attempt_id=attempt.id,
            score=score_payload,
            line_index=line_index,
            reference_text=reference_text,
            empathy=empathy_payload,
        )
    return _attempt_out(attempt, pa_usage=pa_usage, srs_enqueued=srs_enqueued)


@router.post("/attempts/{attempt_id}/score", response_model=AttemptOut)
def score_attempt(
    attempt_id: int,
    body: ScoreAttemptIn,
    user: Annotated[UserRecord, Depends(require_learner_access)],
) -> AttemptOut:
    repo = get_learning_attempt_repository()
    attempt = repo.get_by_id(attempt_id)
    if attempt is None or attempt.user_id != user.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Attempt not found"
        )
    _, dialogue = _require_published_dialogue(attempt.dialogue_id)
    reference_text, stress = _line_reference(dialogue, body.line_index)
    allowed, used, limit = get_pa_rate_limiter().check_and_increment(user.id)
    if not allowed:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Daily pronunciation score limit reached ({limit})",
        )
    try:
        audio = get_storage().get(attempt.audio_object_key)
    except FileNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Attempt audio missing from storage",
        ) from exc

    result = get_pronunciation_engine().assess(
        audio=audio,
        reference_text=reference_text,
        cefr_level=dialogue.cefr_level,
        stress_pattern=stress,
    )
    score_payload = result_to_dict(result)
    empathy_payload, srs_enqueued = _apply_score_side_effects(
        user_id=user.id,
        attempt_id=attempt.id,
        score=score_payload,
        response_mode=attempt.response_mode,
        reference_text=reference_text,
        audio=audio,
    )
    updated = repo.save_score(
        attempt_id=attempt.id,
        score=score_payload,
        line_index=body.line_index,
        reference_text=reference_text,
        empathy=empathy_payload,
    )
    return _attempt_out(
        updated,
        pa_usage={"used": used, "limit": limit},
        srs_enqueued=srs_enqueued,
    )


@router.get("/srs/queue", response_model=list[SrsCardOut])
def list_srs_queue(
    user: Annotated[UserRecord, Depends(require_learner_access)],
    horizon_days: Annotated[int, Query(ge=0, le=7)] = 1,
) -> list[SrsCardOut]:
    """Return incomplete SRS cards due on/before today+horizon (default T+1)."""
    on_or_before = (date.today() + timedelta(days=horizon_days)).isoformat()
    cards = get_srs_repository().list_due(user.id, on_or_before=on_or_before)
    return [
        SrsCardOut(
            id=card.id,
            phrase=card.phrase,
            band=card.band,
            due_at=card.due_at,
            source_attempt_id=card.source_attempt_id,
        )
        for card in cards
    ]


@router.post("/srs/{card_id}/done", response_model=SrsCardOut)
def complete_srs_card(
    card_id: int,
    user: Annotated[UserRecord, Depends(require_learner_access)],
) -> SrsCardOut:
    card = get_srs_repository().mark_done(card_id=card_id, user_id=user.id)
    if card is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="SRS card not found"
        )
    return SrsCardOut(
        id=card.id,
        phrase=card.phrase,
        band=card.band,
        due_at=card.due_at,
        source_attempt_id=card.source_attempt_id,
    )
