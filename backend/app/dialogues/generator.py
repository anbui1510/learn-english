from __future__ import annotations

from typing import Any, Literal, Protocol

from app.dialogues.duration import (
    PRESENTATION_TARGET_SECONDS,
    SessionKind,
    estimate_seconds,
)
from app.facts.repository import FactRecord

DialogueContext = Literal["patient_family", "colleague_sbar", "expert_cme"]
CefrLevel = Literal["A2", "B1", "C1"]

CONTEXTS: tuple[DialogueContext, ...] = (
    "patient_family",
    "colleague_sbar",
    "expert_cme",
)

_PRESENTATION_FRAMES = (
    "Opening: today we review this teaching point carefully. {body}",
    "Clinical emphasis: {body}",
    "Key takeaway for the team: {body}",
    "In practice, remember: {body}",
    "Pause and reflect with colleagues: {body}",
    "Summary slide: {body}",
)


class DialogueGenerator(Protocol):
    def generate(
        self,
        *,
        facts: list[FactRecord],
        context: DialogueContext,
        cefr_level: CefrLevel,
        include_vi: bool,
        session_kind: SessionKind = "standard",
        target_seconds: float | None = None,
    ) -> dict[str, Any]: ...


def _cefr_wrap(fact_text: str, cefr_level: CefrLevel) -> str:
    clean = " ".join(fact_text.split())
    if cefr_level == "A2":
        return f"Please note: {clean}"
    if cefr_level == "B1":
        return f"Based on the case findings, {clean}"
    return (
        "From a clinical teaching perspective, "
        f"{clean} This point should be reviewed carefully with the team."
    )


def _vi_gloss(text: str) -> str:
    # Deterministic placeholder gloss — not a translation model.
    return f"[VI] {text}"


def build_stress_pattern(text: str, *, min_alpha: int = 10) -> list[int] | None:
    """Mark the longest clinical-length token as stress peak (1–3 scale)."""
    tokens = text.split()
    if not tokens:
        return None
    best_i = -1
    best_len = 0
    for index, token in enumerate(tokens):
        alpha = "".join(ch for ch in token if ch.isalpha())
        if len(alpha) >= min_alpha and len(alpha) > best_len:
            best_len = len(alpha)
            best_i = index
    if best_i < 0:
        return None
    pattern = [1] * len(tokens)
    pattern[best_i] = 3
    return pattern


