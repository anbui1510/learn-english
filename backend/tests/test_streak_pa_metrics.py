from __future__ import annotations

from datetime import date, timedelta

from fastapi.testclient import TestClient

from app.auth.settings import AuthSettings
from app.learner.streak import completion_days, current_streak
from tests.conftest import seed_admin_editor_learner, set_session_cookie
from tests.test_learner_stack import _published_with_dialogue


def test_current_streak_counts_consecutive_days() -> None:
    today = date(2026, 11, 15)
    days = {
        today - timedelta(days=0),
        today - timedelta(days=1),
        today - timedelta(days=2),
        today - timedelta(days=5),
    }
    assert current_streak(days, today=today) == 3
    assert current_streak(set(), today=today) == 0
    assert completion_days(["2026-11-15T10:00:00+00:00"]) == {date(2026, 11, 15)}


def test_streak_unlock_and_admin_pa_usage(
    client: TestClient, auth_settings: AuthSettings, monkeypatch
) -> None:
    case_id, dialogue_id = _published_with_dialogue(client, auth_settings)
    admin, editor, learner = seed_admin_editor_learner(auth_settings)
    set_session_cookie(client, auth_settings, editor)
    assert (
        client.post(
            f"/editor/cases/{case_id}/dialogues/{dialogue_id}/synthesize"
        ).status_code
        == 200
    )
    patched = client.patch(
        f"/editor/cases/{case_id}/progression",
        json={
            "module_slug": "peds-resp",
            "unlock_requires_streak_days": 7,
            "clear_unlock_requires_case": True,
        },
    )
    assert patched.status_code == 200, patched.text
    assert patched.json()["unlock_requires_streak_days"] == 7

    set_session_cookie(client, auth_settings, learner)
    denied = client.post("/learner/completions", json={"dialogue_id": dialogue_id})
    assert denied.status_code == 403
    assert "streak" in denied.json()["detail"].lower()

    # Simulate a 7-day streak via completion timestamps
    monkeypatch.setattr(
        "app.learner.router._streak_days",
        lambda _user_id: 7,
    )
    ok = client.post("/learner/completions", json={"dialogue_id": dialogue_id})
    assert ok.status_code == 200, ok.text

    # Generate PA usage then admin report
    attempt = client.post(
        "/learner/attempts/audio",
        data={
            "dialogue_id": str(dialogue_id),
            "mode": "role_play",
            "line_index": "0",
            "score": "true",
        },
        files={"file": ("take.webm", b"z" * 64, "audio/webm")},
    )
    assert attempt.status_code == 201, attempt.text

    set_session_cookie(client, auth_settings, admin)
    usage = client.get("/admin/pa-usage?days=7")
    assert usage.status_code == 200
    assert any(row["user_id"] == learner.id for row in usage.json())

    set_session_cookie(client, auth_settings, learner)
    prog = client.get("/learner/progression")
    assert prog.status_code == 200
    assert prog.json()["streak_days"] == 7
