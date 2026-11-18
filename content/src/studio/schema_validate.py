from __future__ import annotations

import json
from functools import lru_cache

from jsonschema import Draft7Validator

from studio.paths import repo_root

_SCHEMA_FILE = repo_root() / "schemas" / "studio-dialogue.schema.json"


@lru_cache(maxsize=1)
def _validator() -> Draft7Validator:
    schema = json.loads(_SCHEMA_FILE.read_text(encoding="utf-8"))
    Draft7Validator.check_schema(schema)
    return Draft7Validator(schema)


def validate_studio_dialogue(data: dict) -> None:
    """Validate *data* against the studio dialogue JSON Schema.

    Raises ``jsonschema.ValidationError`` when validation fails.
    """
    _validator().validate(data)