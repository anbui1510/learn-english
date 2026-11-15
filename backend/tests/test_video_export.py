from __future__ import annotations

from fastapi.testclient import TestClient

from app.auth.settings import AuthSettings
from app.video.export import build_karaoke_mp4
from tests.conftest import seed_admin_editor_learner, set_session_cookie
from tests.test_learner_stack import _published_with_dialogue


def test_build_karaoke_mp4_writes_file(tmp_path) -> None:
    # Minimal silent wav via ffmpeg
    wav = tmp_path / "line.wav"
    out = tmp_path / "out.mp4"
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
            "0.3",
            str(wav),
        ],
        check=True,
        capture_output=True,
    )
    build_karaoke_mp4(
        output_path=out,
        title="Bronchiolitis teaching",
        lines=[
            {
                "speaker": "doctor",
                "text": "Supportive care is first-line.",
                "audio_path": wav,
            }
        ],
    )
    assert out.exists()
    assert out.stat().st_size > 500


def test_export_video_job_api(
    client: TestClient, auth_settings: AuthSettings
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

    set_session_cookie(client, auth_settings, learner)
    created = client.post(f"/learner/dialogues/{dialogue_id}/export-video")
    assert created.status_code == 201, created.text
    job = created.json()
    assert job["status"] in {"queued", "running", "succeeded"}
    job_id = job["id"]

    # Poll until done (sync worker finishes in request for MVP)
    detail = client.get(f"/learner/video-exports/{job_id}")
    assert detail.status_code == 200, detail.text
    body = detail.json()
    assert body["status"] == "succeeded"
    assert body["download_url"]
    assert body["width"] == 1920
    assert body["height"] == 1080
    assert body["engine"] == "ffmpeg"
