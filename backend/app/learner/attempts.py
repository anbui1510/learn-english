from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Literal

from app.users.db import connect, init_db

AttemptMode = Literal["shadowing", "role_play"]
ResponseMode = Literal["read_along", "free_speech"]


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
    line_index: int | None = None
    reference_text: str | None = None
    score_json: dict[str, Any] | None = None
    scored_at: str | None = None
    response_mode: ResponseMode = "read_along"
    empathy_json: dict[str, Any] | None = None


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _parse_json(raw: str | None) -> dict[str, Any] | None:
    if not raw:
        return None
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, dict) else None


def _row_to_attempt(row: sqlite3.Row) -> LearningAttempt:
    keys = row.keys()
    response_mode = (
        row["response_mode"] if "response_mode" in keys and row["response_mode"] else "read_along"
    )
    return LearningAttempt(
        id=row["id"],
        user_id=row["user_id"],
        case_id=row["case_id"],
        dialogue_id=row["dialogue_id"],
        mode=row["mode"],
        audio_object_key=row["audio_object_key"],
        audio_content_type=row["audio_content_type"],
        created_at=row["created_at"],
        line_index=row["line_index"] if "line_index" in keys else None,
        reference_text=row["reference_text"] if "reference_text" in keys else None,
        score_json=_parse_json(row["score_json"] if "score_json" in keys else None),
        scored_at=row["scored_at"] if "scored_at" in keys else None,
        response_mode=response_mode,
        empathy_json=_parse_json(row["empathy_json"] if "empathy_json" in keys else None),
    )


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
        line_index: int | None = None,
        reference_text: str | None = None,
        response_mode: ResponseMode = "read_along",
    ) -> LearningAttempt:
        now = _now()
        with self._conn() as conn:
            cur = conn.execute(
                """
                INSERT INTO learning_attempts (
                    user_id, case_id, dialogue_id, mode,
                    audio_object_key, audio_content_type, created_at,
                    line_index, reference_text, response_mode
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    user_id,
                    case_id,
                    dialogue_id,
                    mode,
                    audio_object_key,
                    audio_content_type,
                    now,
                    line_index,
                    reference_text,
                    response_mode,
                ),
            )
            attempt_id = int(cur.lastrowid)
            conn.commit()
            row = conn.execute(
                "SELECT * FROM learning_attempts WHERE id = ?", (attempt_id,)
            ).fetchone()
            assert row is not None
            return _row_to_attempt(row)

    def get_by_id(self, attempt_id: int) -> LearningAttempt | None:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM learning_attempts WHERE id = ?", (attempt_id,)
            ).fetchone()
            return _row_to_attempt(row) if row else None

    def save_score(
        self,
        *,
        attempt_id: int,
        score: dict[str, Any],
        line_index: int | None = None,
        reference_text: str | None = None,
        empathy: dict[str, Any] | None = None,
    ) -> LearningAttempt:
        now = _now()
        with self._conn() as conn:
            conn.execute(
                """
                UPDATE learning_attempts
                SET score_json = ?,
                    scored_at = ?,
                    line_index = COALESCE(?, line_index),
                    reference_text = COALESCE(?, reference_text),
                    empathy_json = COALESCE(?, empathy_json)
                WHERE id = ?
                """,
                (
                    json.dumps(score),
                    now,
                    line_index,
                    reference_text,
                    json.dumps(empathy) if empathy is not None else None,
                    attempt_id,
                ),
            )
            conn.commit()
            row = conn.execute(
                "SELECT * FROM learning_attempts WHERE id = ?", (attempt_id,)
            ).fetchone()
            assert row is not None
            return _row_to_attempt(row)

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
            return [_row_to_attempt(row) for row in rows]
