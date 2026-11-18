from __future__ import annotations

CONTEXTS = ("patient_family", "colleague_sbar", "expert_cme")
CEFR_LEVELS = ("A2", "B1", "C1")


def dialogue_stem(context: str, cefr: str) -> str:
    return f"{context}__{cefr}"