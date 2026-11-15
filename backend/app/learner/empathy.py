from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Protocol

DISCLAIMER = (
    "Empathy scoring is a practice aid only and does not replace clinical counseling."
)


@dataclass(frozen=True)
class EmpathyResult:
    engine: str
    score: float
    rubric: dict[str, float]
    feedback: str
    disclaimer: str = DISCLAIMER


class EmpathyEngine(Protocol):
    def score(self, *, transcript_or_context: str, audio_len: int) -> EmpathyResult: ...


def _unit(seed: str) -> float:
    digest = hashlib.sha256(seed.encode("utf-8")).hexdigest()
    return int(digest[:8], 16) / 0xFFFFFFFF


class SyntheticEmpathyScorer:
    """CI-safe empathy rubric without calling Gemini."""

    def score(self, *, transcript_or_context: str, audio_len: int) -> EmpathyResult:
        warmth = round(55 + _unit(f"warmth:{transcript_or_context}") * 40, 1)
        clarity = round(50 + _unit(f"clarity:{transcript_or_context}") * 45, 1)
        reassurance = round(45 + _unit(f"reassure:{audio_len}") * 50, 1)
        if audio_len < 32:
            warmth = min(warmth, 40)
            reassurance = min(reassurance, 35)
        overall = round((warmth + clarity + reassurance) / 3, 1)
        if overall >= 75:
            feedback = "Tone sounds calm and supportive for a family conversation."
        elif overall >= 55:
            feedback = "Add a brief reassuring phrase before clinical details."
        else:
            feedback = "Slow down and acknowledge caregiver concern before advising."
        return EmpathyResult(
            engine="synthetic",
            score=overall,
            rubric={
                "warmth": warmth,
                "clarity": clarity,
                "reassurance": reassurance,
            },
            feedback=feedback,
        )


class GeminiEmpathyScorer:
    """Optional Gemini structured rubric; falls back to synthetic without a key."""

    def __init__(self, *, api_key: str, fallback: EmpathyEngine | None = None) -> None:
        self.api_key = api_key
        self._fallback = fallback or SyntheticEmpathyScorer()

    def score(self, *, transcript_or_context: str, audio_len: int) -> EmpathyResult:
        if not self.api_key:
            return self._fallback.score(
                transcript_or_context=transcript_or_context, audio_len=audio_len
            )
        # Structured Gemini path reserved until live key + prompt pack land.
        return self._fallback.score(
            transcript_or_context=transcript_or_context, audio_len=audio_len
        )


def get_default_empathy(*, use_gemini: bool, api_key: str = "") -> EmpathyEngine:
    if use_gemini and api_key:
        return GeminiEmpathyScorer(api_key=api_key)
    return SyntheticEmpathyScorer()


def empathy_to_dict(result: EmpathyResult) -> dict:
    return {
        "engine": result.engine,
        "score": result.score,
        "rubric": result.rubric,
        "feedback": result.feedback,
        "disclaimer": result.disclaimer,
    }
