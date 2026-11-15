from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Any

from app.users.db import connect, init_db


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _tomorrow() -> str:
    return (date.today() + timedelta(days=1)).isoformat()


@dataclass(frozen=True)
class SrsCard:
    id: int
    user_id: int
    phrase: str
    source_attempt_id: int | None
    band: str
    due_at: str
    done_at: str | None
    created_at: str


def _row(row: sqlite3.Row) -> SrsCard:
    return SrsCard(
        id=row["id"],
        user_id=row["user_id"],
        phrase=row["phrase"],
        source_attempt_id=row["source_attempt_id"],
        band=row["band"],
        due_at=row["due_at"],
        done_at=row["done_at"],
        created_at=row["created_at"],
    )


class SrsRepository:
    """Simple T+1 spaced repetition for weak PA phrases."""

    def __init__(self, db_path: str) -> None:
        self.db_path = db_path
        with connect(db_path) as conn:
            init_db(conn)

    def _conn(self) -> sqlite3.Connection:
        return connect(self.db_path)

    def enqueue_from_score(
        self,
        *,
        user_id: int,
        attempt_id: int | None,
        score: dict[str, Any],
    ) -> list[SrsCard]:
        words = score.get("words") or []
        weak = [
            w
            for w in words
            if isinstance(w, dict) and w.get("band") in {"red", "yellow"}
        ]
        if not weak:
            return []
        due = _tomorrow()
        created: list[SrsCard] = []
        with self._conn() as conn:
            for item in weak:
                phrase = str(item.get("word") or "").strip()
                band = str(item.get("band") or "red")
                if not phrase:
                    continue
                existing = conn.execute(
                    """
                    SELECT * FROM srs_cards
                    WHERE user_id = ? AND phrase = ?
                    """,
                    (user_id, phrase),
                ).fetchone()
                if existing is None:
                    cur = conn.execute(
                        """
                        INSERT INTO srs_cards (
                            user_id, phrase, source_attempt_id, band,
                            due_at, done_at, created_at
                        ) VALUES (?, ?, ?, ?, ?, NULL, ?)
                        """,
                        (user_id, phrase, attempt_id, band, due, _now()),
                    )
                    row = conn.execute(
                        "SELECT * FROM srs_cards WHERE id = ?",
                        (int(cur.lastrowid),),
                    ).fetchone()
                    assert row is not None
                    created.append(_row(row))
                    continue
                # Re-queue: clear done, bump band severity, keep earliest due
                new_due = existing["due_at"]
                if existing["done_at"]:
                    new_due = due
                elif due < existing["due_at"]:
                    new_due = due
                prefer_band = (
                    "red"
                    if band == "red" or existing["band"] == "red"
                    else existing["band"]
                )
                conn.execute(
                    """
                    UPDATE srs_cards
                    SET source_attempt_id = ?,
                        band = ?,
                        due_at = ?,
                        done_at = NULL
                    WHERE id = ?
                    """,
                    (attempt_id, prefer_band, new_due, existing["id"]),
                )
                row = conn.execute(
                    "SELECT * FROM srs_cards WHERE id = ?",
                    (existing["id"],),
                ).fetchone()
                assert row is not None
                created.append(_row(row))
            conn.commit()
        return created

    def list_due(
        self, user_id: int, *, on_or_before: str | None = None
    ) -> list[SrsCard]:
        day = on_or_before or date.today().isoformat()
        with self._conn() as conn:
            rows = conn.execute(
                """
                SELECT * FROM srs_cards
                WHERE user_id = ?
                  AND done_at IS NULL
                  AND due_at <= ?
                ORDER BY due_at ASC, id ASC
                """,
                (user_id, day),
            ).fetchall()
            return [_row(r) for r in rows]

    def mark_done(self, *, card_id: int, user_id: int) -> SrsCard | None:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM srs_cards WHERE id = ? AND user_id = ?",
                (card_id, user_id),
            ).fetchone()
            if row is None:
                return None
            conn.execute(
                "UPDATE srs_cards SET done_at = ? WHERE id = ?",
                (_now(), card_id),
            )
            conn.commit()
            updated = conn.execute(
                "SELECT * FROM srs_cards WHERE id = ?", (card_id,)
            ).fetchone()
            assert updated is not None
            return _row(updated)
