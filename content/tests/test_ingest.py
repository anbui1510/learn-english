from pathlib import Path
import json
from studio.ingest import ingest_case

def test_ingest_from_text_file(tmp_path, monkeypatch):
    monkeypatch.setenv("STUDIO_DATA_ROOT", str(tmp_path))
    src = tmp_path / "in.txt"
    src.write_text("Otitis media causes ear pain and fever in children.", encoding="utf-8")
    case_dir = ingest_case(title="Otitis demo", case_id="otitis-demo", text_file=src, isbn="000", edition="1")
    assert (case_dir / "case.json").exists()
    assert "ear pain" in (case_dir / "source.txt").read_text()
    meta = json.loads((case_dir / "case.json").read_text())
    assert meta["id"] == "otitis-demo"
    assert meta["status"] == "ready_for_generate"
    assert (case_dir / "dialogues").is_dir()