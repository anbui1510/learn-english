from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Literal, Protocol

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


class PronunciationEngine(Protocol):
    def assess(
        self,
        *,
        audio: bytes,
        reference_text: str,
        cefr_level: str,
        stress_pattern: list[int] | None = None,
    ) -> PaResult: ...


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
            # Tiny audio → assume incomplete / poor attempt
            if len(audio) < 32:
                base = min(base, 45)
            accuracy = round(base, 1)
            scored.append(
                WordScore(word=word, accuracy=accuracy, band=band_for_accuracy(accuracy))
            )
        avg = round(sum(w.accuracy for w in scored) / len(scored), 1)
        completeness = 40.0 if len(audio) < 32 else min(100.0, 70 + len(audio) % 30)
        prosody = round(50 + _stable_unit(reference_text) * 45, 1)
        stress_hint = None
        if cefr_level.upper() == "C1" and stress_pattern:
            peak = max(stress_pattern)
            stressed = [
                words[i] if i < len(words) else "?"
                for i, mark in enumerate(stress_pattern)
                if mark == peak
            ]
            if stressed:
                stress_hint = (
                    f"Stress the highlighted syllable(s) in: {', '.join(stressed[:3])}"
                )
        return PaResult(
            engine="synthetic",
            pronunciation=avg,
            completeness=round(completeness, 1),
            prosody=prosody,
            words=scored,
            stress_hint=stress_hint,
        )


class AzurePaEngine:
    """Optional Azure Speech Pronunciation Assessment. Falls back to synthetic."""

    def __init__(
        self,
        *,
        key: str,
        region: str,
        fallback: PronunciationEngine | None = None,
    ) -> None:
        self.key = key
        self.region = region
        self._fallback = fallback or SyntheticPaEngine()

    def assess(
        self,
        *,
        audio: bytes,
        reference_text: str,
        cefr_level: str,
        stress_pattern: list[int] | None = None,
    ) -> PaResult:
        try:
            import azure.cognitiveservices.speech as speechsdk  # type: ignore[import-untyped]
        except ImportError:
            return self._fallback.assess(
                audio=audio,
                reference_text=reference_text,
                cefr_level=cefr_level,
                stress_pattern=stress_pattern,
            )
        # Full Azure wiring needs PCM conversion + continuous recognition.
        # Until credentials + format pipeline are production-ready, keep synthetic
        # path while proving the SDK import works when installed.
        _ = speechsdk
        if not self.key or not self.region:
            return self._fallback.assess(
                audio=audio,
                reference_text=reference_text,
                cefr_level=cefr_level,
                stress_pattern=stress_pattern,
            )
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
