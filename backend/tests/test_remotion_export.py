from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from app.auth.settings import AuthSettings
from app.video.export import build_karaoke_mp4, render_karaoke_export
from tests.conftest import seed_admin_editor_learner, set_session_cookie
from tests.test_learner_stack import _published_with_dialogue


def _tiny_wav(path: Path) -> None:
    import subprocess

    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "anullsrc=r=16000:cl=mono",
            "-t",
            "0.2",
            str(path),
        ],
        check=True,
        capture_output=True,
    )


def test_remotion_engine_falls_back_to_ffmpeg(tmp_path: Path) -> None:
    wav = tmp_path / "a.wav"
    out = tmp_path / "out.mp4"
    _tiny_wav(wav)

    class BoomRemotion:
        def render(self, *, props_path: Path, output_path: Path, width: int, height: int) -> None:
            raise RuntimeError("remotion not installed")

    engine_used = render_karaoke_export(
        output_path=out,
        title="Case",
        lines=[{"speaker": "doctor", "text": "Hello", "audio_path": wav}],
        preferred_engine="remotion",
        remotion=BoomRemotion(),  # type: ignore[arg-type]
    )
    assert engine_used == "ffmpeg"
    assert out.exists()


def test_remotion_engine_succeeds_when_renderer_ok(tmp_path: Path) -> None:
    wav = tmp_path / "a.wav"
    out = tmp_path / "out.mp4"
    _tiny_wav(wav)

    class OkRemotion:
        def render(self, *, props_path: Path, output_path: Path, width: int, height: int) -> None:
            assert props_path.exists()
            # Produce a valid mp4 via ffmpeg shortcut to satisfy file checks
            build_karaoke_mp4(
                output_path=output_path,
                title="via-remotion",
                lines=[{"speaker": "doctor", "text": "Hello", "audio_path": wav}],
                width=width,
                height=height,
            )

    engine_used = render_karaoke_export(
        output_path=out,
        title="Case",
        lines=[{"speaker": "doctor", "text": "Hello", "audio_path": wav}],
        preferred_engine="remotion",
        remotion=OkRemotion(),  # type: ignore[arg-type]
    )
    assert engine_used == "remotion"
    assert out.exists()


def test_export_api_accepts_remotion_engine(
    client: TestClient, auth_settings: AuthSettings, monkeypatch
) -> None:
    case_id, dialogue_id = _published_with_dialogue(client, auth_settings)
    _, editor, learner = seed_admin_editor_learner(auth_settings)
    set_session_cookie(client, auth_settings, editor)
    assert (
        client.post(
            f"/editor/cases/{case_id}/dialogues/{dialogue_id}/synthesize"
        ).status_code
        == 200
    )

    # Force remotion path to succeed via injected ffmpeg-backed fake
    class OkRemotion:
        def render(self, *, props_path: Path, output_path: Path, width: int, height: int) -> None:
            output_path.write_bytes(b"\x00" * 600)

    monkeypatch.setattr(
        "app.video.service.get_remotion_renderer",
        lambda: OkRemotion(),
    )

    set_session_cookie(client, auth_settings, learner)
    created = client.post(
        f"/learner/dialogues/{dialogue_id}/export-video",
        json={"engine": "remotion"},
    )
    assert created.status_code == 201, created.text
    body = created.json()
    assert body["status"] == "succeeded"
    assert body["engine"] == "remotion"
