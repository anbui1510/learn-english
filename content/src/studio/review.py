from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from studio.models import CEFR_LEVELS, CONTEXTS, dialogue_stem
from studio.paths import cases_root


def _utc_now_z() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _case_dir(case_id: str) -> Path:
    case_dir = cases_root() / case_id
    if not case_dir.is_dir():
        raise FileNotFoundError(f"Case not found: {case_id}")
    return case_dir


def _dialogue_path(case_dir: Path, stem: str) -> Path:
    path = case_dir / "dialogues" / f"{stem}.json"
    if not path.is_file():
        raise FileNotFoundError(f"Dialogue not found: {stem}")
    return path


def _load_review(case_dir: Path) -> dict[str, dict[str, object]]:
    review_path = case_dir / "review.json"
    if not review_path.is_file():
        return {}
    return json.loads(review_path.read_text(encoding="utf-8"))


def _save_review(case_dir: Path, review: dict[str, dict[str, object]]) -> None:
    (case_dir / "review.json").write_text(
        json.dumps(review, indent=2) + "\n", encoding="utf-8"
    )


def _set_status(case_id: str, stem: str, status: str, *, notes: str = "") -> None:
    case_dir = _case_dir(case_id)
    dialogue_path = _dialogue_path(case_dir, stem)
    data = json.loads(dialogue_path.read_text(encoding="utf-8"))
    data["status"] = status
    dialogue_path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")

    review = _load_review(case_dir)
    entry: dict[str, object] = {
        "status": status,
        "notes": notes,
        "reviewed_at": _utc_now_z(),
    }
    review[stem] = entry
    _save_review(case_dir, review)


def list_reviews(case_id: str) -> list[dict[str, object]]:
    case_dir = _case_dir(case_id)
    review = _load_review(case_dir)
    rows: list[dict[str, object]] = []
    for context in CONTEXTS:
        for cefr in CEFR_LEVELS:
            stem = dialogue_stem(context, cefr)
            dialogue_path = case_dir / "dialogues" / f"{stem}.json"
            file_status = None
            if dialogue_path.is_file():
                data = json.loads(dialogue_path.read_text(encoding="utf-8"))
                file_status = data.get("status")
            rev = review.get(stem, {})
            rows.append(
                {
                    "stem": stem,
                    "context": context,
                    "cefr_level": cefr,
                    "status": rev.get("status") or file_status or "missing",
                    "notes": rev.get("notes", ""),
                }
            )
    return rows


def accept_dialogue(case_id: str, stem: str) -> None:
    _set_status(case_id, stem, "accepted")


def reject_dialogue(case_id: str, stem: str, notes: str = "") -> None:
    _set_status(case_id, stem, "rejected", notes=notes)


def assert_accepted(case_id: str, stem: str, *, force: bool = False) -> None:
    if force:
        return
    case_dir = _case_dir(case_id)
    dialogue_path = _dialogue_path(case_dir, stem)
    data = json.loads(dialogue_path.read_text(encoding="utf-8"))
    if data.get("status") != "accepted":
        raise RuntimeError(
            f"Dialogue {stem} is not accepted (status={data.get('status')!r})"
        )