from __future__ import annotations

from typing import Any, Literal

SessionKind = Literal["standard", "presentation"]

# Comfortable medical-dialogue speaking rate at 1x (words per minute).
WORDS_PER_MINUTE = 130.0
# MVP target ~2 minutes.
DURATION_WARN_SECONDS = 150.0
# G3 presentation / CME talk target ~10 minutes.
PRESENTATION_TARGET_SECONDS = 600.0
PRESENTATION_MIN_SECONDS = 480.0
PRESENTATION_MAX_SECONDS = 720.0


def estimate_seconds(lines: list[dict[str, Any]]) -> float:
    words = 0
    for line in lines:
        text = str(line.get("text") or "")
        words += len(text.split())
    if words == 0:
        return 0.0
    return round((words / WORDS_PER_MINUTE) * 60.0, 1)


def duration_warning(estimated_seconds: float) -> bool:
    return estimated_seconds > DURATION_WARN_SECONDS


def session_duration_warning(
    estimated_seconds: float, *, session_kind: SessionKind = "standard"
) -> bool:
    if session_kind == "presentation":
        return (
            estimated_seconds < PRESENTATION_MIN_SECONDS
            or estimated_seconds > PRESENTATION_MAX_SECONDS
        )
    return duration_warning(estimated_seconds)
