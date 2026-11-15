from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Literal

from app.facts.schema import validate_fact_payload
from app.users.db import connect, init_db

FactStatus = Literal["needs_review", "verified"]


@dataclass(frozen=True)
class FactRecord:
    id: int
    case_id: int
    source_quote: str
    atomic_fact: str
    category: str
    status: FactStatus
    page: int
    chapter: str | None
    section: str | None
    isbn: str
    edition: str
    created_at: str
    updated_at: str

    def to_schema_payload(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "id": str(self.id),
            "source_quote": self.source_quote,
            "atomic_fact": self.atomic_fact,
            "category": self.category,
            "status": self.status,
            "metadata": {
                "isbn": self.isbn,
                "edition": self.edition,
                "page": self.page,
            },
        }
        if self.chapter:
            payload["metadata"]["chapter"] = self.chapter
        if self.section:
            payload["metadata"]["section"] = self.section
        return payload


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _row_to_fact(row: sqlite3.Row) -> FactRecord:
    return FactRecord(
        id=row["id"],
        case_id=row["case_id"],
        source_quote=row["source_quote"],
        atomic_fact=row["atomic_fact"],
        category=row["category"],
        status=row["status"],
        page=row["page"],
        chapter=row["chapter"],
        section=row["section"],
        isbn=row["isbn"],
        edition=row["edition"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


class FactRepository:
    def __init__(self, db_path: str) -> None:
        self.db_path = db_path
        with connect(db_path) as conn:
            init_db(conn)

    def _conn(self) -> sqlite3.Connection:
        return connect(self.db_path)

    def insert_fact(
        self,
        *,
        case_id: int,
        source_quote: str,
        atomic_fact: str,
        category: str,
        page: int,
        isbn: str,
        edition: str,
        status: FactStatus = "needs_review",
        chapter: str | None = None,
        section: str | None = None,
    ) -> FactRecord:
        payload = {
            "source_quote": source_quote,
            "atomic_fact": atomic_fact,
            "category": category,
            "status": status,
            "metadata": {
                "isbn": isbn,
                "edition": edition,
                "page": page,
            },
        }
        if chapter:
            payload["metadata"]["chapter"] = chapter
        if section:
            payload["metadata"]["section"] = section
        validate_fact_payload(payload)

        now = _now()
        with self._conn() as conn:
            cur = conn.execute(
                """
                INSERT INTO facts (
                    case_id, source_quote, atomic_fact, category, status,
                    page, chapter, section, isbn, edition, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    case_id,
                    source_quote,
                    atomic_fact,
                    category,
                    status,
                    page,
                    chapter,
                    section,
                    isbn,
                    edition,
                    now,
                    now,
                ),
            )
            fact_id = int(cur.lastrowid)
            conn.commit()
            row = conn.execute(
                "SELECT * FROM facts WHERE id = ?", (fact_id,)
            ).fetchone()
            assert row is not None
            return _row_to_fact(row)

    def delete_for_case(self, case_id: int) -> None:
        with self._conn() as conn:
            conn.execute("DELETE FROM facts WHERE case_id = ?", (case_id,))
            conn.commit()

    def list_for_case(
        self,
        case_id: int,
        *,
        status: str | None = None,
        category: str | None = None,
    ) -> list[FactRecord]:
        clauses = ["case_id = ?"]
        params: list[Any] = [case_id]
        if status:
            clauses.append("status = ?")
            params.append(status)
        if category:
            clauses.append("category = ?")
            params.append(category)
        sql = (
            "SELECT * FROM facts WHERE "
            + " AND ".join(clauses)
            + " ORDER BY id ASC"
        )
        with self._conn() as conn:
            rows = conn.execute(sql, params).fetchall()
            return [_row_to_fact(row) for row in rows]
