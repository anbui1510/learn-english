from __future__ import annotations

from app.users.repository import UserRecord
from app.users.roles import Role


class CaseOwnershipError(ValueError):
    """Raised when a user cannot own a Case."""


ALLOWED_OWNER_ROLES: frozenset[Role] = frozenset({"editor", "admin"})


def assert_can_own_case(user: UserRecord) -> None:
    """Cases must be owned by an editor (or admin). Learners are rejected."""
    if user.role not in ALLOWED_OWNER_ROLES:
        raise CaseOwnershipError(
            f"Case owner must be editor or admin; got role={user.role!r} "
            f"for user_id={user.id}"
        )
