from __future__ import annotations

from typing import Any

from app.cases.repository import CaseRecord
from app.dialogues.duration import duration_warning, estimate_seconds
from app.dialogues.generator import (
    CONTEXTS,
    CefrLevel,
    DialogueContext,
    DialogueGenerator,
    get_default_generator,
)
from app.dialogues.repository import DialogueRecord, DialogueRepository
from app.facts.repository import FactRepository


class GenerateError(ValueError):
    """Raised when dialogues cannot be generated."""


def generate_for_case(
    *,
    case: CaseRecord,
    contexts: list[DialogueContext],
    cefr_level: CefrLevel,
    include_vi: bool,
    facts: FactRepository,
    dialogues: DialogueRepository,
    generator: DialogueGenerator | None = None,
    replace_existing: bool = True,
) -> list[DialogueRecord]:
    if case.status != "published":
        raise GenerateError("Case must be published before generate-dialogues")
    if not contexts:
        raise GenerateError("Select at least one context")
    unknown = [c for c in contexts if c not in CONTEXTS]
    if unknown:
        raise GenerateError(f"Unknown context(s): {', '.join(unknown)}")

    verified = facts.list_for_case(case.id, status="verified")
    if not verified:
        raise GenerateError("No verified facts available for dialogue generation")

    active = generator or get_default_generator()
    if replace_existing:
        dialogues.delete_for_case(case.id)

    created: list[DialogueRecord] = []
    for context in contexts:
        payload: dict[str, Any] = active.generate(
            facts=verified,
            context=context,
            cefr_level=cefr_level,
            include_vi=include_vi,
        )
        # Ensure fact_ids only reference verified facts for this case
        verified_ids = {str(f.id) for f in verified}
        for line in payload["lines"]:
            ids = line.get("fact_ids") or []
            if not ids or any(fid not in verified_ids for fid in ids):
                raise GenerateError("Dialogue line fact_ids must cite verified facts")
        seconds = estimate_seconds(payload["lines"])
        warn = duration_warning(seconds)
        created.append(
            dialogues.insert_dialogue(
                case_id=case.id,
                payload=payload,
                estimated_seconds=seconds,
                duration_warning=warn,
            )
        )
    return created
