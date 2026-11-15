from __future__ import annotations

from typing import Any, Literal, Protocol

from app.facts.repository import FactRecord

DialogueContext = Literal["patient_family", "colleague_sbar", "expert_cme"]
CefrLevel = Literal["A2", "B1", "C1"]

CONTEXTS: tuple[DialogueContext, ...] = (
    "patient_family",
    "colleague_sbar",
    "expert_cme",
)


class DialogueGenerator(Protocol):
    def generate(
        self,
        *,
        facts: list[FactRecord],
        context: DialogueContext,
        cefr_level: CefrLevel,
        include_vi: bool,
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


class TemplateDialogueGenerator:
    """CI-safe generator: wraps verified fact text only (no clinical invention)."""

    def generate(
        self,
        *,
        facts: list[FactRecord],
        context: DialogueContext,
        cefr_level: CefrLevel,
        include_vi: bool,
    ) -> dict[str, Any]:
        if not facts:
            raise ValueError("At least one verified fact is required")

        lines: list[dict[str, Any]] = []
        if context == "patient_family":
            lines.extend(self._patient_family(facts, cefr_level, include_vi))
        elif context == "colleague_sbar":
            lines.extend(self._colleague_sbar(facts, cefr_level, include_vi))
        else:
            lines.extend(self._expert_cme(facts, cefr_level, include_vi))

        return {
            "context": context,
            "cefr_level": cefr_level,
            "lines": lines,
        }

    def _line(
        self,
        *,
        speaker: str,
        text: str,
        fact: FactRecord,
        include_vi: bool,
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
        return line

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
    ) -> dict[str, Any]:
        if not self.api_key:
            raise RuntimeError("GEMINI_API_KEY is not configured")
        # Gemini structured-output wiring reserved for when the key + SDK are present.
        # Fall back path for MVP: use template so production never invents facts.
        return TemplateDialogueGenerator().generate(
            facts=facts,
            context=context,
            cefr_level=cefr_level,
            include_vi=include_vi,
        )


def get_default_generator(gemini_api_key: str = "") -> DialogueGenerator:
    if gemini_api_key:
        return GeminiDialogueGenerator(gemini_api_key)
    return TemplateDialogueGenerator()
