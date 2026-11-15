from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from app.users.db import connect, init_db


@dataclass(frozen=True)
class UtteranceRecord:
    id: int
    dialogue_id: int
    line_index: int
    speaker: str
    voice: str
    object_key: str
    content_type: str
    duration_ms: int
    timestamps: list[dict[str, Any]]
    created_at: str
    updated_at: str


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _row_to_utterance(row: sqlite3.Row) -> UtteranceRecord:
    return UtteranceRecord(
        id=row["id"],
        dialogue_id=row["dialogue_id"],
        line_index=row["line_index"],
        speaker=row["speaker"],
        voice=row["voice"],
        object_key=row["object_key"],
        content_type=row["content_type"],
        duration_ms=row["duration_ms"],
        timestamps=json.loads(row["timestamps_json"]),
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


class UtteranceRepository:
    def __init__(self, db_path: str) -> None:
        self.db_path = db_path
        with connect(db_path) as conn:
            init_db(conn)

    def _conn(self) -> sqlite3.Connection:
        return connect(self.db_path)

    def delete_for_dialogue(self, dialogue_id: int) -> None:
        with self._conn() as conn:
            conn.execute(
                "DELETE FROM utterances WHERE dialogue_id = ?", (dialogue_id,)
            )
            conn.commit()

    def upsert_utterance(
        self,
        *,
        dialogue_id: int,
        line_index: int,
        speaker: str,
        voice: str,
        object_key: str,
        content_type: str,
        duration_ms: int,
        timestamps: list[dict[str, Any]],
    ) -> UtteranceRecord:
        now = _now()
        payload = json.dumps(timestamps, ensure_ascii=False)
        with self._conn() as conn:
            conn.execute(
                """
                INSERT INTO utterances (
                    dialogue_id, line_index, speaker, voice, object_key,
                    content_type, duration_ms, timestamps_json, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(dialogue_id, line_index) DO UPDATE SET
                    speaker = excluded.speaker,
                    voice = excluded.voice,
                    object_key = excluded.object_key,
                    content_type = excluded.content_type,
                    duration_ms = excluded.duration_ms,
                    timestamps_json = excluded.timestamps_json,
                    updated_at = excluded.updated_at
                """,
                (
                    dialogue_id,
                    line_index,
                    speaker,
                    voice,
                    object_key,
                    content_type,
                    duration_ms,
                    payload,
                    now,
                    now,
                ),
            )
            conn.commit()
            row = conn.execute(
                """
                SELECT * FROM utterances
                WHERE dialogue_id = ? AND line_index = ?
                """,
                (dialogue_id, line_index),
            ).fetchone()
            assert row is not None
            return _row_to_utterance(row)

    def list_for_dialogue(self, dialogue_id: int) -> list[UtteranceRecord]:
        with self._conn() as conn:
            rows = conn.execute(
                """
                SELECT * FROM utterances
                WHERE dialogue_id = ?
                ORDER BY line_index ASC
                """,
                (dialogue_id,),
            ).fetchall()
            return [_row_to_utterance(row) for row in rows]
