import json
import shutil

import pytest

from studio.generate import generate_dialogues
from studio.ingest import ingest_case
from studio.review import accept_dialogue
from studio.render import build_dualtalk_props, render_dialogue
from studio.synthesize import synthesize_case


def _setup_rendered_case(tmp_path, monkeypatch):
    monkeypatch.setenv("STUDIO_DATA_ROOT", str(tmp_path))
    src = tmp_path / "in.txt"
    src.write_text("Otitis media causes ear pain and fever in children.", encoding="utf-8")
    case_dir = ingest_case(
        title="Otitis demo",
        case_id="otitis-demo",
        text_file=src,
        isbn="978-0-000",
        edition="1",
    )
    generate_dialogues("otitis-demo", mock=True)
    stem = "patient_family__A2"
    accept_dialogue("otitis-demo", stem)
    synthesize_case("otitis-demo", stem, engine="synthetic")
    return case_dir, stem


def test_build_dualtalk_props_includes_timeline(tmp_path, monkeypatch):
    case_dir, stem = _setup_rendered_case(tmp_path, monkeypatch)
    props = build_dualtalk_props(case_dir, stem)
    assert props["title"] == "Otitis demo"
    assert props["isbn"] == "978-0-000"
    assert props["edition"] == "1"
    assert props["lines"]
    assert props["durationMs"] > 0
    assert len(props["speakers"]) >= 2
    assert props["fullAudioPath"]


@pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg not installed")
def test_ffmpeg_fallback_creates_mp4(tmp_path, monkeypatch):
    case_dir, stem = _setup_rendered_case(tmp_path, monkeypatch)

    class MissingRemotion:
        def render(
            self,
            *,
            props_path,
            output_path,
            width: int,
            height: int,
        ) -> None:
            raise RuntimeError("remotion not installed")

    monkeypatch.setattr("studio.render._default_remotion_renderer", lambda: MissingRemotion())

    out = render_dialogue("otitis-demo", stem)
    assert out.is_file()
    assert out.stat().st_size > 0
    assert out.name == f"{stem}.mp4"

    meta_path = case_dir / "video" / f"{stem}.render.json"
    assert meta_path.is_file()
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    assert meta["engine"] == "ffmpeg"

    props_path = case_dir / "video" / f"{stem}.props.json"
    assert props_path.is_file()