from studio.generate import generate_dialogues
from studio.ingest import ingest_case
from studio.manifest import rebuild_index
from studio.review import accept_dialogue
from studio.status import case_status


def _setup_case(tmp_path, monkeypatch):
    monkeypatch.setenv("STUDIO_DATA_ROOT", str(tmp_path))
    src = tmp_path / "in.txt"
    src.write_text(
        "Otitis media causes ear pain and fever in children.",
        encoding="utf-8",
    )
    ingest_case(title="Otitis demo", case_id="otitis-demo", text_file=src)
    generate_dialogues("otitis-demo", mock=True)
    accept_dialogue("otitis-demo", "patient_family__A2")


def test_index_and_status(tmp_path, monkeypatch):
    _setup_case(tmp_path, monkeypatch)
    n = rebuild_index()
    assert n >= 1
    text = case_status("otitis-demo")
    assert "patient_family__A2" in text
    assert "accepted" in text