from __future__ import annotations

from fastapi.testclient import TestClient

from app.auth.settings import AuthSettings
from app.learner.pronunciation import SyntheticPaEngine, band_for_accuracy
from app.learner.rate_limit import PaRateLimiter
from tests.conftest import seed_admin_editor_learner, set_session_cookie
from tests.test_learner_stack import _published_with_dialogue


def test_band_and_synthetic_engine() -> None:
    assert band_for_accuracy(90) == "green"
    assert band_for_accuracy(65) == "yellow"
    assert band_for_accuracy(40) == "red"
    result = SyntheticPaEngine().assess(
        audio=b"x" * 200,
        reference_text="wheezing in infants",
        cefr_level="C1",
        stress_pattern=[1, 3, 1],
    )
    assert result.engine == "synthetic"
    assert len(result.words) == 3
    assert all(w.band in {"green", "yellow", "red"} for w in result.words)
    # Hint only when prosody weak or stressed word not green (gate in _stress_hint).
    if result.prosody < 75 or any(
        w.band != "green"
        for i, w in enumerate(result.words)
        if i < len([1, 3, 1]) and [1, 3, 1][i] == 3
    ):
        assert result.stress_hint
    else:
        assert result.stress_hint is None


def test_pa_rate_limiter(tmp_path) -> None:
    db = str(tmp_path / "pa.sqlite3")
    from app.users.repository import UserRepository

    users = UserRepository(db)
    admin = users.upsert_google_user(
        google_sub="a",
        email="a@example.com",
        name="A",
        bootstrap_admin_emails={"a@example.com"},
    )
    limiter = PaRateLimiter(db, daily_limit=2)
    ok1, used1, limit = limiter.check_and_increment(admin.id)
    ok2, used2, _ = limiter.check_and_increment(admin.id)
    ok3, used3, _ = limiter.check_and_increment(admin.id)
    assert ok1 and used1 == 1 and limit == 2
    assert ok2 and used2 == 2
    assert not ok3 and used3 == 2


def test_upload_scores_attempt(
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
    attempt = client.post(
        "/learner/attempts/audio",
        data={
            "dialogue_id": str(dialogue_id),
            "mode": "role_play",
            "line_index": "0",
            "score": "true",
        },
        files={"file": ("take.webm", b"fake-audio-bytes-long-enough", "audio/webm")},
    )
    assert attempt.status_code == 201, attempt.text
    body = attempt.json()
    assert body["score"]["engine"] == "synthetic"
    assert body["score"]["words"]
    assert body["score"]["words"][0]["band"] in {"green", "yellow", "red"}
    assert body["pa_usage"]["used"] >= 1

    rescored = client.post(
        f"/learner/attempts/{body['id']}/score",
        json={"line_index": 0},
    )
    assert rescored.status_code == 200, rescored.text
    assert rescored.json()["score"]["pronunciation"] >= 0
