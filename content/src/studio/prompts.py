from __future__ import annotations

from typing import Any

_CONTEXT_GUIDANCE: dict[str, str] = {
    "patient_family": (
        "Layperson patient–family explanation. Warm, reassuring tone. "
        "Use simple medical terms with brief clarifications. Doctors speak to a parent or adult patient."
    ),
    "colleague_sbar": (
        "Handover between clinicians using SBAR (Situation, Background, Assessment, Recommendation). "
        "Professional, concise, colleague-to-colleague."
    ),
    "expert_cme": (
        "Formal continuing-medical-education dialogue between subject-matter expert and learner. "
        "Evidence-oriented, precise terminology."
    ),
}

_CEFR_GUIDANCE: dict[str, str] = {
    "A2": (
        "CEFR A2: short sentences, high-frequency vocabulary, about 4 turns (~2 minutes spoken)."
    ),
    "B1": (
        "CEFR B1: everyday and some academic vocabulary, about 5 turns (~2 minutes spoken)."
    ),
    "C1": (
        "CEFR C1: nuanced, formal where appropriate, about 6 turns (~2 minutes spoken)."
    ),
}


def system_instruction(context: str, cefr: str) -> str:
    return (
        "You write English clinical dialogues grounded strictly in the provided source text. "
        "Every factual claim must be supportable from the source. "
        "Output JSON only, matching the given schema.\n\n"
        f"Context: {_CONTEXT_GUIDANCE[context]}\n"
        f"Level: {_CEFR_GUIDANCE[cefr]}\n"
        "Requirements:\n"
        "- Set status to needs_review.\n"
        "- Alternate speakers appropriate to the context (doctor/parent, doctor/colleague, expert/learner).\n"
        "- First line must include source_quote: a short verbatim phrase from source.txt.\n"
        "- Include text_vi on roughly half the lines (Vietnamese gloss).\n"
        "- Do not invent facts not present in the source."
    )


def user_prompt(
    *,
    source_text: str,
    case_meta: dict[str, Any],
    context: str,
    cefr: str,
) -> str:
    title = case_meta.get("title", "")
    isbn = case_meta.get("isbn", "")
    edition = case_meta.get("edition", "")
    meta_bits = [bit for bit in (title, isbn, edition) if bit]
    header = " | ".join(str(b) for b in meta_bits) if meta_bits else case_meta.get("id", "case")

    return (
        f"Case metadata: {header}\n"
        f"Target dialogue context: {context}\n"
        f"Target CEFR: {cefr}\n\n"
        "Source text (ground dialogue only in this material):\n"
        "---\n"
        f"{source_text.strip()}\n"
        "---\n"
        f'Produce one studio dialogue JSON object with context="{context}" and cefr_level="{cefr}".'
    )