from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from jsonschema import Draft7Validator

_SCHEMA_PATH = (
    Path(__file__).resolve().parents[3] / "schemas" / "dialogue.schema.json"
)


@lru_cache
def _validator() -> Draft7Validator:
    schema = json.loads(_SCHEMA_PATH.read_text(encoding="utf-8"))
    Draft7Validator.check_schema(schema)
    return Draft7Validator(schema)


def validate_dialogue_payload(payload: dict[str, Any]) -> None:
    """Raise jsonschema.ValidationError when payload fails draft-07 dialogue schema."""
    _validator().validate(payload)