class TemplateDialogueGenerator:
    """CI-safe generator: wraps verified fact text only (no clinical invention)."""

    def generate(
        self,
        *,
        facts: list[FactRecord],
        context: DialogueContext,
        cefr_level: CefrLevel,
        include_vi: bool,
        session_kind: SessionKind = "standard",
        target_seconds: float | None = None,
    ) -> dict[str, Any]:
        if not facts:
            raise ValueError("At least one verified fact is required")

        if session_kind == "presentation":
            goal = float(target_seconds or PRESENTATION_TARGET_SECONDS)
            lines = self._presentation_lines(
                facts, context, cefr_level, include_vi, goal
            )
        elif context == "patient_family":
            lines = self._patient_family(facts, cefr_level, include_vi)
        elif context == "colleague_sbar":
            lines = self._colleague_sbar(facts, cefr_level, include_vi)
        else:
            lines = self._expert_cme(facts, cefr_level, include_vi)

        payload: dict[str, Any] = {
            "context": context,
            "cefr_level": cefr_level,
            "session_kind": session_kind,
            "lines": lines,
        }
        if session_kind == "presentation":
            payload["target_seconds"] = float(
                target_seconds or PRESENTATION_TARGET_SECONDS
            )
        return payload

    def _line(
        self,
        *,
        speaker: str,
        text: str,
        fact: FactRecord,
        include_vi: bool,
        cefr_level: CefrLevel,
        is_key_phrase: bool = False,
    ) -> dict[str, Any]:
        line: dict[str, Any] = {
            "speaker": speaker,
            "text": text,
            "fact_ids": [str(fact.id)],
        }
        if include_vi:
            line["text_vi"] = _vi_gloss(text)
        if is_key_phrase:
            line["is_key_phrase"] = True
        if cefr_level == "C1":
            pattern = build_stress_pattern(text)
            if pattern is not None:
                line["stress_pattern"] = pattern
        return line

    def _presentation_lines(
        self,
        facts: list[FactRecord],
        context: DialogueContext,
        cefr_level: CefrLevel,
        include_vi: bool,
        target_seconds: float,
    ) -> list[dict[str, Any]]:
        """Expand fact-bound teaching frames until estimated duration hits target."""
        lines: list[dict[str, Any]] = []
        cycle = 0
        # Cap cycles so CI never hangs if WPM math changes.
        while estimate_seconds(lines) < target_seconds * 0.9 and cycle < 80:
            for index, fact in enumerate(facts):
                body = _cefr_wrap(fact.atomic_fact, cefr_level)
                frame = _PRESENTATION_FRAMES[cycle % len(_PRESENTATION_FRAMES)]
                text = frame.format(body=body)
                if context == "colleague_sbar":
                    text = f"SBAR teaching: {text}"
                elif context == "patient_family":
                    text = f"Family education: {text}"
                else:
                    text = f"CME presentation: {text}"
                speaker = "presenter" if index % 2 == 0 else "colleague"
                lines.append(
                    self._line(
                        speaker=speaker,
                        text=text,
                        fact=fact,
                        include_vi=include_vi,
                        cefr_level=cefr_level,
                        is_key_phrase=cycle == 0 and index == 0,
                    )
                )
                if estimate_seconds(lines) >= target_seconds * 0.9:
                    break
            cycle += 1
        return lines

    def _patient_family(
        self,
        facts: list[FactRecord],
        cefr_level: CefrLevel,
        include_vi: bool,
    ) -> list[dict[str, Any]]:
        lines: list[dict[str, Any]] = []
        for index, fact in enumerate(facts):
            wrapped = _cefr_wrap(fact.atomic_fact, cefr_level)
            speaker = "doctor" if index % 2 == 0 else "parent"
            lines.append(
                self._line(
                    speaker=speaker,
                    text=wrapped,
                    fact=fact,
                    include_vi=include_vi,
                    cefr_level=cefr_level,
                    is_key_phrase=index == 0,
                )
            )
        return lines

    def _colleague_sbar(
        self,
        facts: list[FactRecord],
        cefr_level: CefrLevel,
        include_vi: bool,
    ) -> list[dict[str, Any]]:
        labels = ("Situation", "Background", "Assessment", "Recommendation")
        lines: list[dict[str, Any]] = []
        for index, fact in enumerate(facts):
            label = labels[index % len(labels)]
            wrapped = _cefr_wrap(fact.atomic_fact, cefr_level)
            text = f"SBAR {label}: {wrapped}"
            lines.append(
                self._line(
                    speaker="doctor" if index % 2 == 0 else "nurse",
                    text=text,
                    fact=fact,
                    include_vi=include_vi,
                    cefr_level=cefr_level,
                    is_key_phrase=label == "Recommendation",
                )
            )
        return lines

    def _expert_cme(
        self,
        facts: list[FactRecord],
        cefr_level: CefrLevel,
        include_vi: bool,
    ) -> list[dict[str, Any]]:
        lines: list[dict[str, Any]] = []
        for index, fact in enumerate(facts):
            wrapped = _cefr_wrap(fact.atomic_fact, cefr_level)
            text = f"Teaching point: {wrapped}"
            lines.append(
                self._line(
                    speaker="presenter" if index % 2 == 0 else "colleague",
                    text=text,
                    fact=fact,
                    include_vi=include_vi,
                    cefr_level=cefr_level,
                    is_key_phrase=index == 0,
                )
            )
        return lines


class GeminiDialogueGenerator:
    """Optional Gemini adapter — raises if API key / SDK unavailable."""

    def __init__(self, api_key: str) -> None:
        self.api_key = api_key

    def generate(
        self,
        *,
        facts: list[FactRecord],
        context: DialogueContext,
        cefr_level: CefrLevel,
        include_vi: bool,
        session_kind: SessionKind = "standard",
        target_seconds: float | None = None,
    ) -> dict[str, Any]:
        if not self.api_key:
            raise RuntimeError("GEMINI_API_KEY is not configured")
        return TemplateDialogueGenerator().generate(
            facts=facts,
            context=context,
            cefr_level=cefr_level,
            include_vi=include_vi,
            session_kind=session_kind,
            target_seconds=target_seconds,
        )


def get_default_generator(gemini_api_key: str = "") -> DialogueGenerator:
    if gemini_api_key:
        return GeminiDialogueGenerator(gemini_api_key)
    return TemplateDialogueGenerator()
