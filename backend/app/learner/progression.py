from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Literal

from app.users.db import connect, init_db

RankId = Literal[
    "medical_student",
    "intern",
    "resident",
    "fellow",
    "attending",
    "chief_of_staff",
]

RANK_LADDER: list[tuple[RankId, str, int]] = [
    ("medical_student", "Medical Student", 0),
    ("intern", "Intern", 1),
    ("resident", "Resident", 3),
    ("fellow", "Fellow", 6),
    ("attending", "Attending", 10),
    ("chief_of_staff", "Chief of Staff", 15),
]

CME_PER_LESSON = 10
CME_ROLEPLAY_BONUS = 5
ROLEPLAY_PA_THRESHOLD = 60.0
MODULE_CERT_THRESHOLD = 20

CERTIFICATE_DISCLAIMER = (
    "This digital certificate is a practice milestone only and does not replace "
    "official CME credit."
)


def _now() -> str:
    return datetime.now(UTC).isoformat()


def rank_for_completions(completed_cases: int) -> tuple[RankId, str]:
    current: tuple[RankId, str] = ("medical_student", "Medical Student")
    for rank_id, label, needed in RANK_LADDER:
        if completed_cases >= needed:
            current = (rank_id, label)
    return current


def rank_index(rank_id: str) -> int:
    for index, (rid, _, _) in enumerate(RANK_LADDER):
        if rid == rank_id:
            return index
    return 0


@dataclass(frozen=True)
class CmeEntry:
    id: int
    user_id: int
    case_id: int
    dialogue_id: int
    points: int
    reason: str
    created_at: str


@dataclass(frozen=True)
class Certificate:
    id: int
    user_id: int
    module_slug: str
    title: str
    cme_points: int
    rank_at_issue: str
    share_slug: str
    disclaimer: str
    created_at: str


@dataclass(frozen=True)
class UnlockDecision:
    unlocked: bool
    reason: str | None = None


def would_create_unlock_cycle(
    *,
    case_id: int,
    requires_case_id: int | None,
    edges: dict[int, int | None],
) -> bool:
    """True if setting case_id → requires_case_id creates a cycle."""
    if requires_case_id is None:
        return False
    if requires_case_id == case_id:
        return True
    seen: set[int] = set()
    cursor: int | None = requires_case_id
    while cursor is not None:
        if cursor == case_id:
            return True
        if cursor in seen:
            return True
        seen.add(cursor)
        cursor = edges.get(cursor)
    return False


