from __future__ import annotations

from fastapi.testclient import TestClient

from app.auth.settings import AuthSettings
from app.learner.shadowing import build_shadowing_cards
from app.speech.tts import SyntheticTtsEngine, voice_for_speaker
from app.users.service import bootstrap_admin_emails, get_user_repository
from tests.conftest import set_session_cookie
from tests.test_fact_extraction import FIXTURE_PDF


def _users(auth_settings: AuthSettings):
    repo = get_user_repository()
    admin = repo.upsert_google_user(
        google_sub="sub-admin",
        email="admin@example.com",
        name="Admin",
        bootstrap_admin_emails=bootstrap_admin_emails(),
    )
    editor = repo.upsert_google_user(
        google_sub="sub-editor",
        email="editor@example.com",
        name="Editor",
        bootstrap_admin_emails=bootstrap_admin_emails(),
    )
    editor = repo.set_role(
        user_id=editor.id, new_role="editor", actor_user_id=admin.id
    )
    learner = repo.upsert_google_user(
        google_sub="sub-learner",
        email="learner@example.com",
        name="Learner",
        bootstrap_admin_emails=bootstrap_admin_emails(),
    )
    return editor, learner


def _published_with_dialogue(
    client: TestClient, auth_settings: AuthSettings
) -> tuple[int, int]:
    editor, _ = _users(auth_settings)
    set_session_cookie(client, auth_settings, editor)
    created = client.post(
        "/editor/cases/upload",
        data={
            "title": "Bronchiolitis",
            "isbn": "978-0-323-52950-1",
            "edition": "22e",
        },
        files={"file": ("chapter.pdf", FIXTURE_PDF, "application/pdf")},
    )
    assert created.status_code == 201, created.text
    case_id = created.json()["id"]
    assert client.post(f"/editor/cases/{case_id}/extract").status_code == 200
    facts = client.get(f"/editor/cases/{case_id}/facts").json()
    for fact in facts:
        assert (
            client.patch(
                f"/editor/cases/{case_id}/facts/{fact['id']}",
                json={"status": "verified"},
            ).status_code
            == 200
        )
    assert client.post(f"/editor/cases/{case_id}/publish").status_code == 200
    dialogues = client.post(
        f"/editor/cases/{case_id}/generate-dialogues",
        json={
            "contexts": ["patient_family", "colleague_sbar"],
            "cefr_level": "B1",
            "include_vi": True,
        },
    )
    assert dialogues.status_code == 200, dialogues.text
    dialogue_id = dialogues.json()[0]["id"]
    return case_id, dialogue_id


def test_tts_and_shadowing_helpers() -> None:
    assert voice_for_speaker("parent") == "en-US-JennyNeural"
    assert voice_for_speaker("doctor") == "en-US-GuyNeural"
    result = SyntheticTtsEngine(ms_per_word=100).synthesize(
        text="hello world", speaker="doctor"
    )
    assert result.content_type == "audio/wav"
    assert len(result.words) == 2
    assert result.duration_ms == 200

    cards = build_shadowing_cards(
        [
            {"speaker": "doctor", "text": "SBAR Situation: x", "fact_ids": ["1"], "is_key_phrase": True},
            {"speaker": "nurse", "text": "ok", "fact_ids": ["1"]},
        ],
        target=10,
    )
    assert len(cards) == 10
    assert any("SBAR" in str(c["text"]) for c in cards)


def test_synthesize_playlist_shadowing_journey_attempts(
    client: TestClient, auth_settings: AuthSettings
) -> None:
    case_id, dialogue_id = _published_with_dialogue(client, auth_settings)
    editor, learner = _users(auth_settings)
    set_session_cookie(client, auth_settings, editor)

    synth = client.post(
        f"/editor/cases/{case_id}/dialogues/{dialogue_id}/synthesize"
    )
    assert synth.status_code == 200, synth.text
    assert len(synth.json()) >= 1
    assert synth.json()[0]["timestamps"]

    set_session_cookie(client, auth_settings, learner)
    library = client.get("/learner/cases")
    assert library.status_code == 200
    assert any(item["id"] == case_id for item in library.json())

    case_dialogues = client.get(f"/learner/cases/{case_id}/dialogues")
    assert case_dialogues.status_code == 200
    assert any(item["id"] == dialogue_id for item in case_dialogues.json())

    lesson = client.get(f"/learner/dialogues/{dialogue_id}/lesson")
    assert lesson.status_code == 200, lesson.text
    body = lesson.json()
    assert body["isbn"] == "978-0-323-52950-1"
    assert body["edition"] == "22e"
    assert len(body["playlist"]) >= 1
    assert body["playlist"][0]["audio_url"]
    assert body["citation_pages"]

    shadow = client.get(f"/learner/dialogues/{dialogue_id}/shadowing")
    assert shadow.status_code == 200
    assert len(shadow.json()["cards"]) == 10

    profile = client.get("/learner/profile")
    assert profile.status_code == 200
    patched = client.patch(
        "/learner/profile",
        json={"lessons_per_week": 4, "cefr_package": "A2"},
    )
    assert patched.status_code == 200
    assert patched.json()["lessons_per_week"] == 4
    assert patched.json()["cefr_package"] == "A2"

    done = client.post(
        "/learner/completions", json={"dialogue_id": dialogue_id}
    )
    assert done.status_code == 200
    assert done.json()["dialogue_id"] == dialogue_id

    attempt = client.post(
        "/learner/attempts/audio",
        data={"dialogue_id": str(dialogue_id), "mode": "shadowing"},
        files={"file": ("take.webm", b"fake-audio", "audio/webm")},
    )
    assert attempt.status_code == 201, attempt.text
    assert attempt.json()["mode"] == "shadowing"
