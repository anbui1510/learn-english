from __future__ import annotations

from datetime import date, timedelta

from fastapi.testclient import TestClient

from app.auth.settings import AuthSettings
from app.learner.empathy import SyntheticEmpathyScorer
from app.learner.srs import SrsRepository
from tests.conftest import seed_admin_editor_learner, set_session_cookie
from tests.test_learner_stack import _published_with_dialogue


def test_synthetic_empathy_disclaimer() -> None:
    result = SyntheticEmpathyScorer().score(
        transcript_or_context="I understand this is worrying.",
        audio_len=200,
    )
    assert result.score > 0
    assert "clinical counseling" in result.disclaimer.lower()


def test_srs_enqueue_and_due(tmp_path) -> None:
    db = str(tmp_path / "srs.sqlite3")
    from app.users.repository import UserRepository

    users = UserRepository(db)
    admin = users.upsert_google_user(
        google_sub="a",
        email="a@example.com",
        name="A",
        bootstrap_admin_emails={"a@example.com"},
    )
    repo = SrsRepository(db)
    created = repo.enqueue_from_score(
        user_id=admin.id,
        attempt_id=None,
        score={
            "words": [
                {"word": "wheezing", "accuracy": 40, "band": "red"},
                {"word": "ok", "accuracy": 95, "band": "green"},
            ]
        },
    )
    assert len(created) == 1
    tomorrow = (date.today() + timedelta(days=1)).isoformat()
    due = repo.list_due(admin.id, on_or_before=tomorrow)
    assert len(due) == 1
    assert due[0].phrase == "wheezing"
    done = repo.mark_done(card_id=due[0].id, user_id=admin.id)
    assert done is not None
    assert done.repetition == 1
    assert done.done_at is None
    # First success schedules +1 day; still due within T+1 horizon.
    assert done.due_at == tomorrow
    # Not due today after review.
    assert repo.list_due(admin.id, on_or_before=date.today().isoformat()) == []


def test_free_speech_empathy_and_srs_api(
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
            "response_mode": "free_speech",
        },
        files={"file": ("take.webm", b"x" * 8, "audio/webm")},
    )
    assert attempt.status_code == 201, attempt.text
    body = attempt.json()
    assert body["response_mode"] == "free_speech"
    assert body["empathy"]["score"] >= 0
    assert "counseling" in body["empathy"]["disclaimer"].lower()
    assert body["srs_enqueued"] >= 1

    queue = client.get("/learner/srs/queue?horizon_days=1")
    assert queue.status_code == 200
    cards = queue.json()
    assert len(cards) >= 1
    card_id = cards[0]["id"]
    done = client.post(f"/learner/srs/{card_id}/done")
    assert done.status_code == 200
    body = done.json()
    assert body["repetition"] == 1
    assert body["due_at"] == (date.today() + timedelta(days=1)).isoformat()
    # Reviewed card is scheduled ahead; not due "today" (horizon 0).
    today_queue = client.get("/learner/srs/queue?horizon_days=0").json()
    assert all(c["id"] != card_id for c in today_queue)
