import json

import pytest

from studio.generate import generate_dialogues
from studio.ingest import ingest_case
from studio.review import accept_dialogue
from studio.synthesize import synthesize_case


def _setup_case(tmp_path, monkeypatch):
    monkeypatch.setenv("STUDIO_DATA_ROOT", str(tmp_path))
    src = tmp_path / "in.txt"
    src.write_text("Otitis media causes ear pain and fever in children.", encoding="utf-8")
    case_dir = ingest_case(title="Otitis demo", case_id="otitis-demo", text_file=src)
    generate_dialogues("otitis-demo", mock=True)
    return case_dir


def test_synthesize_accepted_only(tmp_path, monkeypatch):
    case_dir = _setup_case(tmp_path, monkeypatch)
    stem = "patient_family__A2"

    with pytest.raises(RuntimeError, match="not accepted"):
        synthesize_case("otitis-demo", stem, engine="synthetic")

    accept_dialogue("otitis-demo", stem)
    paths = synthesize_case("otitis-demo", stem, engine="synthetic")
    assert paths

    audio_dir = case_dir / "audio" / stem
    ts_path = audio_dir / "timestamps.json"
    assert ts_path.is_file()
    meta = json.loads(ts_path.read_text(encoding="utf-8"))
    assert meta["engine"] == "synthetic"
    assert meta["lines"]
    assert meta["lines"][0]["words"]
    assert meta["lines"][0]["voice"] in {"en-US-GuyNeural", "en-US-JennyNeural"}

    ext = "wav"
    assert (audio_dir / f"line_001.{ext}").is_file()
    assert (audio_dir / f"full.{ext}").is_file()
    assert any(str(p).endswith("timestamps.json") for p in paths)


def test_synthesize_force_skips_accept_gate(tmp_path, monkeypatch):
    _setup_case(tmp_path, monkeypatch)
    stem = "colleague_sbar__B1"
    paths = synthesize_case("otitis-demo", stem, force=True, engine="synthetic")
    assert paths
    assert any("timestamps.json" in str(p) for p in paths)


def test_synthesize_all_accepted_when_no_stem(tmp_path, monkeypatch):
    case_dir = _setup_case(tmp_path, monkeypatch)
    accept_dialogue("otitis-demo", "patient_family__A2")
    accept_dialogue("otitis-demo", "expert_cme__C1")

    paths = synthesize_case("otitis-demo", engine="synthetic")
    ts_paths = [p for p in paths if p.name == "timestamps.json"]
    assert len(ts_paths) == 2
    assert (case_dir / "audio" / "patient_family__A2" / "timestamps.json").is_file()
    assert (case_dir / "audio" / "expert_cme__C1" / "timestamps.json").is_file()