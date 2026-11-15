from __future__ import annotations

from datetime import date, datetime, timedelta


def completion_days(iso_timestamps: list[str]) -> set[date]:
    days: set[date] = set()
    for raw in iso_timestamps:
        try:
            # Accept date-only or full ISO timestamps.
            day = date.fromisoformat(raw[:10])
        except ValueError:
            continue
        days.add(day)
    return days


def current_streak(days: set[date], *, today: date | None = None) -> int:
    """Count consecutive days ending today or yesterday (grace if no activity today)."""
    if not days:
        return 0
    anchor = today or date.today()
    if anchor not in days and (anchor - timedelta(days=1)) not in days:
        return 0
    cursor = anchor if anchor in days else anchor - timedelta(days=1)
    streak = 0
    while cursor in days:
        streak += 1
        cursor -= timedelta(days=1)
    return streak


def parse_completed_at(value: str) -> str:
    """Normalize for storage/tests."""
    try:
        datetime.fromisoformat(value.replace("Z", "+00:00"))
        return value
    except ValueError:
        return value
