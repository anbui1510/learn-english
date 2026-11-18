from __future__ import annotations

from studio.manifest import fetch_case_rows


def case_status(case_id: str) -> str:
    """Return a printable pipeline summary for a case."""
    case, dialogues, assets = fetch_case_rows(case_id)
    if case is None:
        raise FileNotFoundError(f"Case not indexed: {case_id}")

    assets_by_dialogue: dict[str, dict[str, str]] = {}
    for row in assets:
        stem = row["dialogue_id"]
        bucket = assets_by_dialogue.setdefault(stem, {})
        bucket[row["kind"]] = row["status"]

    lines: list[str] = [
        f"Case: {case_id}",
        f"Title: {case['title']}",
        f"Case status: {case['status']}",
        "",
        "Dialogues:",
    ]
    if not dialogues:
        lines.append("  (none)")
    else:
        for row in dialogues:
            stem = row["id"]
            parts = [f"  {stem}", f"status={row['status']}"]
            audio = assets_by_dialogue.get(stem, {}).get("audio")
            video = assets_by_dialogue.get(stem, {}).get("video")
            if audio:
                parts.append(f"audio={audio}")
            if video:
                parts.append(f"video={video}")
            lines.append("  ".join(parts))

    accepted = sum(1 for r in dialogues if r["status"] == "accepted")
    lines.extend(
        [
            "",
            f"Summary: {len(dialogues)} dialogues, {accepted} accepted",
        ]
    )
    return "\n".join(lines) + "\n"