from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime

from app.users.db import connect, init_db

DEFAULT_SOURCES: tuple[dict[str, str | None], ...] = (
    {
        "slug": "nelson-pediatrics",
        "title": "Nelson Textbook of Pediatrics",
        "publisher": "Elsevier",
        "default_isbn": "978-0-323-52950-1",
        "notes": "Primary MVP source",
    },
    {
        "slug": "harriet-lane",
        "title": "The Harriet Lane Handbook",
        "publisher": "Elsevier",
        "default_isbn": None,
        "notes": "Quick-reference pediatric handbook",
    },
    {
        "slug": "who-guidelines",
        "title": "WHO pediatric guidelines",
        "publisher": "World Health Organization",
        "default_isbn": None,
        "notes": "Public health / guideline corpus",
    },
)


@dataclass(frozen=True)
class BookSource:
    id: int
    slug: str
    title: str
    publisher: str | None
    default_isbn: str | None
    notes: str | None
    created_at: str
    updated_at: str


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _row(row: sqlite3.Row) -> BookSource:
    return BookSource(
        id=int(row["id"]),
        slug=row["slug"],
        title=row["title"],
        publisher=row["publisher"],
        default_isbn=row["default_isbn"],
        notes=row["notes"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


class BookSourceRepository:
    def __init__(self, db_path: str) -> None:
        self.db_path = db_path
        with connect(db_path) as conn:
            init_db(conn)

    def _conn(self) -> sqlite3.Connection:
        return connect(self.db_path)

    def list_sources(self) -> list[BookSource]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT * FROM book_sources ORDER BY title COLLATE NOCASE"
            ).fetchall()
            return [_row(r) for r in rows]

    def get(self, source_id: int) -> BookSource | None:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM book_sources WHERE id = ?", (source_id,)
            ).fetchone()
            return _row(row) if row else None

    def get_by_slug(self, slug: str) -> BookSource | None:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM book_sources WHERE slug = ?", (slug,)
            ).fetchone()
            return _row(row) if row else None

    def create(
        self,
        *,
        slug: str,
        title: str,
        publisher: str | None = None,
        default_isbn: str | None = None,
        notes: str | None = None,
    ) -> BookSource:
        clean_slug = slug.strip().lower().replace(" ", "-")
        clean_title = title.strip()
        if not clean_slug or not clean_title:
            raise ValueError("slug and title are required")
        now = _now()
        with self._conn() as conn:
            cur = conn.execute(
                """
                INSERT INTO book_sources (
                    slug, title, publisher, default_isbn, notes, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    clean_slug,
                    clean_title,
                    publisher,
                    default_isbn,
                    notes,
                    now,
                    now,
                ),
            )
            conn.commit()
            row = conn.execute(
                "SELECT * FROM book_sources WHERE id = ?", (int(cur.lastrowid),)
            ).fetchone()
            assert row is not None
            return _row(row)

    def update(
        self,
        source_id: int,
        *,
        title: str | None = None,
        publisher: str | None = None,
        default_isbn: str | None = None,
        notes: str | None = None,
        clear_default_isbn: bool = False,
        clear_notes: bool = False,
        clear_publisher: bool = False,
    ) -> BookSource:
        current = self.get(source_id)
        if current is None:
            raise KeyError(source_id)
        new_title = title.strip() if title is not None else current.title
        if not new_title:
            raise ValueError("title is required")
        new_publisher = (
            None
            if clear_publisher
            else (publisher if publisher is not None else current.publisher)
        )
        new_isbn = (
            None
            if clear_default_isbn
            else (default_isbn if default_isbn is not None else current.default_isbn)
        )
        new_notes = (
            None if clear_notes else (notes if notes is not None else current.notes)
        )
        with self._conn() as conn:
            conn.execute(
                """
                UPDATE book_sources
                SET title = ?, publisher = ?, default_isbn = ?, notes = ?, updated_at = ?
                WHERE id = ?
                """,
                (new_title, new_publisher, new_isbn, new_notes, _now(), source_id),
            )
            conn.commit()
        updated = self.get(source_id)
        assert updated is not None
        return updated
