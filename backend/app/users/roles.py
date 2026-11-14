from __future__ import annotations

from typing import Literal

Role = Literal["admin", "editor", "learner"]
ROLES: tuple[Role, ...] = ("admin", "editor", "learner")


def parse_role(value: str) -> Role:
    if value not in ROLES:
        raise ValueError(f"Invalid role: {value}")
    return value  # type: ignore[return-value]
