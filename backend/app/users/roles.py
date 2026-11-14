from __future__ import annotations

from typing import Literal

Role = Literal["admin", "editor", "learner"]
ROLES: tuple[Role, ...] = ("admin", "editor", "learner")


def parse_role(value: str) -> Role:
    if value == "admin":
        return "admin"
    if value == "editor":
        return "editor"
    if value == "learner":
        return "learner"
    raise ValueError(f"Invalid role: {value}")
