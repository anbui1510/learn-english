"""Validate shared clinical-fact and dialogue JSON Schema fixtures."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from jsonschema import Draft7Validator
from jsonschema.exceptions import ValidationError

REPO_ROOT = Path(__file__).resolve().parents[2]
SCHEMAS_DIR = REPO_ROOT / "schemas"
FIXTURES_DIR = SCHEMAS_DIR / "fixtures"


def _load_json(path: Path) -> dict:
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def _validator(schema_name: str) -> Draft7Validator:
    schema = _load_json(SCHEMAS_DIR / schema_name)
    Draft7Validator.check_schema(schema)
    return Draft7Validator(schema)


@pytest.fixture(scope="module")
def fact_validator() -> Draft7Validator:
    return _validator("clinical-fact.schema.json")


@pytest.fixture(scope="module")
def dialogue_validator() -> Draft7Validator:
    return _validator("dialogue.schema.json")


def test_valid_clinical_fact_passes(fact_validator: Draft7Validator) -> None:
    instance = _load_json(FIXTURES_DIR / "clinical-fact.valid.json")
    fact_validator.validate(instance)


def test_invalid_clinical_fact_fails(fact_validator: Draft7Validator) -> None:
    instance = _load_json(FIXTURES_DIR / "clinical-fact.invalid.json")
    with pytest.raises(ValidationError):
        fact_validator.validate(instance)


def test_valid_dialogue_passes(dialogue_validator: Draft7Validator) -> None:
    instance = _load_json(FIXTURES_DIR / "dialogue.valid.json")
    dialogue_validator.validate(instance)
    for line in instance["lines"]:
        assert len(line["fact_ids"]) >= 1


def test_invalid_dialogue_empty_fact_ids_fails(
    dialogue_validator: Draft7Validator,
) -> None:
    instance = _load_json(FIXTURES_DIR / "dialogue.invalid-empty-fact-ids.json")
    with pytest.raises(ValidationError):
        dialogue_validator.validate(instance)
