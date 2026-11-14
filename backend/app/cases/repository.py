from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal

from app.cases.ownership import assert_can_own_case
from app.users.db import connect, init_db
from app.users.repository import UserRecord

CaseStatus = Literal["draft", "published"]


@dataclass(frozen=True)
class CaseRecord:
    id: int
    owner_user_id: int
    title: str
    status: CaseStatus
    isbn: str | None
    edition: str | None
    created_at: str
    updated_at: str


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _row_to_case(row: sqlite3.Row) -> CaseRecord:
    return CaseRecord(
        id=row["id"],
        owner_user_id=row["owner_user_id"],
        title=row["title"],
        status=row["status"],
        isbn=row["isbn"],
        edition=row["edition"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


class CaseRepository:
    def __init__(self, db_path: str) -> None:
        self.db_path = db_path
        with connect(db_path) as conn:
            init_db(conn)

    def _conn(self) -> sqlite3.Connection:
        return connect(self.db_path)

    def create_case(
        self,
        *,
        owner: UserRecord,
        title: str,
        isbn: str | None = None,
        edition: str | None = None,
    ) -> CaseRecord:
        assert_can_own_case(owner)
        title_clean = title.strip()
        if not title_clean:
            raise ValueError("Case title is required")
        now = _now()
        with self._conn() as conn:
            cur = conn.execute(
                """
                INSERT INTO cases
                    (owner_user_id, title, status, isbn, edition, created_at, updated_at)
                VALUES (?, ?, 'draft', ?, ?, ?, ?)
                """,
                (owner.id, title_clean, isbn, edition, now, now),
            )
            case_id = int(cur.lastrowid)
            conn.commit()
            row = conn.execute(
                "SELECT * FROM cases WHERE id = ?",
                (case_id,),
            ).fetchone()
            assert row is not None
            return _row_to_case(row)

    def get_by_id(self, case_id: int) -> CaseRecord | None:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM cases WHERE id = ?",
                (case_id,),
            ).fetchone()
            return _row_to_case(row) if row else None

    def list_for_owner(self, owner_user_id: int) -> list[CaseRecord]:
        with self._conn() as conn:
            rows = conn.execute(
                """
                SELECT * FROM cases
                WHERE owner_user_id = ?
                ORDER BY id ASC
                """,
                (owner_user_id,),
            ).fetchall()
            return [_row_to_case(row) for row in rows]

    def reassign_owner(
        self,
        *,
        case_id: int,
        new_owner: UserRecord,
    ) -> CaseRecord:
        """Reassign ownership; rejects learners via assert_can_own_case."""
        assert_can_own_case(new_owner)
        now = _now()
        with self._conn() as conn:
            existing = conn.execute(
                "SELECT * FROM cases WHERE id = ?",
                (case_id,),
            ).fetchone()
            if existing is None:
                raise KeyError(f"case {case_id} not found")
            conn.execute(
                """
                UPDATE cases
                SET owner_user_id = ?, updated_at = ?
                WHERE id = ?
                """,
                (new_owner.id, now, case_id),
            )
            conn.commit()
            row = conn.execute(
                "SELECT * FROM cases WHERE id = ?",
                (case_id,),
            ).fetchone()
            assert row is not None
            return _row_to_case(row)


__all__ = ["CaseRecord", "CaseRepository"]
