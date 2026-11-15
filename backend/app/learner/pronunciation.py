from __future__ import annotations

import hashlib
import json
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, Protocol

WordBand = Literal["green", "yellow", "red"]


@dataclass(frozen=True)
class WordScore:
    word: str
    accuracy: float
    band: WordBand


@dataclass(frozen=True)
class PaResult:
    engine: str
    pronunciation: float
    completeness: float
    prosody: float
    words: list[WordScore]
    stress_hint: str | None = None


def band_for_accuracy(score: float) -> WordBand:
    if score >= 80:
        return "green"
    if score >= 60:
        return "yellow"
    return "red"


def _stable_unit(seed: str) -> float:
    digest = hashlib.sha256(seed.encode("utf-8")).hexdigest()
    return int(digest[:8], 16) / 0xFFFFFFFF


_PROSODY_STRESS_GATE = 75.0


def _stress_hint(
    *,
    cefr_level: str,
    stress_pattern: list[int] | None,
    words: list[WordScore] | list[str],
    prosody: float,
) -> str | None:
    """C1 stress coaching only when prosody is weak or a stressed word is not green."""
    if cefr_level.upper() != "C1" or not stress_pattern:
        return None
    peak = max(stress_pattern)
    scored: list[WordScore] = []
    for item in words:
        if isinstance(item, WordScore):
            scored.append(item)
        else:
            scored.append(WordScore(word=str(item), accuracy=100.0, band="green"))
    stressed_scores = [
        scored[i] if i < len(scored) else WordScore(word="?", accuracy=0.0, band="red")
        for i, mark in enumerate(stress_pattern)
        if mark == peak
    ]
    if not stressed_scores:
        return None
    stressed_wrong = any(w.band != "green" for w in stressed_scores)
    if prosody >= _PROSODY_STRESS_GATE and not stressed_wrong:
        return None
    labels = [w.word for w in stressed_scores]
    return f"Stress the highlighted syllable(s) in: {', '.join(labels[:3])}"


class PronunciationEngine(Protocol):
    def assess(
        self,
        *,
        audio: bytes,
        reference_text: str,
        cefr_level: str,
        stress_pattern: list[int] | None = None,
    ) -> PaResult: ...


class AzureSpeechPaClient(Protocol):
    def assess_wav(self, *, wav_bytes: bytes, reference_text: str) -> str: ...


def to_wav_pcm16(audio: bytes, *, sample_rate: int = 16000) -> bytes:
    """Return mono PCM16 WAV. Passthrough if already RIFF/WAV; else ffmpeg."""
    if len(audio) >= 12 and audio[:4] == b"RIFF" and audio[8:12] == b"WAVE":
        return audio
    with tempfile.TemporaryDirectory() as tmp:
        src = Path(tmp) / "in.bin"
        dst = Path(tmp) / "out.wav"
        src.write_bytes(audio)
        cmd = [
            "ffmpeg",
            "-y",
            "-i",
            str(src),
            "-ac",
            "1",
            "-ar",
            str(sample_rate),
            "-sample_fmt",
            "s16",
            str(dst),
        ]
        proc = subprocess.run(cmd, capture_output=True, check=False)
        if proc.returncode != 0 or not dst.exists():
            raise RuntimeError(
                f"ffmpeg convert failed: {proc.stderr.decode('utf-8', errors='ignore')[:200]}"
            )
        return dst.read_bytes()


def parse_azure_pa_json(
    raw: str | dict[str, Any],
    *,
    cefr_level: str = "B1",
    stress_pattern: list[int] | None = None,
    reference_text: str = "",
) -> PaResult:
    payload = json.loads(raw) if isinstance(raw, str) else raw
    nbest = payload.get("NBest") or []
    if not nbest:
        raise ValueError("Azure PA JSON missing NBest")
    best = nbest[0]
    pa = best.get("PronunciationAssessment") or {}
    pronunciation = float(
        pa.get("PronScore")
        if pa.get("PronScore") is not None
        else pa.get("AccuracyScore")
        or 0
    )
    completeness = float(pa.get("CompletenessScore") or 0)
    prosody = float(pa.get("ProsodyScore") or pa.get("FluencyScore") or 0)
    words_out: list[WordScore] = []
    for item in best.get("Words") or []:
        word = str(item.get("Word") or "").strip()
        if not word:
            continue
        wpa = item.get("PronunciationAssessment") or {}
        accuracy = float(wpa.get("AccuracyScore") or 0)
        error = str(wpa.get("ErrorType") or "None")
        if error in {"Omission", "Insertion"}:
            accuracy = min(accuracy, 40.0)
        words_out.append(
            WordScore(word=word, accuracy=round(accuracy, 1), band=band_for_accuracy(accuracy))
        )
    if not words_out and reference_text:
        for token in reference_text.split():
            words_out.append(
                WordScore(word=token, accuracy=round(pronunciation, 1), band=band_for_accuracy(pronunciation))
            )
    hint = _stress_hint(
        cefr_level=cefr_level,
        stress_pattern=stress_pattern,
        words=words_out
        or [
            WordScore(word=t, accuracy=round(pronunciation, 1), band=band_for_accuracy(pronunciation))
            for t in reference_text.split()
        ],
        prosody=prosody,
    )
    return PaResult(
        engine="azure",
        pronunciation=round(pronunciation, 1),
        completeness=round(completeness, 1),
        prosody=round(prosody, 1),
        words=words_out,
        stress_hint=hint,
    )


