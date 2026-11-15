from __future__ import annotations

from typing import Any


def build_shadowing_cards(
    lines: list[dict[str, Any]], *, target: int = 10
) -> list[dict[str, Any]]:
    """Select up to 10 cards: prefer is_key_phrase, ensure SBAR if present, pad."""
    keyed = [
        (index, line)
        for index, line in enumerate(lines)
        if line.get("is_key_phrase")
    ]
    sbar = [
        (index, line)
        for index, line in enumerate(lines)
        if "SBAR" in str(line.get("text") or "")
    ]
    chosen: list[tuple[int, dict[str, Any]]] = []
    seen: set[int] = set()

    def add(item: tuple[int, dict[str, Any]]) -> None:
        index, _ = item
        if index in seen or len(chosen) >= target:
            return
        seen.add(index)
        chosen.append(item)

    for item in keyed:
        add(item)
    for item in sbar:
        add(item)
    for index, line in enumerate(lines):
        add((index, line))

    # Pad by cycling if fewer than target
    if lines and len(chosen) < target:
        cycle = 0
        while len(chosen) < target:
            index = cycle % len(lines)
            line = lines[index]
            chosen.append((index, line))
            cycle += 1

    cards: list[dict[str, Any]] = []
    for ordinal, (line_index, line) in enumerate(chosen[:target]):
        cards.append(
            {
                "card_index": ordinal,
                "line_index": line_index,
                "speaker": line.get("speaker"),
                "text": line.get("text"),
                "text_vi": line.get("text_vi"),
                "fact_ids": list(line.get("fact_ids") or []),
                "is_key_phrase": bool(line.get("is_key_phrase")),
            }
        )
    return cards
