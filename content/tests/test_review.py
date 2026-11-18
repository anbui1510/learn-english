import json

import pytest

from studio.generate import generate_dialogues
from studio.ingest import ingest_case
from studio.review import (
    accept_dialogue,
    assert_accepted,
    list_reviews,
    reject_dialogue,
)


def _setup_case(tmp_path, monkeypatch):
    monkeypatch.setenv("STUDIO_DATA_ROOT", str(tmp_path))
    src = tmp_path / "in.txt"
    src.write_text("Otitis media causes ear pain and fever in children.", encoding="utf-8")
    case_dir = ingest_case(title="Otitis demo", case_id="otitis-demo", text_file=src)
    generate_dialogues("otitis-demo", mock=True)
    return case_dir


def test_accept_updates_review_json(tmp_path, monkeypatch):
    case_dir = _setup_case(tmp_path, monkeypatch)
    accept_dialogue("otitis-demo", "patient_family__A2")
    d = json.loads((case_dir / "dialogues" / "patient_family__A2.json").read_text())
    assert d["status"] == "accepted"
    review = json.loads((case_dir / "review.json").read_text())
    assert review["patient_family__A2"]["status"] == "accepted"
    assert review["patient_family__A2"]["reviewed_at"]


def test_reject_updates_notes(tmp_path, monkeypatch):
    case_dir = _setup_case(tmp_path, monkeypatch)
    reject_dialogue("otitis-demo", "colleague_sbar__B1", notes="Too informal")
    d = json.loads((case_dir / "dialogues" / "colleague_sbar__B1.json").read_text())
    assert d["status"] == "rejected"
    review = json.loads((case_dir / "review.json").read_text())
    assert review["colleague_sbar__B1"]["status"] == "rejected"
    assert review["colleague_sbar__B1"]["notes"] == "Too informal"


def test_list_reviews_includes_stems(tmp_path, monkeypatch):
    _setup_case(tmp_path, monkeypatch)
    rows = list_reviews("otitis-demo")
    assert len(rows) == 9
    stems = {r["stem"] for r in rows}
    assert "expert_cme__C1" in stems


def test_assert_accepted_blocks_when_not_accepted(tmp_path, monkeypatch):
    _setup_case(tmp_path, monkeypatch)
    with pytest.raises(RuntimeError):
        assert_accepted("otitis-demo", "patient_family__A2")


def test_assert_accepted_passes_after_accept(tmp_path, monkeypatch):
    _setup_case(tmp_path, monkeypatch)
    accept_dialogue("otitis-demo", "patient_family__A2")
    assert_accepted("otitis-demo", "patient_family__A2")


def test_assert_accepted_force_skips_check(tmp_path, monkeypatch):
    _setup_case(tmp_path, monkeypatch)
    assert_accepted("otitis-demo", "patient_family__A2", force=True)