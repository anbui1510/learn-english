from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime

from app.users.db import connect, init_db


def _today() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%d")


@dataclass(frozen=True)
class PaUsageRow:
    user_id: int
    email: str | None
    usage_day: str
    score_count: int
    estimated_cost_usd: float


class PaRateLimiter:
    """Per-user daily cap for pronunciation scoring calls (cost control)."""

    def __init__(
        self,
        db_path: str,
        *,
        daily_limit: int,
        cost_per_score_usd: float = 0.0,
    ) -> None:
        self.db_path = db_path
        self.daily_limit = daily_limit
        self.cost_per_score_usd = cost_per_score_usd
        with connect(db_path) as conn:
            init_db(conn)

    def _conn(self) -> sqlite3.Connection:
        return connect(self.db_path)

    def check_and_increment(self, user_id: int) -> tuple[bool, int, int]:
        """Return (allowed, used_after, limit)."""
        day = _today()
        with self._conn() as conn:
            row = conn.execute(
                """
                SELECT score_count FROM pa_score_usage
                WHERE user_id = ? AND usage_day = ?
                """,
                (user_id, day),
            ).fetchone()
            used = int(row["score_count"]) if row else 0
            if used >= self.daily_limit:
                return False, used, self.daily_limit
            if row is None:
                conn.execute(
                    """
                    INSERT INTO pa_score_usage (user_id, usage_day, score_count)
                    VALUES (?, ?, 1)
                    """,
                    (user_id, day),
                )
                used_after = 1
            else:
                conn.execute(
                    """
                    UPDATE pa_score_usage
                    SET score_count = score_count + 1
                    WHERE user_id = ? AND usage_day = ?
                    """,
                    (user_id, day),
                )
                used_after = used + 1
            conn.commit()
            return True, used_after, self.daily_limit

    def usage_report(self, *, days: int = 14) -> list[PaUsageRow]:
        with self._conn() as conn:
            rows = conn.execute(
                """
                SELECT u.user_id, usr.email, u.usage_day, u.score_count
                FROM pa_score_usage u
                LEFT JOIN users usr ON usr.id = u.user_id
                WHERE u.usage_day >= date('now', ?)
                ORDER BY u.usage_day DESC, u.user_id ASC
                """,
                (f"-{max(days - 1, 0)} day",),
            ).fetchall()
            return [
                PaUsageRow(
                    user_id=int(row["user_id"]),
                    email=row["email"],
                    usage_day=row["usage_day"],
                    score_count=int(row["score_count"]),
                    estimated_cost_usd=round(
                        int(row["score_count"]) * self.cost_per_score_usd, 4
                    ),
                )
                for row in rows
            ]
