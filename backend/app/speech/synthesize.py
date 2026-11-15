from __future__ import annotations

from app.auth.settings import get_auth_settings
from app.dialogues.repository import DialogueRecord
from app.speech.repository import UtteranceRecord, UtteranceRepository
from app.speech.tts import TtsEngine, get_default_tts
from app.storage.base import ObjectStorage


def synthesize_dialogue(
    *,
    dialogue: DialogueRecord,
    utterances: UtteranceRepository,
    storage: ObjectStorage,
    engine: TtsEngine | None = None,
) -> list[UtteranceRecord]:
    """Idempotent re-synth: replaces utterances for the dialogue."""
    settings = get_auth_settings()
    tts = engine or get_default_tts(use_edge=settings.use_edge_tts)
    lines = list(dialogue.payload.get("lines") or [])
    if not lines:
        raise ValueError("Dialogue has no lines to synthesize")

    utterances.delete_for_dialogue(dialogue.id)
    created: list[UtteranceRecord] = []
    for index, line in enumerate(lines):
        text = str(line.get("text") or "").strip()
        speaker = str(line.get("speaker") or "doctor")
        result = tts.synthesize(text=text, speaker=speaker)
        ext = "mp3" if "mpeg" in result.content_type else "wav"
        key = f"audio/dialogues/{dialogue.id}/line-{index:03d}.{ext}"
        stored = storage.put(key, result.audio, content_type=result.content_type)
        stamps = [
            {
                "word": w.word,
                "offset_ms": w.offset_ms,
                "duration_ms": w.duration_ms,
            }
            for w in result.words
        ]
        created.append(
            utterances.upsert_utterance(
                dialogue_id=dialogue.id,
                line_index=index,
                speaker=speaker,
                voice=result.voice,
                object_key=stored.key,
                content_type=stored.content_type,
                duration_ms=result.duration_ms,
                timestamps=stamps,
            )
        )
    return created
