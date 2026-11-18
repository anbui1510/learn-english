from __future__ import annotations

import json
import re
from pathlib import Path

from studio.models import CEFR_LEVELS, CONTEXTS, dialogue_stem
from studio.paths import cases_root
from studio.schema_validate import validate_studio_dialogue

_SPEAKERS: dict[str, tuple[str, str]] = {
    "patient_family": ("doctor", "parent"),
    "colleague_sbar": ("doctor", "colleague"),
    "expert_cme": ("expert", "learner"),
}

_LINE_COUNTS = {"A2": 4, "B1": 5, "C1": 6}


def _first_sentence(source_text: str) -> str:
    text = source_text.strip()
    if not text:
        return ""
    match = re.split(r"(?<=[.!?])\s+", text, maxsplit=1)
    return match[0].strip()


def _short_quote(sentence: str, max_len: int = 80) -> str:
    quote = sentence.strip()
    if len(quote) <= max_len:
        return quote
    return quote[: max_len - 3].rstrip() + "..."


def _mock_dialogue_payload(
    context: str, cefr: str, source_quote: str
) -> dict[str, object]:
    speaker_a, speaker_b = _SPEAKERS[context]
    n_lines = _LINE_COUNTS[cefr]
    lines: list[dict[str, object]] = []
    for i in range(n_lines):
        speaker = speaker_a if i % 2 == 0 else speaker_b
        line: dict[str, object] = {
            "speaker": speaker,
            "text": f"[{context}/{cefr}] Line {i + 1}: {source_quote}",
        }
        if i == 0:
            line["source_quote"] = source_quote
        if i % 2 == 0:
            line["text_vi"] = f"(VI) {source_quote[:40]}"
        lines.append(line)
    return {
        "context": context,
        "cefr_level": cefr,
        "status": "needs_review",
        "lines": lines,
    }


def _case_dir(case_id: str) -> Path:
    case_dir = cases_root() / case_id
    if not (case_dir / "source.txt").is_file():
        raise FileNotFoundError(f"Case not found or missing source: {case_id}")
    return case_dir


def _existing_status(dialogue_path: Path) -> str | None:
    if not dialogue_path.is_file():
        return None
    try:
        data = json.loads(dialogue_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    status = data.get("status")
    return str(status) if isinstance(status, str) else None


def _write_dialogue(path: Path, payload: dict[str, object]) -> None:
    validate_studio_dialogue(payload)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _touch_review(case_dir: Path, stem: str) -> None:
    review_path = case_dir / "review.json"
    review = json.loads(review_path.read_text(encoding="utf-8"))
    review[stem] = {
        "status": "needs_review",
        "notes": "",
        "reviewed_at": "",
    }
    review_path.write_text(json.dumps(review, indent=2) + "\n", encoding="utf-8")


def generate_dialogues(case_id: str, *, mock: bool = False) -> list[Path]:
    if not mock:
        raise NotImplementedError(
            "Live Gemini generation is not implemented yet; use mock=True"
        )

    case_dir = _case_dir(case_id)
    source_text = (case_dir / "source.txt").read_text(encoding="utf-8")
    source_quote = _short_quote(_first_sentence(source_text))
    if not source_quote:
        raise ValueError(f"Case {case_id} has empty source.txt")

    dialogues_dir = case_dir / "dialogues"
    dialogues_dir.mkdir(parents=True, exist_ok=True)

    written: list[Path] = []
    for context in CONTEXTS:
        for cefr in CEFR_LEVELS:
            stem = dialogue_stem(context, cefr)
            out_path = dialogues_dir / f"{stem}.json"
            if _existing_status(out_path) == "accepted":
                written.append(out_path)
                continue

            payload = _mock_dialogue_payload(context, cefr, source_quote)
            _write_dialogue(out_path, payload)
            _touch_review(case_dir, stem)
            written.append(out_path)

    return written