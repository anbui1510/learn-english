from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from app.dialogues.schema import validate_dialogue_payload
from app.users.db import connect, init_db


@dataclass(frozen=True)
class DialogueRecord:
    id: int
    case_id: int
    context: str
    cefr_level: str
    payload: dict[str, Any]
    estimated_seconds: float
    duration_warning: bool
    created_at: str
    updated_at: str


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _row_to_dialogue(row: sqlite3.Row) -> DialogueRecord:
    payload = json.loads(row["payload_json"])
    return DialogueRecord(
        id=row["id"],
        case_id=row["case_id"],
        context=row["context"],
        cefr_level=row["cefr_level"],
        payload=payload,
        estimated_seconds=float(row["estimated_seconds"]),
        duration_warning=bool(row["duration_warning"]),
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


class DialogueRepository:
    def __init__(self, db_path: str) -> None:
        self.db_path = db_path
        with connect(db_path) as conn:
            init_db(conn)

    def _conn(self) -> sqlite3.Connection:
        return connect(self.db_path)

    def insert_dialogue(
        self,
        *,
        case_id: int,
        payload: dict[str, Any],
        estimated_seconds: float,
        duration_warning: bool,
    ) -> DialogueRecord:
        validate_dialogue_payload(payload)
        now = _now()
        with self._conn() as conn:
            cur = conn.execute(
                """
                INSERT INTO dialogues (
                    case_id, context, cefr_level, payload_json,
                    estimated_seconds, duration_warning, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    case_id,
                    payload["context"],
                    payload["cefr_level"],
                    json.dumps(payload, ensure_ascii=False),
                    estimated_seconds,
                    1 if duration_warning else 0,
                    now,
                    now,
                ),
            )
            dialogue_id = int(cur.lastrowid)
            # Stamp id into payload for API consumers
            payload_with_id = {**payload, "id": str(dialogue_id)}
            validate_dialogue_payload(payload_with_id)
            conn.execute(
                """
                UPDATE dialogues
                SET payload_json = ?, updated_at = ?
                WHERE id = ?
                """,
                (
                    json.dumps(payload_with_id, ensure_ascii=False),
                    now,
                    dialogue_id,
                ),
            )
            conn.commit()
            row = conn.execute(
                "SELECT * FROM dialogues WHERE id = ?", (dialogue_id,)
            ).fetchone()
            assert row is not None
            return _row_to_dialogue(row)

    def delete_for_case(self, case_id: int) -> None:
        with self._conn() as conn:
            conn.execute("DELETE FROM dialogues WHERE case_id = ?", (case_id,))
            conn.commit()

    def list_for_case(self, case_id: int) -> list[DialogueRecord]:
        with self._conn() as conn:
            rows = conn.execute(
                """
                SELECT * FROM dialogues
                WHERE case_id = ?
                ORDER BY id ASC
                """,
                (case_id,),
            ).fetchall()
            return [_row_to_dialogue(row) for row in rows]

    def get_by_id(self, dialogue_id: int) -> DialogueRecord | None:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM dialogues WHERE id = ?", (dialogue_id,)
            ).fetchone()
            return _row_to_dialogue(row) if row else None
