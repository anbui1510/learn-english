from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal

from app.users.db import connect, init_db

ExportStatus = Literal["queued", "running", "succeeded", "failed"]


@dataclass(frozen=True)
class VideoExportJob:
    id: int
    user_id: int
    dialogue_id: int
    case_id: int
    status: ExportStatus
    object_key: str | None
    error: str | None
    width: int
    height: int
    engine: str
    created_at: str
    finished_at: str | None


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _row(row: sqlite3.Row) -> VideoExportJob:
    return VideoExportJob(
        id=int(row["id"]),
        user_id=int(row["user_id"]),
        dialogue_id=int(row["dialogue_id"]),
        case_id=int(row["case_id"]),
        status=row["status"],  # type: ignore[arg-type]
        object_key=row["object_key"],
        error=row["error"],
        width=int(row["width"]),
        height=int(row["height"]),
        engine=row["engine"],
        created_at=row["created_at"],
        finished_at=row["finished_at"],
    )


class VideoExportRepository:
    def __init__(self, db_path: str) -> None:
        self.db_path = db_path
        with connect(db_path) as conn:
            init_db(conn)

    def _conn(self) -> sqlite3.Connection:
        return connect(self.db_path)

    def create(
        self,
        *,
        user_id: int,
        dialogue_id: int,
        case_id: int,
        width: int = 1920,
        height: int = 1080,
        engine: str = "ffmpeg",
    ) -> VideoExportJob:
        now = _now()
        with self._conn() as conn:
            cur = conn.execute(
                """
                INSERT INTO video_exports (
                    user_id, dialogue_id, case_id, status, object_key, error,
                    width, height, engine, created_at, finished_at
                ) VALUES (?, ?, ?, 'queued', NULL, NULL, ?, ?, ?, ?, NULL)
                """,
                (user_id, dialogue_id, case_id, width, height, engine, now),
            )
            conn.commit()
            row = conn.execute(
                "SELECT * FROM video_exports WHERE id = ?", (int(cur.lastrowid),)
            ).fetchone()
            assert row is not None
            return _row(row)

    def get(self, job_id: int) -> VideoExportJob | None:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM video_exports WHERE id = ?", (job_id,)
            ).fetchone()
            return _row(row) if row else None

    def mark_running(self, job_id: int) -> VideoExportJob:
        with self._conn() as conn:
            conn.execute(
                "UPDATE video_exports SET status = 'running' WHERE id = ?",
                (job_id,),
            )
            conn.commit()
        job = self.get(job_id)
        assert job is not None
        return job

    def mark_succeeded(self, job_id: int, *, object_key: str) -> VideoExportJob:
        with self._conn() as conn:
            conn.execute(
                """
                UPDATE video_exports
                SET status = 'succeeded', object_key = ?, error = NULL, finished_at = ?
                WHERE id = ?
                """,
                (object_key, _now(), job_id),
            )
            conn.commit()
        job = self.get(job_id)
        assert job is not None
        return job

    def mark_failed(self, job_id: int, *, error: str) -> VideoExportJob:
        with self._conn() as conn:
            conn.execute(
                """
                UPDATE video_exports
                SET status = 'failed', error = ?, finished_at = ?
                WHERE id = ?
                """,
                (error[:500], _now(), job_id),
            )
            conn.commit()
        job = self.get(job_id)
        assert job is not None
        return job
