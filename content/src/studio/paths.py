from __future__ import annotations

import os
from pathlib import Path


def package_root() -> Path:
    return Path(__file__).resolve().parents[2]


def repo_root() -> Path:
    return package_root().parent


def data_root() -> Path:
    override = os.environ.get("STUDIO_DATA_ROOT")
    if override:
        return Path(override)
    return package_root() / "data"


def cases_root() -> Path:
    return data_root() / "cases"