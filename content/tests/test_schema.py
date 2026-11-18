from pathlib import Path
import json
import pytest
from studio.schema_validate import validate_studio_dialogue

FIXTURES = Path(__file__).resolve().parents[2] / "schemas" / "fixtures"

def test_valid_studio_dialogue_passes():
    data = json.loads((FIXTURES / "studio-dialogue.valid.json").read_text())
    validate_studio_dialogue(data)

def test_empty_text_fails():
    data = json.loads((FIXTURES / "studio-dialogue.invalid-empty-text.json").read_text())
    with pytest.raises(Exception):
        validate_studio_dialogue(data)