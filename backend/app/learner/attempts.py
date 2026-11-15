from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal

from app.users.db import connect, init_db

AttemptMode = Literal["shadowing", "role_play"]


@dataclass(frozen=True)
class LearningAttempt:
    id: int
    user_id: int
    case_id: int
    dialogue_id: int
    mode: AttemptMode
    audio_object_key: str
    audio_content_type: str
    created_at: str


def _now() -> str:
    return datetime.now(UTC).isoformat()


class LearningAttemptRepository:
    def __init__(self, db_path: str) -> None:
        self.db_path = db_path
        with connect(db_path) as conn:
            init_db(conn)

    def _conn(self) -> sqlite3.Connection:
        return connect(self.db_path)

    def create(
        self,
        *,
        user_id: int,
        case_id: int,
        dialogue_id: int,
        mode: AttemptMode,
        audio_object_key: str,
        audio_content_type: str,
    ) -> LearningAttempt:
        now = _now()
        with self._conn() as conn:
            cur = conn.execute(
                """
                INSERT INTO learning_attempts (
                    user_id, case_id, dialogue_id, mode,
                    audio_object_key, audio_content_type, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    user_id,
                    case_id,
                    dialogue_id,
                    mode,
                    audio_object_key,
                    audio_content_type,
                    now,
                ),
            )
            attempt_id = int(cur.lastrowid)
            conn.commit()
            row = conn.execute(
                "SELECT * FROM learning_attempts WHERE id = ?", (attempt_id,)
            ).fetchone()
            assert row is not None
            return LearningAttempt(
                id=row["id"],
                user_id=row["user_id"],
                case_id=row["case_id"],
                dialogue_id=row["dialogue_id"],
                mode=row["mode"],
                audio_object_key=row["audio_object_key"],
                audio_content_type=row["audio_content_type"],
                created_at=row["created_at"],
            )

    def list_for_user(self, user_id: int) -> list[LearningAttempt]:
        with self._conn() as conn:
            rows = conn.execute(
                """
                SELECT * FROM learning_attempts
                WHERE user_id = ?
                ORDER BY id ASC
                """,
                (user_id,),
            ).fetchall()
            return [
                LearningAttempt(
                    id=row["id"],
                    user_id=row["user_id"],
                    case_id=row["case_id"],
                    dialogue_id=row["dialogue_id"],
                    mode=row["mode"],
                    audio_object_key=row["audio_object_key"],
                    audio_content_type=row["audio_content_type"],
                    created_at=row["created_at"],
                )
                for row in rows
            ]
