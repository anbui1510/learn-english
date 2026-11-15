from __future__ import annotations

import tempfile
from functools import lru_cache
from pathlib import Path
from typing import Literal

from app.auth.settings import get_auth_settings
from app.dialogues.service import get_dialogue_repository
from app.speech.service import get_utterance_repository
from app.speech.synthesize import synthesize_dialogue
from app.storage.factory import get_storage
from app.video.export import (
    CliRemotionRenderer,
    RemotionRenderer,
    render_karaoke_export,
)
from app.video.repository import VideoExportJob, VideoExportRepository

VideoEngine = Literal["ffmpeg", "remotion"]


@lru_cache
def get_video_export_repository() -> VideoExportRepository:
    return VideoExportRepository(get_auth_settings().database_path)


def get_remotion_renderer() -> RemotionRenderer:
    return CliRemotionRenderer()


def run_export_job(
    job_id: int, *, preferred_engine: VideoEngine = "ffmpeg"
) -> VideoExportJob:
    repo = get_video_export_repository()
    job = repo.get(job_id)
    if job is None:
        raise KeyError(job_id)
    repo.mark_running(job_id)
    try:
        dialogue = get_dialogue_repository().get_by_id(job.dialogue_id)
        if dialogue is None:
            raise ValueError("Dialogue not found")
        utterances = get_utterance_repository().list_for_dialogue(job.dialogue_id)
        if not utterances:
            utterances = synthesize_dialogue(
                dialogue=dialogue,
                utterances=get_utterance_repository(),
                storage=get_storage(),
            )
        lines_payload = list(dialogue.payload.get("lines") or [])
        storage = get_storage()
        with tempfile.TemporaryDirectory() as tmp:
            work = Path(tmp)
            clips: list[dict] = []
            for utt in utterances:
                audio_bytes = storage.get(utt.object_key)
                ext = ".mp3" if "mpeg" in (utt.content_type or "") else ".wav"
                audio_path = work / f"line-{utt.line_index:03d}{ext}"
                audio_path.write_bytes(audio_bytes)
                line = (
                    lines_payload[utt.line_index]
                    if utt.line_index < len(lines_payload)
                    else {}
                )
                clips.append(
                    {
                        "speaker": utt.speaker,
                        "text": str(line.get("text") or ""),
                        "audio_path": audio_path,
                        "timestamps": utt.timestamps,
                    }
                )
            out = work / "export.mp4"
            from app.cases.service import get_case_repository

            case = get_case_repository().get_by_id(job.case_id)
            title = case.title if case else f"Dialogue {job.dialogue_id}"
            used = render_karaoke_export(
                output_path=out,
                title=title,
                lines=clips,
                preferred_engine=preferred_engine,
                width=job.width,
                height=job.height,
                remotion=get_remotion_renderer(),
            )
            key = f"video/exports/{job.user_id}/{job.id}.mp4"
            stored = storage.put(key, out.read_bytes(), content_type="video/mp4")
        return repo.mark_succeeded(job_id, object_key=stored.key, engine=used)
    except Exception as exc:  # noqa: BLE001 — surface to job error field
        return repo.mark_failed(job_id, error=str(exc))