class ProgressionRepository:
    def __init__(self, db_path: str) -> None:
        self.db_path = db_path
        with connect(db_path) as conn:
            init_db(conn)

    def _conn(self) -> sqlite3.Connection:
        return connect(self.db_path)

    def completed_case_ids(self, user_id: int) -> set[int]:
        with self._conn() as conn:
            rows = conn.execute(
                """
                SELECT DISTINCT case_id FROM lesson_completions
                WHERE user_id = ?
                """,
                (user_id,),
            ).fetchall()
            return {int(r["case_id"]) for r in rows}

    def cme_total(self, user_id: int) -> int:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT COALESCE(SUM(points), 0) AS total FROM cme_ledger WHERE user_id = ?",
                (user_id,),
            ).fetchone()
            return int(row["total"]) if row else 0

    def cme_for_module(self, user_id: int, module_slug: str) -> int:
        with self._conn() as conn:
            row = conn.execute(
                """
                SELECT COALESCE(SUM(l.points), 0) AS total
                FROM cme_ledger l
                JOIN cases c ON c.id = l.case_id
                WHERE l.user_id = ? AND c.module_slug = ?
                """,
                (user_id, module_slug),
            ).fetchone()
            return int(row["total"]) if row else 0

    def list_ledger(self, user_id: int) -> list[CmeEntry]:
        with self._conn() as conn:
            rows = conn.execute(
                """
                SELECT * FROM cme_ledger
                WHERE user_id = ?
                ORDER BY id ASC
                """,
                (user_id,),
            ).fetchall()
            return [
                CmeEntry(
                    id=r["id"],
                    user_id=r["user_id"],
                    case_id=r["case_id"],
                    dialogue_id=r["dialogue_id"],
                    points=r["points"],
                    reason=r["reason"],
                    created_at=r["created_at"],
                )
                for r in rows
            ]

    def award_lesson_cme(
        self,
        *,
        user_id: int,
        case_id: int,
        dialogue_id: int,
        roleplay_bonus: bool,
    ) -> list[CmeEntry]:
        awarded: list[CmeEntry] = []
        with self._conn() as conn:
            existing = conn.execute(
                """
                SELECT id FROM cme_ledger
                WHERE user_id = ? AND dialogue_id = ? AND reason = 'lesson_complete'
                """,
                (user_id, dialogue_id),
            ).fetchone()
            if existing is None:
                awarded.append(
                    self._insert_locked(
                        conn,
                        user_id=user_id,
                        case_id=case_id,
                        dialogue_id=dialogue_id,
                        points=CME_PER_LESSON,
                        reason="lesson_complete",
                    )
                )
            if roleplay_bonus:
                bonus = conn.execute(
                    """
                    SELECT id FROM cme_ledger
                    WHERE user_id = ? AND dialogue_id = ? AND reason = 'roleplay_threshold'
                    """,
                    (user_id, dialogue_id),
                ).fetchone()
                if bonus is None:
                    awarded.append(
                        self._insert_locked(
                            conn,
                            user_id=user_id,
                            case_id=case_id,
                            dialogue_id=dialogue_id,
                            points=CME_ROLEPLAY_BONUS,
                            reason="roleplay_threshold",
                        )
                    )
            conn.commit()
        return awarded

    def _insert_locked(
        self,
        conn: sqlite3.Connection,
        *,
        user_id: int,
        case_id: int,
        dialogue_id: int,
        points: int,
        reason: str,
    ) -> CmeEntry:
        cur = conn.execute(
            """
            INSERT INTO cme_ledger (
                user_id, case_id, dialogue_id, points, reason, created_at
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (user_id, case_id, dialogue_id, points, reason, _now()),
        )
        row = conn.execute(
            "SELECT * FROM cme_ledger WHERE id = ?", (int(cur.lastrowid),)
        ).fetchone()
        assert row is not None
        return CmeEntry(
            id=row["id"],
            user_id=row["user_id"],
            case_id=row["case_id"],
            dialogue_id=row["dialogue_id"],
            points=row["points"],
            reason=row["reason"],
            created_at=row["created_at"],
        )

    def issue_module_certificate_if_eligible(
        self,
        *,
        user_id: int,
        module_slug: str,
        rank_id: str,
    ) -> Certificate | None:
        if not module_slug:
            return None
        points = self.cme_for_module(user_id, module_slug)
        if points < MODULE_CERT_THRESHOLD:
            return None
        with self._conn() as conn:
            existing = conn.execute(
                """
                SELECT * FROM certificates
                WHERE user_id = ? AND module_slug = ?
                """,
                (user_id, module_slug),
            ).fetchone()
            if existing:
                return self._cert_row(existing)
            share_slug = f"{user_id}-{module_slug}-{int(datetime.now(UTC).timestamp())}"
            title = f"Module complete: {module_slug}"
            cur = conn.execute(
                """
                INSERT INTO certificates (
                    user_id, module_slug, title, cme_points, rank_at_issue,
                    share_slug, disclaimer, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    user_id,
                    module_slug,
                    title,
                    points,
                    rank_id,
                    share_slug,
                    CERTIFICATE_DISCLAIMER,
                    _now(),
                ),
            )
            conn.commit()
            row = conn.execute(
                "SELECT * FROM certificates WHERE id = ?", (int(cur.lastrowid),)
            ).fetchone()
            assert row is not None
            return self._cert_row(row)

    def get_certificate_by_slug(self, share_slug: str) -> Certificate | None:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM certificates WHERE share_slug = ?",
                (share_slug,),
            ).fetchone()
            return self._cert_row(row) if row else None

    def list_certificates(self, user_id: int) -> list[Certificate]:
        with self._conn() as conn:
            rows = conn.execute(
                """
                SELECT * FROM certificates
                WHERE user_id = ?
                ORDER BY id ASC
                """,
                (user_id,),
            ).fetchall()
            return [self._cert_row(r) for r in rows]

    def _cert_row(self, row: sqlite3.Row) -> Certificate:
        return Certificate(
            id=row["id"],
            user_id=row["user_id"],
            module_slug=row["module_slug"],
            title=row["title"],
            cme_points=row["cme_points"],
            rank_at_issue=row["rank_at_issue"],
            share_slug=row["share_slug"],
            disclaimer=row["disclaimer"],
            created_at=row["created_at"],
        )


def evaluate_unlock(
    *,
    case: Any,
    completed_cases: set[int],
    cme_total: int,
    rank_id: str,
    streak_days: int = 0,
) -> UnlockDecision:
    req_case = getattr(case, "unlock_requires_case_id", None)
    req_cme = getattr(case, "unlock_cme_points", None) or 0
    req_rank = getattr(case, "unlock_rank", None)
    req_streak = getattr(case, "unlock_requires_streak_days", None) or 0
    if req_case is not None and req_case not in completed_cases:
        return UnlockDecision(
            False, f"Complete prerequisite case #{req_case} first"
        )
    if req_cme and cme_total < req_cme:
        return UnlockDecision(False, f"Need {req_cme} CME points (have {cme_total})")
    if req_rank and rank_index(rank_id) < rank_index(req_rank):
        label = next(
            (label for rid, label, _ in RANK_LADDER if rid == req_rank),
            req_rank,
        )
        return UnlockDecision(False, f"Reach rank {label} first")
    if req_streak and streak_days < req_streak:
        return UnlockDecision(
            False,
            f"Need a {req_streak}-day learning streak (have {streak_days})",
        )
    return UnlockDecision(True)


def progression_snapshot(
    *,
    user_id: int,
    repo: ProgressionRepository,
    streak_days: int = 0,
) -> dict[str, Any]:
    completed = repo.completed_case_ids(user_id)
    rank_id, rank_label = rank_for_completions(len(completed))
    return {
        "rank_id": rank_id,
        "rank_label": rank_label,
        "cases_completed": len(completed),
        "cme_points": repo.cme_total(user_id),
        "streak_days": streak_days,
        "certificates": [
            {
                "id": c.id,
                "module_slug": c.module_slug,
                "title": c.title,
                "cme_points": c.cme_points,
                "rank_at_issue": c.rank_at_issue,
                "share_slug": c.share_slug,
                "disclaimer": c.disclaimer,
                "created_at": c.created_at,
            }
            for c in repo.list_certificates(user_id)
        ],
        "ranks": [
            {"id": rid, "label": label, "cases_required": need}
            for rid, label, need in RANK_LADDER
        ],
    }
