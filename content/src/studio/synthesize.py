from __future__ import annotations

import asyncio
import json
import wave
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from typing import Literal

from studio.models import CEFR_LEVELS, CONTEXTS, dialogue_stem
from studio.paths import cases_root
from studio.review import assert_accepted

TtsEngineName = Literal["auto", "synthetic", "edge"]

MALE_VOICE = "en-US-GuyNeural"
FEMALE_VOICE = "en-US-JennyNeural"
FEMALE_SPEAKERS = {"parent", "nurse", "jenny", "mother", "family", "patient"}


@dataclass(frozen=True)
class WordTimestamp:
    word: str
    offset_ms: int
    duration_ms: int


@dataclass(frozen=True)
class SynthResult:
    audio: bytes
    content_type: str
    voice: str
    duration_ms: int
    words: list[WordTimestamp]
    engine: str = "synthetic"


def voice_for_speaker(speaker: str) -> str:
    key = speaker.strip().lower()
    if key in FEMALE_SPEAKERS:
        return FEMALE_VOICE
    return MALE_VOICE


def _silent_wav(duration_ms: int, sample_rate: int = 8000) -> bytes:
    n_frames = max(1, int(sample_rate * duration_ms / 1000))
    buf = BytesIO()
    with wave.open(buf, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(sample_rate)
        wav.writeframes(b"\x00\x00" * n_frames)
    return buf.getvalue()


def _stamp_words(text: str, *, ms_per_word: int = 320) -> tuple[list[WordTimestamp], int]:
    words = [w for w in text.split() if w] or ["…"]
    stamps: list[WordTimestamp] = []
    cursor = 0
    for word in words:
        stamps.append(
            WordTimestamp(word=word, offset_ms=cursor, duration_ms=ms_per_word)
        )
        cursor += ms_per_word
    return stamps, cursor


class SyntheticTtsEngine:
    """CI-safe TTS: silent WAV + evenly spaced word timestamps (no network)."""

    def __init__(self, *, ms_per_word: int = 320) -> None:
        self.ms_per_word = ms_per_word

    def synthesize(self, *, text: str, speaker: str) -> SynthResult:
        stamps, duration_ms = _stamp_words(text, ms_per_word=self.ms_per_word)
        audio = _silent_wav(duration_ms)
        return SynthResult(
            audio=audio,
            content_type="audio/wav",
            voice=voice_for_speaker(speaker),
            duration_ms=duration_ms,
            words=stamps,
            engine="synthetic",
        )


async def _edge_stream(text: str, voice: str) -> SynthResult:
    import edge_tts  # type: ignore[import-untyped]

    communicate = edge_tts.Communicate(text, voice)
    audio = bytearray()
    words: list[WordTimestamp] = []
    async for chunk in communicate.stream():
        kind = chunk.get("type")
        if kind == "audio":
            audio.extend(chunk.get("data") or b"")
        elif kind == "WordBoundary":
            offset_ms = int(chunk.get("offset", 0) / 10_000)
            duration_ms = int(chunk.get("duration", 0) / 10_000)
            words.append(
                WordTimestamp(
                    word=str(chunk.get("text") or ""),
                    offset_ms=offset_ms,
                    duration_ms=max(duration_ms, 1),
                )
            )
    duration_ms = 0
    if words:
        last = words[-1]
        duration_ms = last.offset_ms + last.duration_ms
    if not audio:
        raise RuntimeError("edge-tts returned empty audio")
    if not words:
        parts = text.split() or ["…"]
        step = max(duration_ms // len(parts), 200) if duration_ms else 320
        cursor = 0
        for part in parts:
            words.append(
                WordTimestamp(word=part, offset_ms=cursor, duration_ms=step)
            )
            cursor += step
        duration_ms = cursor
    return SynthResult(
        audio=bytes(audio),
        content_type="audio/mpeg",
        voice=voice,
        duration_ms=duration_ms,
        words=words,
        engine="edge",
    )


class EdgeTtsEngine:
    """Optional edge-tts adapter. Falls back to synthetic if SDK/network fails."""

    def __init__(self) -> None:
        self._fallback = SyntheticTtsEngine()

    def synthesize(self, *, text: str, speaker: str) -> SynthResult:
        voice = voice_for_speaker(speaker)
        try:
            import edge_tts  # noqa: F401  # type: ignore[import-untyped]
        except ImportError:
            return self._fallback.synthesize(text=text, speaker=speaker)
        try:
            return asyncio.run(_edge_stream(text, voice))
        except Exception:
            return self._fallback.synthesize(text=text, speaker=speaker)


def resolve_engine(name: TtsEngineName) -> SyntheticTtsEngine | EdgeTtsEngine:
    if name == "synthetic":
        return SyntheticTtsEngine()
    if name == "edge":
        return EdgeTtsEngine()
    # auto: prefer edge when importable, else synthetic
    try:
        import edge_tts  # noqa: F401  # type: ignore[import-untyped]

        return EdgeTtsEngine()
    except ImportError:
        return SyntheticTtsEngine()


def _concat_wav(chunks: list[bytes]) -> bytes:
    if not chunks:
        return _silent_wav(1)
    if len(chunks) == 1:
        return chunks[0]
    params: tuple[int, int, int] | None = None
    frames = bytearray()
    for chunk in chunks:
        with wave.open(BytesIO(chunk), "rb") as src:
            if params is None:
                params = (src.getnchannels(), src.getsampwidth(), src.getframerate())
            else:
                cur = (src.getnchannels(), src.getsampwidth(), src.getframerate())
                if cur != params:
                    raise ValueError("incompatible wav streams for concat")
            frames.extend(src.readframes(src.getnframes()))
    assert params is not None
    nch, sw, rate = params
    out = BytesIO()
    with wave.open(out, "wb") as wav:
        wav.setnchannels(nch)
        wav.setsampwidth(sw)
        wav.setframerate(rate)
        wav.writeframes(frames)
    return out.getvalue()


def _concat_mp3(chunks: list[bytes]) -> bytes:
    return b"".join(chunks)


def _case_dir(case_id: str) -> Path:
    case_dir = cases_root() / case_id
    if not case_dir.is_dir():
        raise FileNotFoundError(f"Case not found: {case_id}")
    return case_dir


def _load_dialogue(case_dir: Path, stem: str) -> dict[str, object]:
    path = case_dir / "dialogues" / f"{stem}.json"
    if not path.is_file():
        raise FileNotFoundError(f"Dialogue not found: {stem}")
    return json.loads(path.read_text(encoding="utf-8"))


def _synthesize_stem(
    case_dir: Path,
    stem: str,
    *,
    force: bool,
    engine_name: TtsEngineName,
) -> Path:
    assert_accepted(case_dir.name, stem, force=force)
    dialogue = _load_dialogue(case_dir, stem)
    lines = dialogue.get("lines") or []
    if not lines:
        raise ValueError(f"Dialogue {stem} has no lines")

    tts = resolve_engine(engine_name)
    audio_dir = case_dir / "audio" / stem
    audio_dir.mkdir(parents=True, exist_ok=True)

    pending: list[tuple[int, str, str]] = []
    for index, line in enumerate(lines):
        text = str(line.get("text") or "").strip()
        speaker = str(line.get("speaker") or "doctor")
        if not text:
            continue
        pending.append((index, text, speaker))

    synth_results: list[tuple[int, str, str, SynthResult]] = []
    for index, text, speaker in pending:
        result = tts.synthesize(text=text, speaker=speaker)
        synth_results.append((index, text, speaker, result))

    engines_used = {r.engine for *_, r in synth_results}
    has_mp3 = any("mpeg" in r.content_type for *_, r in synth_results)
    has_wav = any("mpeg" not in r.content_type for *_, r in synth_results)
    mixed_containers = has_mp3 and has_wav

    if mixed_containers:
        uniform = SyntheticTtsEngine()
        synth_results = [
            (index, text, speaker, uniform.synthesize(text=text, speaker=speaker))
            for index, text, speaker in pending
        ]
        engines_used = {"synthetic"}

    line_entries: list[dict[str, object]] = []
    audio_chunks: list[bytes] = []
    timeline_ms = 0

    for index, text, speaker, result in synth_results:
        ext = "mp3" if "mpeg" in result.content_type else "wav"
        filename = f"line_{index + 1:03d}.{ext}"
        line_path = audio_dir / filename
        line_path.write_bytes(result.audio)
        audio_chunks.append(result.audio)

        line_entries.append(
            {
                "line_index": index,
                "speaker": speaker,
                "voice": result.voice,
                "text": text,
                "file": filename,
                "duration_ms": result.duration_ms,
                "offset_ms": timeline_ms,
                "words": [
                    {
                        "word": w.word,
                        "offset_ms": w.offset_ms,
                        "duration_ms": w.duration_ms,
                    }
                    for w in result.words
                ],
            }
        )
        timeline_ms += result.duration_ms

    if engine_name == "synthetic" or "synthetic" in engines_used:
        effective_engine = "synthetic"
    elif engines_used == {"edge"}:
        effective_engine = "edge"
    else:
        effective_engine = "synthetic"

    all_mp3 = bool(synth_results) and all(
        "mpeg" in r.content_type for *_, r in synth_results
    )
    if all_mp3:
        full_bytes = _concat_mp3(audio_chunks)
        full_name = "full.mp3"
    else:
        full_bytes = _concat_wav(audio_chunks)
        full_name = "full.wav"

    (audio_dir / full_name).write_bytes(full_bytes)

    ts_path = audio_dir / "timestamps.json"
    payload = {
        "dialogue_stem": stem,
        "engine": effective_engine,
        "duration_ms": timeline_ms,
        "full": full_name,
        "lines": line_entries,
    }
    ts_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return ts_path


def _stems_for_case(case_id: str, stem_filter: str | None) -> list[str]:
    if stem_filter:
        return [stem_filter]
    case_dir = _case_dir(case_id)
    stems: list[str] = []
    for context in CONTEXTS:
        for cefr in CEFR_LEVELS:
            stem = dialogue_stem(context, cefr)
            path = case_dir / "dialogues" / f"{stem}.json"
            if not path.is_file():
                continue
            data = json.loads(path.read_text(encoding="utf-8"))
            if data.get("status") == "accepted":
                stems.append(stem)
    return stems


def synthesize_case(
    case_id: str,
    dialogue_stem: str | None = None,
    *,
    force: bool = False,
    engine: TtsEngineName = "auto",
) -> list[Path]:
    """Synthesize line audio + timestamps for accepted dialogues (or all with --force)."""
    case_dir = _case_dir(case_id)
    stems = _stems_for_case(case_id, dialogue_stem)
    if not stems:
        raise ValueError(
            f"No dialogues to synthesize for case {case_id}"
            + (f" (stem={dialogue_stem!r})" if dialogue_stem else " (no accepted dialogues)")
        )
    written: list[Path] = []
    for stem in stems:
        _synthesize_stem(case_dir, stem, force=force, engine_name=engine)
        stem_dir = case_dir / "audio" / stem
        for child in sorted(stem_dir.iterdir()):
            if child.is_file():
                written.append(child)
    return written