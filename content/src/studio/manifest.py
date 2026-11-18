from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from studio.paths import cases_root, data_root

_SCHEMA = """
CREATE TABLE IF NOT EXISTS cases (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    status TEXT NOT NULL,
    path TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS dialogues (
    id TEXT PRIMARY KEY,
    case_id TEXT NOT NULL,
    context TEXT NOT NULL,
    cefr_level TEXT NOT NULL,
    status TEXT NOT NULL,
    path TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (case_id) REFERENCES cases(id)
);
CREATE TABLE IF NOT EXISTS assets (
    id TEXT PRIMARY KEY,
    dialogue_id TEXT NOT NULL,
    kind TEXT NOT NULL CHECK (kind IN ('audio', 'video')),
    path TEXT NOT NULL,
    status TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (dialogue_id) REFERENCES dialogues(id)
);
CREATE INDEX IF NOT EXISTS idx_dialogues_case ON dialogues(case_id);
CREATE INDEX IF NOT EXISTS idx_assets_dialogue ON assets(dialogue_id);
"""


def _utc_now_z() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _mtime_iso(path: Path) -> str:
    if path.is_file():
        ts = path.stat().st_mtime
        return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    return _utc_now_z()


def sqlite_path() -> Path:
    return data_root() / "studio.sqlite"


def _connect() -> sqlite3.Connection:
    data_root().mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(sqlite_path())
    conn.executescript(_SCHEMA)
    conn.row_factory = sqlite3.Row
    return conn


def _parse_stem(stem: str) -> tuple[str, str]:
    if "__" in stem:
        context, cefr = stem.split("__", 1)
        return context, cefr
    return stem, ""


def _upsert(
    conn: sqlite3.Connection,
    table: str,
    *,
    id: str,
    columns: dict[str, object],
) -> None:
    keys = ["id", *columns.keys()]
    placeholders = ", ".join("?" * len(keys))
    col_names = ", ".join(keys)
    updates = ", ".join(f"{k}=excluded.{k}" for k in columns)
    values = [id, *columns.values()]
    conn.execute(
        f"INSERT INTO {table} ({col_names}) VALUES ({placeholders}) "
        f"ON CONFLICT(id) DO UPDATE SET {updates}",
        values,
    )


def _index_case(conn: sqlite3.Connection, case_dir: Path) -> int:
    touched = 0
    case_id = case_dir.name
    case_json = case_dir / "case.json"
    meta: dict[str, object] = {}
    if case_json.is_file():
        meta = json.loads(case_json.read_text(encoding="utf-8"))
    title = str(meta.get("title") or case_id)
    status = str(meta.get("status") or "unknown")
    updated_at = str(meta.get("updated_at") or _mtime_iso(case_json))

    _upsert(
        conn,
        "cases",
        id=case_id,
        columns={
            "title": title,
            "status": status,
            "path": str(case_dir),
            "updated_at": updated_at,
        },
    )
    touched += 1

    dialogues_dir = case_dir / "dialogues"
    if dialogues_dir.is_dir():
        for path in sorted(dialogues_dir.glob("*.json")):
            if path.name.endswith(".generate_error.json"):
                continue
            data = json.loads(path.read_text(encoding="utf-8"))
            stem = path.stem
            context = str(data.get("context") or _parse_stem(stem)[0])
            cefr = str(data.get("cefr_level") or _parse_stem(stem)[1])
            d_status = str(data.get("status") or "draft")
            d_updated = _mtime_iso(path)

            _upsert(
                conn,
                "dialogues",
                id=stem,
                columns={
                    "case_id": case_id,
                    "context": context,
                    "cefr_level": cefr,
                    "status": d_status,
                    "path": str(path),
                    "updated_at": d_updated,
                },
            )
            touched += 1

            audio_ts = case_dir / "audio" / stem / "timestamps.json"
            if audio_ts.is_file():
                _upsert(
                    conn,
                    "assets",
                    id=f"{stem}:audio",
                    columns={
                        "dialogue_id": stem,
                        "kind": "audio",
                        "path": str(audio_ts.parent),
                        "status": "ready",
                        "updated_at": _mtime_iso(audio_ts),
                    },
                )
                touched += 1

            video_mp4 = case_dir / "video" / f"{stem}.mp4"
            render_meta = case_dir / "video" / f"{stem}.render.json"
            if video_mp4.is_file():
                v_status = "ready"
                if render_meta.is_file():
                    meta_render = json.loads(render_meta.read_text(encoding="utf-8"))
                    engine = meta_render.get("engine", "unknown")
                    v_status = f"ready ({engine})"
                _upsert(
                    conn,
                    "assets",
                    id=f"{stem}:video",
                    columns={
                        "dialogue_id": stem,
                        "kind": "video",
                        "path": str(video_mp4),
                        "status": v_status,
                        "updated_at": _mtime_iso(video_mp4),
                    },
                )
                touched += 1

    return touched


def rebuild_index() -> int:
    """Rebuild SQLite manifest from case folders on disk. Returns rows touched."""
    root = cases_root()
    root.mkdir(parents=True, exist_ok=True)
    total = 0
    with _connect() as conn:
        for case_dir in sorted(root.iterdir()):
            if not case_dir.is_dir():
                continue
            if not (case_dir / "case.json").is_file():
                continue
            total += _index_case(conn, case_dir)
        conn.commit()
    return total


def fetch_case_rows(case_id: str) -> tuple[sqlite3.Row | None, list[sqlite3.Row], list[sqlite3.Row]]:
    """Load case, dialogue, and asset rows for a case (re-indexes that case first)."""
    case_dir = cases_root() / case_id
    if not case_dir.is_dir():
        raise FileNotFoundError(f"Case not found: {case_id}")

    with _connect() as conn:
        _index_case(conn, case_dir)
        conn.commit()
        case = conn.execute("SELECT * FROM cases WHERE id = ?", (case_id,)).fetchone()
        dialogues = conn.execute(
            "SELECT * FROM dialogues WHERE case_id = ? ORDER BY context, cefr_level",
            (case_id,),
        ).fetchall()
        stems = [r["id"] for r in dialogues]
        assets: list[sqlite3.Row] = []
        if stems:
            placeholders = ",".join("?" * len(stems))
            assets = conn.execute(
                f"SELECT * FROM assets WHERE dialogue_id IN ({placeholders}) ORDER BY dialogue_id, kind",
                stems,
            ).fetchall()
    return case, dialogues, assets