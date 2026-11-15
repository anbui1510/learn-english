from __future__ import annotations

from fastapi.testclient import TestClient

from app.auth.settings import AuthSettings
from app.speech.tts import resolve_tts_provider_name
from tests.conftest import seed_admin_editor_learner, set_session_cookie
from tests.test_learner_stack import _published_with_dialogue


def test_resolve_tts_provider_name_respects_premium_gate() -> None:
    assert (
        resolve_tts_provider_name(
            provider="azure", premium_enabled=False, use_edge=False
        )
        == "synthetic"
    )
    assert (
        resolve_tts_provider_name(
            provider="elevenlabs", premium_enabled=False, use_edge=True
        )
        == "edge"
    )
    assert (
        resolve_tts_provider_name(
            provider="azure", premium_enabled=True, use_edge=False
        )
        == "azure"
    )


def test_lesson_includes_tts_provider(
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
    lesson = client.get(f"/learner/dialogues/{dialogue_id}/lesson")
    assert lesson.status_code == 200, lesson.text
    body = lesson.json()
    assert body["tts_provider"] in {"synthetic", "edge", "azure", "elevenlabs"}
    assert body["playlist"]
    assert body["playlist"][0]["voice"]
