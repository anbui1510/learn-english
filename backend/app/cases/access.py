from __future__ import annotations

from app.cases.repository import CaseRecord
from app.users.repository import UserRecord

PDF_MIME = "application/pdf"


def can_access_case(user: UserRecord, case: CaseRecord) -> bool:
    """Owner editor or platform admin may access case PDF bytes / editor APIs."""
    return user.role == "admin" or case.owner_user_id == user.id
