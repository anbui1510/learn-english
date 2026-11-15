from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
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

CREATE TABLE IF NOT EXISTS book_sources (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    slug TEXT NOT NULL UNIQUE,
    title TEXT NOT NULL,
    publisher TEXT,
    default_isbn TEXT,
    notes TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS cases (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    owner_user_id INTEGER NOT NULL,
    title TEXT NOT NULL,
    status TEXT NOT NULL CHECK(status IN ('draft', 'published')),
    isbn TEXT,
    edition TEXT,
    book_source_id INTEGER,
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
    module_slug TEXT,
    unlock_cme_points INTEGER NOT NULL DEFAULT 0,
    unlock_rank TEXT,
    unlock_requires_case_id INTEGER,
    unlock_requires_streak_days INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY(owner_user_id) REFERENCES users(id),
    FOREIGN KEY(published_by_user_id) REFERENCES users(id),
    FOREIGN KEY(unlock_requires_case_id) REFERENCES cases(id),
    FOREIGN KEY(book_source_id) REFERENCES book_sources(id)
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

CREATE TABLE IF NOT EXISTS utterances (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    dialogue_id INTEGER NOT NULL,
    line_index INTEGER NOT NULL,
    speaker TEXT NOT NULL,
    voice TEXT NOT NULL,
    object_key TEXT NOT NULL,
    content_type TEXT NOT NULL,
    duration_ms INTEGER NOT NULL,
    timestamps_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(dialogue_id, line_index),
    FOREIGN KEY(dialogue_id) REFERENCES dialogues(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS learner_profiles (
    user_id INTEGER PRIMARY KEY,
    lessons_per_week INTEGER NOT NULL DEFAULT 3,
    cefr_package TEXT NOT NULL DEFAULT 'B1'
        CHECK(cefr_package IN ('A2', 'B1', 'C1')),
    path_months INTEGER NOT NULL DEFAULT 6,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS lesson_completions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    case_id INTEGER NOT NULL,
    dialogue_id INTEGER NOT NULL,
    completed_at TEXT NOT NULL,
    UNIQUE(user_id, dialogue_id),
    FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY(case_id) REFERENCES cases(id) ON DELETE CASCADE,
    FOREIGN KEY(dialogue_id) REFERENCES dialogues(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS learning_attempts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    case_id INTEGER NOT NULL,
    dialogue_id INTEGER NOT NULL,
    mode TEXT NOT NULL CHECK(mode IN ('shadowing', 'role_play')),
    audio_object_key TEXT NOT NULL,
    audio_content_type TEXT NOT NULL,
    created_at TEXT NOT NULL,
    line_index INTEGER,
    reference_text TEXT,
    score_json TEXT,
    scored_at TEXT,
    response_mode TEXT NOT NULL DEFAULT 'read_along'
        CHECK(response_mode IN ('read_along', 'free_speech')),
    empathy_json TEXT,
    FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY(case_id) REFERENCES cases(id) ON DELETE CASCADE,
    FOREIGN KEY(dialogue_id) REFERENCES dialogues(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS pa_score_usage (
    user_id INTEGER NOT NULL,
    usage_day TEXT NOT NULL,
    score_count INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (user_id, usage_day),
    FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS srs_cards (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    phrase TEXT NOT NULL,
    source_attempt_id INTEGER,
    band TEXT NOT NULL CHECK(band IN ('red', 'yellow')),
    due_at TEXT NOT NULL,
    done_at TEXT,
    created_at TEXT NOT NULL,
    UNIQUE(user_id, phrase),
    FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY(source_attempt_id) REFERENCES learning_attempts(id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS cme_ledger (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    case_id INTEGER NOT NULL,
    dialogue_id INTEGER NOT NULL,
    points INTEGER NOT NULL,
    reason TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY(case_id) REFERENCES cases(id) ON DELETE CASCADE,
    FOREIGN KEY(dialogue_id) REFERENCES dialogues(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS certificates (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    module_slug TEXT NOT NULL,
    title TEXT NOT NULL,
    cme_points INTEGER NOT NULL,
    rank_at_issue TEXT NOT NULL,
    share_slug TEXT NOT NULL UNIQUE,
    disclaimer TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE(user_id, module_slug),
    FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS org_settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS video_exports (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    dialogue_id INTEGER NOT NULL,
    case_id INTEGER NOT NULL,
    status TEXT NOT NULL
        CHECK(status IN ('queued', 'running', 'succeeded', 'failed')),
    object_key TEXT,
    error TEXT,
    width INTEGER NOT NULL DEFAULT 1920,
    height INTEGER NOT NULL DEFAULT 1080,
    engine TEXT NOT NULL DEFAULT 'ffmpeg',
    created_at TEXT NOT NULL,
    finished_at TEXT,
    FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY(dialogue_id) REFERENCES dialogues(id) ON DELETE CASCADE,
    FOREIGN KEY(case_id) REFERENCES cases(id) ON DELETE CASCADE
);
"""

_ATTEMPT_COLUMNS: dict[str, str] = {
    "line_index": "INTEGER",
    "reference_text": "TEXT",
    "score_json": "TEXT",
    "scored_at": "TEXT",
    "response_mode": "TEXT NOT NULL DEFAULT 'read_along'",
    "empathy_json": "TEXT",
}

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
    "module_slug": "TEXT",
    "unlock_cme_points": "INTEGER NOT NULL DEFAULT 0",
    "unlock_rank": "TEXT",
    "unlock_requires_case_id": "INTEGER",
    "unlock_requires_streak_days": "INTEGER NOT NULL DEFAULT 0",
    "book_source_id": "INTEGER",
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


def _seed_book_sources(conn: sqlite3.Connection) -> None:
    from app.books.repository import DEFAULT_SOURCES

    now = datetime.now(UTC).isoformat()
    for item in DEFAULT_SOURCES:
        conn.execute(
            """
            INSERT OR IGNORE INTO book_sources (
                slug, title, publisher, default_isbn, notes, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                item["slug"],
                item["title"],
                item["publisher"],
                item["default_isbn"],
                item["notes"],
                now,
                now,
            ),
        )


def init_db(conn: sqlite3.Connection) -> None:
    conn.executescript(_SCHEMA)
    existing = {
        row[1] for row in conn.execute("PRAGMA table_info(cases)").fetchall()
    }
    for name, col_type in _CASE_COLUMNS.items():
        if name not in existing:
            conn.execute(f"ALTER TABLE cases ADD COLUMN {name} {col_type}")
    attempt_cols = {
        row[1] for row in conn.execute("PRAGMA table_info(learning_attempts)").fetchall()
    }
    for name, col_type in _ATTEMPT_COLUMNS.items():
        if name not in attempt_cols:
            conn.execute(f"ALTER TABLE learning_attempts ADD COLUMN {name} {col_type}")
    _migrate_facts_status_rejected(conn)
    _seed_book_sources(conn)
    _seed_org_tts_defaults(conn)
    conn.commit()


def _seed_org_tts_defaults(conn: sqlite3.Connection) -> None:
    from app.auth.settings import get_auth_settings

    now = datetime.now(UTC).isoformat()
    try:
        default_provider = get_auth_settings().tts_provider_default or "synthetic"
    except Exception:  # noqa: BLE001
        default_provider = "synthetic"
    if default_provider not in {"synthetic", "edge", "azure", "elevenlabs"}:
        default_provider = "synthetic"
    conn.execute(
        """
        INSERT OR IGNORE INTO org_settings (key, value, updated_at)
        VALUES ('tts_provider', ?, ?)
        """,
        (default_provider, now),
    )
    conn.execute(
        """
        INSERT OR IGNORE INTO org_settings (key, value, updated_at)
        VALUES ('tts_premium_enabled', 'false', ?)
        """,
        (now,),
    )
