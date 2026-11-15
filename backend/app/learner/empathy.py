from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass
from typing import Any, Protocol

import httpx

logger = logging.getLogger(__name__)

DISCLAIMER = (
    "Empathy scoring is a practice aid only and does not replace clinical counseling."
)

SAMPLE_PHRASE_LOW = (
    "I can see this is worrying for you. Let us walk through the plan together."
)
SAMPLE_PHRASE_MID = (
    "Thank you for sharing that. Here is what we can do next, step by step."
)

EMPATHY_RESPONSE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "warmth": {"type": "number"},
        "clarity": {"type": "number"},
        "reassurance": {"type": "number"},
        "feedback": {"type": "string"},
        "coaching_tip": {"type": "string"},
        "sample_phrase": {"type": "string"},
    },
    "required": ["warmth", "clarity", "reassurance", "feedback"],
}

_GEMINI_MODEL = "gemini-2.0-flash"
_GEMINI_URL = (
    f"https://generativelanguage.googleapis.com/v1beta/models/"
    f"{_GEMINI_MODEL}:generateContent"
)


@dataclass(frozen=True)
class EmpathyResult:
    engine: str
    score: float
    rubric: dict[str, float]
    feedback: str
    disclaimer: str = DISCLAIMER
    coaching_tip: str | None = None
    sample_phrase: str | None = None


class EmpathyEngine(Protocol):
    def score(self, *, transcript_or_context: str, audio_len: int) -> EmpathyResult: ...


class GeminiEmpathyClient(Protocol):
    def generate_empathy_json(self, *, prompt: str) -> dict[str, Any]: ...


def _unit(seed: str) -> float:
    digest = hashlib.sha256(seed.encode("utf-8")).hexdigest()
    return int(digest[:8], 16) / 0xFFFFFFFF


def _coaching_for_score(overall: float) -> tuple[str | None, str | None]:
    if overall >= 75:
        return None, None
    if overall >= 55:
        return (
            "Try a warmer intonation on the first sentence, then give clinical details.",
            SAMPLE_PHRASE_MID,
        )
    return (
        "Acknowledge caregiver concern first, then slow your pace before advising.",
        SAMPLE_PHRASE_LOW,
    )


def _clamp_score(value: Any) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Invalid empathy score: {value!r}") from exc
    return round(min(100.0, max(0.0, number)), 1)


def parse_empathy_payload(payload: dict[str, Any], *, engine: str) -> EmpathyResult:
    warmth = _clamp_score(payload.get("warmth"))
    clarity = _clamp_score(payload.get("clarity"))
    reassurance = _clamp_score(payload.get("reassurance"))
    overall = round((warmth + clarity + reassurance) / 3, 1)
    feedback = str(payload.get("feedback") or "").strip()
    if not feedback:
        feedback = "Review warmth, clarity, and reassurance in your reply."

    tip = str(payload.get("coaching_tip") or "").strip() or None
    sample = str(payload.get("sample_phrase") or "").strip() or None
    if overall >= 75:
        tip, sample = None, None
    elif tip is None or sample is None:
        default_tip, default_sample = _coaching_for_score(overall)
        tip = tip or default_tip
        sample = sample or default_sample

    return EmpathyResult(
        engine=engine,
        score=overall,
        rubric={
            "warmth": warmth,
            "clarity": clarity,
            "reassurance": reassurance,
        },
        feedback=feedback,
        coaching_tip=tip,
        sample_phrase=sample,
    )


def build_empathy_prompt(*, transcript_or_context: str, audio_len: int) -> str:
    return (
        "You are scoring a pediatric resident's spoken reply to a caregiver "
        "during free-speech role-play (bad-news / counseling practice).\n"
        "Score warmth, clarity, and reassurance from 0–100.\n"
        "If overall empathy would be below 75, include coaching_tip and a short "
        "sample_phrase the learner can practice aloud.\n"
        "Do not invent clinical diagnoses; focus on communication tone.\n"
        f"Audio length (bytes proxy): {audio_len}\n"
        f"Learner utterance / context:\n{transcript_or_context.strip() or '(empty)'}\n"
    )


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
        tip, sample = _coaching_for_score(overall)
        return EmpathyResult(
            engine="synthetic",
            score=overall,
            rubric={
                "warmth": warmth,
                "clarity": clarity,
                "reassurance": reassurance,
            },
            feedback=feedback,
            coaching_tip=tip,
            sample_phrase=sample,
        )


class HttpxGeminiEmpathyClient:
    """Calls Gemini generateContent over HTTPS (no SDK required)."""

    def __init__(
        self,
        *,
        api_key: str,
        timeout_seconds: float = 20.0,
        http_client: httpx.Client | None = None,
    ) -> None:
        self.api_key = api_key
        self.timeout_seconds = timeout_seconds
        self._http = http_client

    def generate_empathy_json(self, *, prompt: str) -> dict[str, Any]:
        body = {
            "contents": [{"role": "user", "parts": [{"text": prompt}]}],
            "generationConfig": {
                "temperature": 0.2,
                "responseMimeType": "application/json",
                "responseSchema": EMPATHY_RESPONSE_SCHEMA,
            },
        }
        owns_client = self._http is None
        client = self._http or httpx.Client(timeout=self.timeout_seconds)
        try:
            response = client.post(
                _GEMINI_URL,
                params={"key": self.api_key},
                json=body,
            )
            response.raise_for_status()
            data = response.json()
        finally:
            if owns_client:
                client.close()

        try:
            text = data["candidates"][0]["content"]["parts"][0]["text"]
        except (KeyError, IndexError, TypeError) as exc:
            raise RuntimeError("Gemini empathy response missing text") from exc
        parsed = json.loads(text)
        if not isinstance(parsed, dict):
            raise RuntimeError("Gemini empathy JSON must be an object")
        return parsed


class GeminiEmpathyScorer:
    """Gemini structured rubric with synthetic fallback on any failure."""

    def __init__(
        self,
        *,
        api_key: str,
        client: GeminiEmpathyClient | None = None,
        fallback: EmpathyEngine | None = None,
    ) -> None:
        self.api_key = api_key
        self._client = client
        self._fallback = fallback or SyntheticEmpathyScorer()

    def _resolve_client(self) -> GeminiEmpathyClient | None:
        if self._client is not None:
            return self._client
        if not self.api_key:
            return None
        return HttpxGeminiEmpathyClient(api_key=self.api_key)

    def score(self, *, transcript_or_context: str, audio_len: int) -> EmpathyResult:
        client = self._resolve_client()
        if client is None:
            return self._fallback.score(
                transcript_or_context=transcript_or_context, audio_len=audio_len
            )
        try:
            prompt = build_empathy_prompt(
                transcript_or_context=transcript_or_context,
                audio_len=audio_len,
            )
            payload = client.generate_empathy_json(prompt=prompt)
            return parse_empathy_payload(payload, engine="gemini")
        except Exception:
            logger.warning(
                "Gemini empathy scoring failed; falling back to synthetic",
                exc_info=True,
            )
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
        "coaching_tip": result.coaching_tip,
        "sample_phrase": result.sample_phrase,
    }
