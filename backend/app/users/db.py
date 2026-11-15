from __future__ import annotations

import sqlite3
from pathlib import Path

_SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    google_sub TEXT NOT NULL UNIQUE,
    email TEXT NOT NULL UNIQUE,
    name TEXT,
    role TEXT NOT NULL CHECK(role IN ('admin', 'editor', 'learner')),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS role_audit (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    actor_user_id INTEGER,
    old_role TEXT,
    new_role TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY(user_id) REFERENCES users(id),
    FOREIGN KEY(actor_user_id) REFERENCES users(id)
);

CREATE TABLE IF NOT EXISTS cases (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    owner_user_id INTEGER NOT NULL,
    title TEXT NOT NULL,
    status TEXT NOT NULL CHECK(status IN ('draft', 'published')),
    isbn TEXT,
    edition TEXT,
    pdf_object_key TEXT,
    pdf_content_type TEXT,
    pdf_byte_size INTEGER,
    extract_status TEXT NOT NULL DEFAULT 'none'
        CHECK(extract_status IN ('none', 'queued', 'running', 'succeeded', 'failed')),
    extract_error TEXT,
    extract_started_at TEXT,
    extract_finished_at TEXT,
    published_at TEXT,
    published_by_user_id INTEGER,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY(owner_user_id) REFERENCES users(id),
    FOREIGN KEY(published_by_user_id) REFERENCES users(id)
);

CREATE TABLE IF NOT EXISTS facts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    case_id INTEGER NOT NULL,
    source_quote TEXT NOT NULL,
    atomic_fact TEXT NOT NULL,
    category TEXT NOT NULL,
    status TEXT NOT NULL CHECK(status IN ('needs_review', 'verified', 'rejected')),
    page INTEGER NOT NULL CHECK(page >= 1),
    chapter TEXT,
    section TEXT,
    isbn TEXT NOT NULL,
    edition TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY(case_id) REFERENCES cases(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS fact_status_audit (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    fact_id INTEGER NOT NULL,
    actor_user_id INTEGER,
    old_status TEXT,
    new_status TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY(fact_id) REFERENCES facts(id) ON DELETE CASCADE,
    FOREIGN KEY(actor_user_id) REFERENCES users(id)
);

CREATE TABLE IF NOT EXISTS dialogues (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    case_id INTEGER NOT NULL,
    context TEXT NOT NULL
        CHECK(context IN ('patient_family', 'colleague_sbar', 'expert_cme')),
    cefr_level TEXT NOT NULL CHECK(cefr_level IN ('A2', 'B1', 'C1')),
    payload_json TEXT NOT NULL,
    estimated_seconds REAL NOT NULL,
    duration_warning INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY(case_id) REFERENCES cases(id) ON DELETE CASCADE
);
"""

_CASE_COLUMNS: dict[str, str] = {
    "pdf_object_key": "TEXT",
    "pdf_content_type": "TEXT",
    "pdf_byte_size": "INTEGER",
    "extract_status": "TEXT NOT NULL DEFAULT 'none'",
    "extract_error": "TEXT",
    "extract_started_at": "TEXT",
    "extract_finished_at": "TEXT",
    "published_at": "TEXT",
    "published_by_user_id": "INTEGER",
}


def connect(db_path: str | Path) -> sqlite3.Connection:
    path = Path(db_path)
    if str(path) != ":memory:":
        path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def _migrate_facts_status_rejected(conn: sqlite3.Connection) -> None:
    """Rebuild facts table when CHECK constraint lacks rejected."""
    row = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name='facts'"
    ).fetchone()
    if row is None or not row[0]:
        return
    ddl = row[0]
    if "rejected" in ddl:
        return
    conn.executescript(
        """
        CREATE TABLE facts_migrated (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            case_id INTEGER NOT NULL,
            source_quote TEXT NOT NULL,
            atomic_fact TEXT NOT NULL,
            category TEXT NOT NULL,
            status TEXT NOT NULL
                CHECK(status IN ('needs_review', 'verified', 'rejected')),
            page INTEGER NOT NULL CHECK(page >= 1),
            chapter TEXT,
            section TEXT,
            isbn TEXT NOT NULL,
            edition TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY(case_id) REFERENCES cases(id) ON DELETE CASCADE
        );
        INSERT INTO facts_migrated (
            id, case_id, source_quote, atomic_fact, category, status,
            page, chapter, section, isbn, edition, created_at, updated_at
        )
        SELECT
            id, case_id, source_quote, atomic_fact, category, status,
            page, chapter, section, isbn, edition, created_at, updated_at
        FROM facts;
        DROP TABLE facts;
        ALTER TABLE facts_migrated RENAME TO facts;
        """
    )


def init_db(conn: sqlite3.Connection) -> None:
    conn.executescript(_SCHEMA)
    existing = {
        row[1] for row in conn.execute("PRAGMA table_info(cases)").fetchall()
    }
    for name, col_type in _CASE_COLUMNS.items():
        if name not in existing:
            conn.execute(f"ALTER TABLE cases ADD COLUMN {name} {col_type}")
    _migrate_facts_status_rejected(conn)
    conn.commit()
