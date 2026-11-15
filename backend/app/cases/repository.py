from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal

from app.cases.ownership import assert_can_own_case
from app.users.db import connect, init_db
from app.users.repository import UserRecord

CaseStatus = Literal["draft", "published"]
ExtractStatus = Literal["none", "queued", "running", "succeeded", "failed"]


@dataclass(frozen=True)
class CaseRecord:
    id: int
    owner_user_id: int
    title: str
    status: CaseStatus
    isbn: str | None
    edition: str | None
    pdf_object_key: str | None
    pdf_content_type: str | None
    pdf_byte_size: int | None
    extract_status: ExtractStatus
    extract_error: str | None
    extract_started_at: str | None
    extract_finished_at: str | None
    published_at: str | None
    published_by_user_id: int | None
    module_slug: str | None
    unlock_cme_points: int
    unlock_rank: str | None
    unlock_requires_case_id: int | None
    created_at: str
    updated_at: str


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _row_to_case(row: sqlite3.Row) -> CaseRecord:
    keys = row.keys()
    extract_status = (
        row["extract_status"] if "extract_status" in keys and row["extract_status"] else "none"
    )
    return CaseRecord(
        id=row["id"],
        owner_user_id=row["owner_user_id"],
        title=row["title"],
        status=row["status"],
        isbn=row["isbn"],
        edition=row["edition"],
        pdf_object_key=row["pdf_object_key"] if "pdf_object_key" in keys else None,
        pdf_content_type=(
            row["pdf_content_type"] if "pdf_content_type" in keys else None
        ),
        pdf_byte_size=row["pdf_byte_size"] if "pdf_byte_size" in keys else None,
        extract_status=extract_status,
        extract_error=row["extract_error"] if "extract_error" in keys else None,
        extract_started_at=(
            row["extract_started_at"] if "extract_started_at" in keys else None
        ),
        extract_finished_at=(
            row["extract_finished_at"] if "extract_finished_at" in keys else None
        ),
        published_at=row["published_at"] if "published_at" in keys else None,
        published_by_user_id=(
            row["published_by_user_id"] if "published_by_user_id" in keys else None
        ),
        module_slug=row["module_slug"] if "module_slug" in keys else None,
        unlock_cme_points=(
            int(row["unlock_cme_points"])
            if "unlock_cme_points" in keys and row["unlock_cme_points"] is not None
            else 0
        ),
        unlock_rank=row["unlock_rank"] if "unlock_rank" in keys else None,
        unlock_requires_case_id=(
            row["unlock_requires_case_id"]
            if "unlock_requires_case_id" in keys
            else None
        ),
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
        pdf_object_key: str | None = None,
        pdf_content_type: str | None = None,
        pdf_byte_size: int | None = None,
    ) -> CaseRecord:
        assert_can_own_case(owner)
        title_clean = title.strip()
        if not title_clean:
            raise ValueError("Case title is required")
        now = _now()
        with self._conn() as conn:
            cur = conn.execute(
                """
                INSERT INTO cases (
                    owner_user_id, title, status, isbn, edition,
                    pdf_object_key, pdf_content_type, pdf_byte_size,
                    extract_status, created_at, updated_at
                )
                VALUES (?, ?, 'draft', ?, ?, ?, ?, ?, 'none', ?, ?)
                """,
                (
                    owner.id,
                    title_clean,
                    isbn,
                    edition,
                    pdf_object_key,
                    pdf_content_type,
                    pdf_byte_size,
                    now,
                    now,
                ),
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

    def list_published(self) -> list[CaseRecord]:
        with self._conn() as conn:
            rows = conn.execute(
                """
                SELECT * FROM cases
                WHERE status = 'published'
                ORDER BY id ASC
                """
            ).fetchall()
            return [_row_to_case(row) for row in rows]

    def set_extract_status(
        self,
        case_id: int,
        *,
        status: ExtractStatus,
        error: str | None = None,
    ) -> CaseRecord:
        now = _now()
        with self._conn() as conn:
            existing = conn.execute(
                "SELECT * FROM cases WHERE id = ?",
                (case_id,),
            ).fetchone()
            if existing is None:
                raise KeyError(f"case {case_id} not found")

            started_at = existing["extract_started_at"]
            finished_at = existing["extract_finished_at"]
            if status in {"queued", "running"}:
                if status == "queued" or started_at is None:
                    started_at = now
                finished_at = None
            elif status in {"succeeded", "failed"}:
                finished_at = now
                if started_at is None:
                    started_at = now

            conn.execute(
                """
                UPDATE cases
                SET extract_status = ?,
                    extract_error = ?,
                    extract_started_at = ?,
                    extract_finished_at = ?,
                    updated_at = ?
                WHERE id = ?
                """,
                (status, error, started_at, finished_at, now, case_id),
            )
            conn.commit()
            row = conn.execute(
                "SELECT * FROM cases WHERE id = ?",
                (case_id,),
            ).fetchone()
            assert row is not None
            return _row_to_case(row)

    def publish(
        self,
        *,
        case_id: int,
        publisher: UserRecord,
    ) -> CaseRecord:
        now = _now()
        with self._conn() as conn:
            existing = conn.execute(
                "SELECT * FROM cases WHERE id = ?",
                (case_id,),
            ).fetchone()
            if existing is None:
                raise KeyError(f"case {case_id} not found")
            if existing["status"] == "published":
                return _row_to_case(existing)
            conn.execute(
                """
                UPDATE cases
                SET status = 'published',
                    published_at = ?,
                    published_by_user_id = ?,
                    updated_at = ?
                WHERE id = ?
                """,
                (now, publisher.id, now, case_id),
            )
            conn.commit()
            row = conn.execute(
                "SELECT * FROM cases WHERE id = ?",
                (case_id,),
            ).fetchone()
            assert row is not None
            return _row_to_case(row)

    def unlock_edges(self) -> dict[int, int | None]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT id, unlock_requires_case_id FROM cases"
            ).fetchall()
            return {int(r["id"]): r["unlock_requires_case_id"] for r in rows}

    def set_progression(
        self,
        *,
        case_id: int,
        module_slug: str | None = None,
        unlock_cme_points: int | None = None,
        unlock_rank: str | None = None,
        unlock_requires_case_id: int | None = None,
        clear_unlock_requires_case: bool = False,
    ) -> CaseRecord:
        now = _now()
        with self._conn() as conn:
            existing = conn.execute(
                "SELECT * FROM cases WHERE id = ?",
                (case_id,),
            ).fetchone()
            if existing is None:
                raise KeyError(f"case {case_id} not found")
            next_module = (
                module_slug
                if module_slug is not None
                else existing["module_slug"]
            )
            next_cme = (
                unlock_cme_points
                if unlock_cme_points is not None
                else (existing["unlock_cme_points"] or 0)
            )
            next_rank = (
                unlock_rank if unlock_rank is not None else existing["unlock_rank"]
            )
            if clear_unlock_requires_case:
                next_req = None
            elif unlock_requires_case_id is not None:
                next_req = unlock_requires_case_id
            else:
                next_req = existing["unlock_requires_case_id"]
            conn.execute(
                """
                UPDATE cases
                SET module_slug = ?,
                    unlock_cme_points = ?,
                    unlock_rank = ?,
                    unlock_requires_case_id = ?,
                    updated_at = ?
                WHERE id = ?
                """,
                (next_module, next_cme, next_rank, next_req, now, case_id),
            )
            conn.commit()
            row = conn.execute(
                "SELECT * FROM cases WHERE id = ?",
                (case_id,),
            ).fetchone()
            assert row is not None
            return _row_to_case(row)

    def reassign_owner(
        self,
        *,
        case_id: int,
        new_owner: UserRecord,
    ) -> CaseRecord:
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


__all__ = ["CaseRecord", "CaseRepository", "ExtractStatus"]
