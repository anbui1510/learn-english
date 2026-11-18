import json

import pytest

from studio.generate import generate_dialogues
from studio.ingest import ingest_case


def _ingest_otitis(tmp_path, monkeypatch):
    monkeypatch.setenv("STUDIO_DATA_ROOT", str(tmp_path))
    src = tmp_path / "in.txt"
    src.write_text(
        "Otitis media causes ear pain and fever in children. It is common in winter.",
        encoding="utf-8",
    )
    return ingest_case(title="Otitis demo", case_id="otitis-demo", text_file=src)


def test_mock_generate_writes_nine_files(tmp_path, monkeypatch):
    _ingest_otitis(tmp_path, monkeypatch)
    paths = generate_dialogues("otitis-demo", mock=True)
    assert len(paths) == 9
    data = json.loads(paths[0].read_text())
    assert data["status"] == "needs_review"
    assert data["lines"][0]["source_quote"]


def test_mock_generate_validates_schema(tmp_path, monkeypatch):
    _ingest_otitis(tmp_path, monkeypatch)
    paths = generate_dialogues("otitis-demo", mock=True)
    for path in paths:
        data = json.loads(path.read_text())
        assert data["context"] in ("patient_family", "colleague_sbar", "expert_cme")
        assert data["cefr_level"] in ("A2", "B1", "C1")
        assert 4 <= len(data["lines"]) <= 6


def test_generate_skips_accepted_dialogue(tmp_path, monkeypatch):
    case_dir = _ingest_otitis(tmp_path, monkeypatch)
    generate_dialogues("otitis-demo", mock=True)
    stem = "patient_family__A2"
    dialogue_path = case_dir / "dialogues" / f"{stem}.json"
    original = dialogue_path.read_text()
    data = json.loads(original)
    data["status"] = "accepted"
    data["lines"][0]["text"] = "KEEP_THIS_ACCEPTED_LINE"
    dialogue_path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")

    generate_dialogues("otitis-demo", mock=True)
    kept = json.loads(dialogue_path.read_text())
    assert kept["status"] == "accepted"
    assert kept["lines"][0]["text"] == "KEEP_THIS_ACCEPTED_LINE"


def test_generate_non_mock_raises_without_api_key(tmp_path, monkeypatch):
    _ingest_otitis(tmp_path, monkeypatch)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    with pytest.raises(RuntimeError, match="GEMINI_API_KEY"):
        generate_dialogues("otitis-demo", mock=False)


def test_generate_missing_case_raises(tmp_path, monkeypatch):
    monkeypatch.setenv("STUDIO_DATA_ROOT", str(tmp_path))
    import pytest

    with pytest.raises(FileNotFoundError):
        generate_dialogues("no-such-case", mock=True)