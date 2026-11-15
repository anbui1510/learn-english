from __future__ import annotations

import asyncio
import wave
from dataclasses import dataclass
from io import BytesIO
from typing import Protocol


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


# Demo voice map (edge-tts names kept for metadata even when synthetic).
MALE_VOICE = "en-US-GuyNeural"
FEMALE_VOICE = "en-US-JennyNeural"
FEMALE_SPEAKERS = {"parent", "nurse", "jenny", "mother", "family"}


def voice_for_speaker(speaker: str) -> str:
    key = speaker.strip().lower()
    if key in FEMALE_SPEAKERS:
        return FEMALE_VOICE
    return MALE_VOICE


class TtsEngine(Protocol):
    def synthesize(self, *, text: str, speaker: str) -> SynthResult: ...


def _silent_wav(duration_ms: int, sample_rate: int = 8000) -> bytes:
    n_frames = max(1, int(sample_rate * duration_ms / 1000))
    buf = BytesIO()
    with wave.open(buf, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(sample_rate)
        wav.writeframes(b"\x00\x00" * n_frames)
    return buf.getvalue()


class SyntheticTtsEngine:
    """CI-safe TTS: silent WAV + evenly spaced word timestamps (no network)."""

    def __init__(self, *, ms_per_word: int = 320) -> None:
        self.ms_per_word = ms_per_word

    def synthesize(self, *, text: str, speaker: str) -> SynthResult:
        words = [w for w in text.split() if w]
        if not words:
            words = ["…"]
        stamps: list[WordTimestamp] = []
        cursor = 0
        for word in words:
            stamps.append(
                WordTimestamp(word=word, offset_ms=cursor, duration_ms=self.ms_per_word)
            )
            cursor += self.ms_per_word
        audio = _silent_wav(cursor)
        return SynthResult(
            audio=audio,
            content_type="audio/wav",
            voice=voice_for_speaker(speaker),
            duration_ms=cursor,
            words=stamps,
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
            # edge-tts offsets are in 100-nanosecond units
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
        # Fallback stamp whole utterance if WordBoundary missing
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


def get_default_tts(*, use_edge: bool = False) -> TtsEngine:
    if use_edge:
        return EdgeTtsEngine()
    return SyntheticTtsEngine()
