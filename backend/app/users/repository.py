from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime

from app.users.db import connect, init_db
from app.users.roles import Role, parse_role


@dataclass(frozen=True)
class UserRecord:
    id: int
    google_sub: str
    email: str
    name: str | None
    role: Role
    created_at: str
    updated_at: str


@dataclass(frozen=True)
class RoleAuditRecord:
    id: int
    user_id: int
    actor_user_id: int | None
    old_role: str | None
    new_role: str
    created_at: str


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _row_to_user(row: sqlite3.Row) -> UserRecord:
    return UserRecord(
        id=row["id"],
        google_sub=row["google_sub"],
        email=row["email"],
        name=row["name"],
        role=parse_role(row["role"]),
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


class UserRepository:
    def __init__(self, db_path: str) -> None:
        self.db_path = db_path
        with connect(db_path) as conn:
            init_db(conn)

    def _conn(self) -> sqlite3.Connection:
        return connect(self.db_path)

    def upsert_google_user(
        self,
        *,
        google_sub: str,
        email: str,
        name: str | None,
        bootstrap_admin_emails: set[str],
    ) -> UserRecord:
        email_norm = email.strip().lower()
        now = _now()
        with self._conn() as conn:
            existing = conn.execute(
                "SELECT * FROM users WHERE google_sub = ? OR email = ?",
                (google_sub, email_norm),
            ).fetchone()
            if existing:
                conn.execute(
                    """
                    UPDATE users
                    SET google_sub = ?, email = ?, name = ?, updated_at = ?
                    WHERE id = ?
                    """,
                    (google_sub, email_norm, name, now, existing["id"]),
                )
                conn.commit()
                row = conn.execute(
                    "SELECT * FROM users WHERE id = ?",
                    (existing["id"],),
                ).fetchone()
                assert row is not None
                return _row_to_user(row)

            role: Role = (
                "admin" if email_norm in bootstrap_admin_emails else "learner"
            )
            cur = conn.execute(
                """
                INSERT INTO users (google_sub, email, name, role, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (google_sub, email_norm, name, role, now, now),
            )
            user_id = int(cur.lastrowid)
            conn.execute(
                """
                INSERT INTO role_audit (user_id, actor_user_id, old_role, new_role, created_at)
                VALUES (?, NULL, NULL, ?, ?)
                """,
                (user_id, role, now),
            )
            conn.commit()
            row = conn.execute(
                "SELECT * FROM users WHERE id = ?",
                (user_id,),
            ).fetchone()
            assert row is not None
            return _row_to_user(row)

    def get_by_google_sub(self, google_sub: str) -> UserRecord | None:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM users WHERE google_sub = ?",
                (google_sub,),
            ).fetchone()
            return _row_to_user(row) if row else None

    def get_by_id(self, user_id: int) -> UserRecord | None:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM users WHERE id = ?",
                (user_id,),
            ).fetchone()
            return _row_to_user(row) if row else None

    def list_users(self) -> list[UserRecord]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT * FROM users ORDER BY id ASC"
            ).fetchall()
            return [_row_to_user(row) for row in rows]

    def set_role(
        self,
        *,
        user_id: int,
        new_role: Role,
        actor_user_id: int,
    ) -> UserRecord:
        now = _now()
        with self._conn() as conn:
            existing = conn.execute(
                "SELECT * FROM users WHERE id = ?",
                (user_id,),
            ).fetchone()
            if existing is None:
                raise KeyError(f"user {user_id} not found")
            old_role = existing["role"]
            if old_role == new_role:
                return _row_to_user(existing)
            conn.execute(
                "UPDATE users SET role = ?, updated_at = ? WHERE id = ?",
                (new_role, now, user_id),
            )
            conn.execute(
                """
                INSERT INTO role_audit
                    (user_id, actor_user_id, old_role, new_role, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (user_id, actor_user_id, old_role, new_role, now),
            )
            conn.commit()
            row = conn.execute(
                "SELECT * FROM users WHERE id = ?",
                (user_id,),
            ).fetchone()
            assert row is not None
            return _row_to_user(row)

    def list_role_audit(self, user_id: int | None = None) -> list[RoleAuditRecord]:
        with self._conn() as conn:
            if user_id is None:
                rows = conn.execute(
                    "SELECT * FROM role_audit ORDER BY id ASC"
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM role_audit WHERE user_id = ? ORDER BY id ASC",
                    (user_id,),
                ).fetchall()
            return [
                RoleAuditRecord(
                    id=row["id"],
                    user_id=row["user_id"],
                    actor_user_id=row["actor_user_id"],
                    old_role=row["old_role"],
                    new_role=row["new_role"],
                    created_at=row["created_at"],
                )
                for row in rows
            ]
