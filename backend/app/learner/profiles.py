from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal

from app.users.db import connect, init_db

CefrPackage = Literal["A2", "B1", "C1"]


@dataclass(frozen=True)
class LearnerProfile:
    user_id: int
    lessons_per_week: int
    cefr_package: CefrPackage
    path_months: int
    created_at: str
    updated_at: str


@dataclass(frozen=True)
class LessonCompletion:
    id: int
    user_id: int
    case_id: int
    dialogue_id: int
    completed_at: str


def _now() -> str:
    return datetime.now(UTC).isoformat()


class LearnerProfileRepository:
    def __init__(self, db_path: str) -> None:
        self.db_path = db_path
        with connect(db_path) as conn:
            init_db(conn)

    def _conn(self) -> sqlite3.Connection:
        return connect(self.db_path)

    def get_or_create(self, user_id: int) -> LearnerProfile:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM learner_profiles WHERE user_id = ?", (user_id,)
            ).fetchone()
            if row:
                return LearnerProfile(
                    user_id=row["user_id"],
                    lessons_per_week=row["lessons_per_week"],
                    cefr_package=row["cefr_package"],
                    path_months=row["path_months"],
                    created_at=row["created_at"],
                    updated_at=row["updated_at"],
                )
            now = _now()
            conn.execute(
                """
                INSERT INTO learner_profiles (
                    user_id, lessons_per_week, cefr_package, path_months,
                    created_at, updated_at
                ) VALUES (?, 3, 'B1', 6, ?, ?)
                """,
                (user_id, now, now),
            )
            conn.commit()
            return LearnerProfile(
                user_id=user_id,
                lessons_per_week=3,
                cefr_package="B1",
                path_months=6,
                created_at=now,
                updated_at=now,
            )

    def update(
        self,
        user_id: int,
        *,
        lessons_per_week: int | None = None,
        cefr_package: CefrPackage | None = None,
        path_months: int | None = None,
    ) -> LearnerProfile:
        current = self.get_or_create(user_id)
        lpw = lessons_per_week if lessons_per_week is not None else current.lessons_per_week
        cefr = cefr_package if cefr_package is not None else current.cefr_package
        months = path_months if path_months is not None else current.path_months
        if lpw < 1 or lpw > 14:
            raise ValueError("lessons_per_week must be 1–14")
        if months != 6:
            raise ValueError("MVP path_months must be 6")
        now = _now()
        with self._conn() as conn:
            conn.execute(
                """
                UPDATE learner_profiles
                SET lessons_per_week = ?, cefr_package = ?, path_months = ?,
                    updated_at = ?
                WHERE user_id = ?
                """,
                (lpw, cefr, months, now, user_id),
            )
            conn.commit()
        return self.get_or_create(user_id)

    def mark_complete(
        self, *, user_id: int, case_id: int, dialogue_id: int
    ) -> LessonCompletion:
        now = _now()
        with self._conn() as conn:
            conn.execute(
                """
                INSERT INTO lesson_completions (
                    user_id, case_id, dialogue_id, completed_at
                ) VALUES (?, ?, ?, ?)
                ON CONFLICT(user_id, dialogue_id) DO UPDATE SET
                    completed_at = excluded.completed_at
                """,
                (user_id, case_id, dialogue_id, now),
            )
            conn.commit()
            row = conn.execute(
                """
                SELECT * FROM lesson_completions
                WHERE user_id = ? AND dialogue_id = ?
                """,
                (user_id, dialogue_id),
            ).fetchone()
            assert row is not None
            return LessonCompletion(
                id=row["id"],
                user_id=row["user_id"],
                case_id=row["case_id"],
                dialogue_id=row["dialogue_id"],
                completed_at=row["completed_at"],
            )

    def list_completions(self, user_id: int) -> list[LessonCompletion]:
        with self._conn() as conn:
            rows = conn.execute(
                """
                SELECT * FROM lesson_completions
                WHERE user_id = ?
                ORDER BY id ASC
                """,
                (user_id,),
            ).fetchall()
            return [
                LessonCompletion(
                    id=row["id"],
                    user_id=row["user_id"],
                    case_id=row["case_id"],
                    dialogue_id=row["dialogue_id"],
                    completed_at=row["completed_at"],
                )
                for row in rows
            ]

    def completion_timestamps(self, user_id: int) -> list[str]:
        return [row.completed_at for row in self.list_completions(user_id)]