class SyntheticPaEngine:
    """CI-safe PA: deterministic scores from reference text + audio bytes (no Azure)."""

    def assess(
        self,
        *,
        audio: bytes,
        reference_text: str,
        cefr_level: str,
        stress_pattern: list[int] | None = None,
    ) -> PaResult:
        words = [w for w in reference_text.split() if w]
        if not words:
            words = ["…"]
        scored: list[WordScore] = []
        for index, word in enumerate(words):
            base = 55 + _stable_unit(f"{word}:{len(audio)}:{index}") * 45
            if len(audio) < 32:
                base = min(base, 45)
            accuracy = round(base, 1)
            scored.append(
                WordScore(word=word, accuracy=accuracy, band=band_for_accuracy(accuracy))
            )
        avg = round(sum(w.accuracy for w in scored) / len(scored), 1)
        completeness = 40.0 if len(audio) < 32 else min(100.0, 70 + len(audio) % 30)
        prosody = round(50 + _stable_unit(reference_text) * 45, 1)
        return PaResult(
            engine="synthetic",
            pronunciation=avg,
            completeness=round(completeness, 1),
            prosody=prosody,
            words=scored,
            stress_hint=_stress_hint(
                cefr_level=cefr_level,
                stress_pattern=stress_pattern,
                words=scored,
                prosody=prosody,
            ),
        )


class SdkAzureSpeechPaClient:
    """Live Azure Speech SDK client (optional dependency group `speech`)."""

    def __init__(self, *, key: str, region: str, locale: str = "en-US") -> None:
        self.key = key
        self.region = region
        self.locale = locale

    def assess_wav(self, *, wav_bytes: bytes, reference_text: str) -> str:
        import azure.cognitiveservices.speech as speechsdk  # type: ignore[import-untyped]

        speech_config = speechsdk.SpeechConfig(subscription=self.key, region=self.region)
        speech_config.speech_recognition_language = self.locale
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=True) as handle:
            handle.write(wav_bytes)
            handle.flush()
            audio_config = speechsdk.audio.AudioConfig(filename=handle.name)
            pronunciation_config = speechsdk.PronunciationAssessmentConfig(
                reference_text=reference_text,
                grading_system=speechsdk.PronunciationAssessmentGradingSystem.HundredMark,
                granularity=speechsdk.PronunciationAssessmentGranularity.Word,
                enable_miscue=True,
            )
            try:
                pronunciation_config.enable_prosody_assessment()
            except AttributeError:
                pass
            recognizer = speechsdk.SpeechRecognizer(
                speech_config=speech_config, audio_config=audio_config
            )
            pronunciation_config.apply_to(recognizer)
            result = recognizer.recognize_once()
            if result.reason != speechsdk.ResultReason.RecognizedSpeech:
                detail = getattr(result, "cancellation_details", None)
                raise RuntimeError(f"Azure PA failed: {result.reason} {detail}")
            raw = result.properties.get(
                speechsdk.PropertyId.SpeechServiceResponse_JsonResult
            )
            if not raw:
                raise RuntimeError("Azure PA returned empty JSON result")
            return str(raw)


class AzurePaEngine:
    """Optional Azure Speech Pronunciation Assessment. Falls back to synthetic."""

    def __init__(
        self,
        *,
        key: str,
        region: str,
        fallback: PronunciationEngine | None = None,
        client: AzureSpeechPaClient | None = None,
    ) -> None:
        self.key = key
        self.region = region
        self._fallback = fallback or SyntheticPaEngine()
        self._client = client

    def _resolve_client(self) -> AzureSpeechPaClient | None:
        if self._client is not None:
            return self._client
        if not self.key or not self.region:
            return None
        try:
            import azure.cognitiveservices.speech as speechsdk  # noqa: F401
        except ImportError:
            return None
        return SdkAzureSpeechPaClient(key=self.key, region=self.region)

    def assess(
        self,
        *,
        audio: bytes,
        reference_text: str,
        cefr_level: str,
        stress_pattern: list[int] | None = None,
    ) -> PaResult:
        client = self._resolve_client()
        if client is None:
            return self._fallback.assess(
                audio=audio,
                reference_text=reference_text,
                cefr_level=cefr_level,
                stress_pattern=stress_pattern,
            )
        try:
            wav = to_wav_pcm16(audio)
            raw = client.assess_wav(wav_bytes=wav, reference_text=reference_text)
            return parse_azure_pa_json(
                raw,
                cefr_level=cefr_level,
                stress_pattern=stress_pattern,
                reference_text=reference_text,
            )
        except Exception:
            return self._fallback.assess(
                audio=audio,
                reference_text=reference_text,
                cefr_level=cefr_level,
                stress_pattern=stress_pattern,
            )


def get_default_pa(*, use_azure: bool, key: str = "", region: str = "") -> PronunciationEngine:
    if use_azure and key:
        return AzurePaEngine(key=key, region=region)
    return SyntheticPaEngine()


def result_to_dict(result: PaResult) -> dict:
    return {
        "engine": result.engine,
        "pronunciation": result.pronunciation,
        "completeness": result.completeness,
        "prosody": result.prosody,
        "words": [
            {"word": w.word, "accuracy": w.accuracy, "band": w.band} for w in result.words
        ],
        "stress_hint": result.stress_hint,
    }
