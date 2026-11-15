from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Literal

from app.facts.schema import validate_fact_payload
from app.users.db import connect, init_db

FactStatus = Literal["needs_review", "verified", "rejected"]


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


@dataclass(frozen=True)
class FactStatusAuditRecord:
    id: int
    fact_id: int
    actor_user_id: int | None
    old_status: str | None
    new_status: str
    created_at: str


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


def _row_to_audit(row: sqlite3.Row) -> FactStatusAuditRecord:
    return FactStatusAuditRecord(
        id=row["id"],
        fact_id=row["fact_id"],
        actor_user_id=row["actor_user_id"],
        old_status=row["old_status"],
        new_status=row["new_status"],
        created_at=row["created_at"],
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

    def get_by_id(self, fact_id: int) -> FactRecord | None:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM facts WHERE id = ?", (fact_id,)
            ).fetchone()
            return _row_to_fact(row) if row else None

    def update_fact(
        self,
        *,
        fact_id: int,
        actor_user_id: int | None,
        status: FactStatus | None = None,
        source_quote: str | None = None,
        atomic_fact: str | None = None,
        category: str | None = None,
    ) -> FactRecord:
        with self._conn() as conn:
            existing = conn.execute(
                "SELECT * FROM facts WHERE id = ?", (fact_id,)
            ).fetchone()
            if existing is None:
                raise KeyError(f"fact {fact_id} not found")

            new_status: FactStatus = status if status is not None else existing["status"]
            new_quote = (
                source_quote if source_quote is not None else existing["source_quote"]
            )
            new_atomic = (
                atomic_fact if atomic_fact is not None else existing["atomic_fact"]
            )
            new_category = category if category is not None else existing["category"]

            payload = {
                "id": str(existing["id"]),
                "source_quote": new_quote,
                "atomic_fact": new_atomic,
                "category": new_category,
                "status": new_status,
                "metadata": {
                    "isbn": existing["isbn"],
                    "edition": existing["edition"],
                    "page": existing["page"],
                },
            }
            if existing["chapter"]:
                payload["metadata"]["chapter"] = existing["chapter"]
            if existing["section"]:
                payload["metadata"]["section"] = existing["section"]
            validate_fact_payload(payload)

            now = _now()
            old_status = existing["status"]
            conn.execute(
                """
                UPDATE facts
                SET source_quote = ?, atomic_fact = ?, category = ?,
                    status = ?, updated_at = ?
                WHERE id = ?
                """,
                (new_quote, new_atomic, new_category, new_status, now, fact_id),
            )
            if new_status != old_status:
                conn.execute(
                    """
                    INSERT INTO fact_status_audit (
                        fact_id, actor_user_id, old_status, new_status, created_at
                    ) VALUES (?, ?, ?, ?, ?)
                    """,
                    (fact_id, actor_user_id, old_status, new_status, now),
                )
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

    def count_by_status(self, case_id: int) -> dict[str, int]:
        with self._conn() as conn:
            rows = conn.execute(
                """
                SELECT status, COUNT(*) AS n
                FROM facts
                WHERE case_id = ?
                GROUP BY status
                """,
                (case_id,),
            ).fetchall()
            return {row["status"]: int(row["n"]) for row in rows}

    def list_status_audit(self, fact_id: int) -> list[FactStatusAuditRecord]:
        with self._conn() as conn:
            rows = conn.execute(
                """
                SELECT * FROM fact_status_audit
                WHERE fact_id = ?
                ORDER BY id ASC
                """,
                (fact_id,),
            ).fetchall()
            return [_row_to_audit(row) for row in rows]
