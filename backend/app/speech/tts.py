from __future__ import annotations

import asyncio
import wave
from dataclasses import dataclass
from io import BytesIO
from typing import Literal, Protocol

TtsProvider = Literal["synthetic", "edge", "azure", "elevenlabs"]


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


# Demo voice map (edge-tts names kept for metadata even when synthetic).
MALE_VOICE = "en-US-GuyNeural"
FEMALE_VOICE = "en-US-JennyNeural"
FEMALE_SPEAKERS = {"parent", "nurse", "jenny", "mother", "family"}
AZURE_MALE = "en-US-GuyNeural"
AZURE_FEMALE = "en-US-JennyNeural"


def voice_for_speaker(speaker: str) -> str:
    key = speaker.strip().lower()
    if key in FEMALE_SPEAKERS:
        return FEMALE_VOICE
    return MALE_VOICE


def azure_voice_for_speaker(speaker: str) -> str:
    key = speaker.strip().lower()
    if key in FEMALE_SPEAKERS:
        return AZURE_FEMALE
    return AZURE_MALE


class TtsEngine(Protocol):
    def synthesize(self, *, text: str, speaker: str) -> SynthResult: ...


class ElevenLabsHttpClient(Protocol):
    def post_tts(self, *, text: str, voice_id: str) -> bytes: ...


class AzureTtsClient(Protocol):
    def synthesize(self, *, text: str, voice: str) -> bytes: ...


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


class HttpElevenLabsClient:
    def __init__(self, *, api_key: str) -> None:
        self.api_key = api_key

    def post_tts(self, *, text: str, voice_id: str) -> bytes:
        import httpx

        url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"
        response = httpx.post(
            url,
            headers={
                "xi-api-key": self.api_key,
                "Accept": "audio/mpeg",
                "Content-Type": "application/json",
            },
            json={"text": text, "model_id": "eleven_monolingual_v1"},
            timeout=60.0,
        )
        response.raise_for_status()
        return response.content


class ElevenLabsTtsEngine:
    """Premium ElevenLabs TTS. Falls back to synthetic without key/network."""

    def __init__(
        self,
        *,
        api_key: str,
        voice_id: str = "21m00Tcm4TlvDq8ikWAM",
        client: ElevenLabsHttpClient | None = None,
        fallback: TtsEngine | None = None,
    ) -> None:
        self.api_key = api_key
        self.voice_id = voice_id
        self._client = client
        self._fallback = fallback or SyntheticTtsEngine()

    def synthesize(self, *, text: str, speaker: str) -> SynthResult:
        del speaker
        if not self.api_key and self._client is None:
            return self._fallback.synthesize(text=text, speaker="doctor")
        client = self._client or HttpElevenLabsClient(api_key=self.api_key)
        try:
            audio = client.post_tts(text=text, voice_id=self.voice_id)
            stamps, duration_ms = _stamp_words(text)
            return SynthResult(
                audio=audio,
                content_type="audio/mpeg",
                voice=self.voice_id,
                duration_ms=duration_ms,
                words=stamps,
                engine="elevenlabs",
            )
        except Exception:
            return self._fallback.synthesize(text=text, speaker="doctor")


class SdkAzureTtsClient:
    def __init__(self, *, key: str, region: str) -> None:
        self.key = key
        self.region = region

    def synthesize(self, *, text: str, voice: str) -> bytes:
        import azure.cognitiveservices.speech as speechsdk  # type: ignore[import-untyped]

        speech_config = speechsdk.SpeechConfig(subscription=self.key, region=self.region)
        speech_config.speech_synthesis_voice_name = voice
        speech_config.set_speech_synthesis_output_format(
            speechsdk.SpeechSynthesisOutputFormat.Audio16Khz32KBitRateMonoMp3
        )
        synthesizer = speechsdk.SpeechSynthesizer(
            speech_config=speech_config, audio_config=None
        )
        result = synthesizer.speak_text_async(text).get()
        if result.reason != speechsdk.ResultReason.SynthesizingAudioCompleted:
            raise RuntimeError(f"Azure TTS failed: {result.reason}")
        return bytes(result.audio_data)


class AzureTtsEngine:
    """Premium Azure Neural TTS. Falls back to synthetic without key/SDK."""

    def __init__(
        self,
        *,
        key: str,
        region: str,
        client: AzureTtsClient | None = None,
        fallback: TtsEngine | None = None,
    ) -> None:
        self.key = key
        self.region = region
        self._client = client
        self._fallback = fallback or SyntheticTtsEngine()

    def synthesize(self, *, text: str, speaker: str) -> SynthResult:
        voice = azure_voice_for_speaker(speaker)
        if self._client is None and (not self.key or not self.region):
            return self._fallback.synthesize(text=text, speaker=speaker)
        client = self._client
        if client is None:
            try:
                import azure.cognitiveservices.speech  # noqa: F401
            except ImportError:
                return self._fallback.synthesize(text=text, speaker=speaker)
            client = SdkAzureTtsClient(key=self.key, region=self.region)
        try:
            audio = client.synthesize(text=text, voice=voice)
            stamps, duration_ms = _stamp_words(text)
            return SynthResult(
                audio=audio,
                content_type="audio/mpeg",
                voice=voice,
                duration_ms=duration_ms,
                words=stamps,
                engine="azure",
            )
        except Exception:
            return self._fallback.synthesize(text=text, speaker=speaker)


def resolve_tts(
    *,
    provider: TtsProvider = "synthetic",
    premium_enabled: bool = False,
    use_edge: bool = False,
    azure_speech_key: str = "",
    azure_speech_region: str = "eastasia",
    elevenlabs_api_key: str = "",
    elevenlabs_voice_id: str = "21m00Tcm4TlvDq8ikWAM",
) -> TtsEngine:
    """Pick TTS engine from org provider + premium cost flag."""
    if provider in {"azure", "elevenlabs"} and not premium_enabled:
        # Cost gate: premium providers require org flag.
        if use_edge:
            return EdgeTtsEngine()
        return SyntheticTtsEngine()
    if provider == "elevenlabs":
        return ElevenLabsTtsEngine(
            api_key=elevenlabs_api_key,
            voice_id=elevenlabs_voice_id,
        )
    if provider == "azure":
        return AzureTtsEngine(key=azure_speech_key, region=azure_speech_region)
    if provider == "edge" or use_edge:
        return EdgeTtsEngine()
    return SyntheticTtsEngine()


def get_default_tts(*, use_edge: bool = False) -> TtsEngine:
    """Backward-compatible helper used by synthesize_dialogue."""
    from app.auth.settings import get_auth_settings
    from app.org_settings.service import get_tts_org_settings

    settings = get_auth_settings()
    org = get_tts_org_settings()
    return resolve_tts(
        provider=org.provider,  # type: ignore[arg-type]
        premium_enabled=org.premium_enabled,
        use_edge=use_edge or settings.use_edge_tts,
        azure_speech_key=settings.azure_speech_key,
        azure_speech_region=settings.azure_speech_region,
        elevenlabs_api_key=settings.elevenlabs_api_key,
        elevenlabs_voice_id=settings.elevenlabs_voice_id,
    )
