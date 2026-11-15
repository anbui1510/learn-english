from __future__ import annotations

import json

import httpx
import pytest
from fastapi.testclient import TestClient

from app.auth.settings import AuthSettings
from app.learner.empathy import (
    GeminiEmpathyScorer,
    HttpxGeminiEmpathyClient,
    SyntheticEmpathyScorer,
    parse_empathy_payload,
)
from tests.conftest import seed_admin_editor_learner, set_session_cookie
from tests.test_learner_stack import _published_with_dialogue


def test_parse_empathy_payload_clamps_and_coaches() -> None:
    result = parse_empathy_payload(
        {
            "warmth": 40,
            "clarity": 42,
            "reassurance": 38,
            "feedback": "Acknowledge concern first.",
        },
        engine="gemini",
    )
    assert result.engine == "gemini"
    assert result.score < 55
    assert result.coaching_tip
    assert result.sample_phrase
    assert "counseling" in result.disclaimer.lower()


def test_parse_empathy_payload_high_clears_coaching() -> None:
    result = parse_empathy_payload(
        {
            "warmth": 90,
            "clarity": 88,
            "reassurance": 92,
            "feedback": "Supportive tone.",
            "coaching_tip": "should be cleared",
            "sample_phrase": "should be cleared",
        },
        engine="gemini",
    )
    assert result.score >= 75
    assert result.coaching_tip is None
    assert result.sample_phrase is None


def test_gemini_engine_uses_injected_client() -> None:
    class FakeClient:
        def generate_empathy_json(self, *, prompt: str) -> dict:
            assert "caregiver" in prompt.lower() or "Learner" in prompt
            return {
                "warmth": 62,
                "clarity": 70,
                "reassurance": 58,
                "feedback": "Warm opener, then details.",
                "coaching_tip": "Slow the first sentence.",
                "sample_phrase": "I hear your concern. Here is the next step.",
            }

    engine = GeminiEmpathyScorer(api_key="fake", client=FakeClient())
    result = engine.score(
        transcript_or_context="Your child needs antibiotics now.",
        audio_len=1200,
    )
    assert result.engine == "gemini"
    assert result.score == pytest.approx(63.3, abs=0.1)
    assert result.coaching_tip
    assert result.sample_phrase


def test_gemini_engine_falls_back_when_client_fails() -> None:
    class BoomClient:
        def generate_empathy_json(self, *, prompt: str) -> dict:
            raise RuntimeError("timeout")

    engine = GeminiEmpathyScorer(api_key="fake", client=BoomClient())
    result = engine.score(transcript_or_context="Hello", audio_len=100)
    assert result.engine == "synthetic"


def test_httpx_gemini_client_parses_generate_content() -> None:
    payload = {
        "warmth": 80,
        "clarity": 82,
        "reassurance": 78,
        "feedback": "Calm and clear.",
    }

    def handler(request: httpx.Request) -> httpx.Response:
        assert "generateContent" in str(request.url)
        assert request.url.params.get("key") == "test-key"
        body = json.loads(request.content.decode())
        assert body["generationConfig"]["responseMimeType"] == "application/json"
        return httpx.Response(
            200,
            json={
                "candidates": [
                    {"content": {"parts": [{"text": json.dumps(payload)}]}}
                ]
            },
        )

    transport = httpx.MockTransport(handler)
    with httpx.Client(transport=transport) as http:
        client = HttpxGeminiEmpathyClient(api_key="test-key", http_client=http)
        parsed = client.generate_empathy_json(prompt="score this")
    assert parsed["warmth"] == 80


def test_free_speech_uses_gemini_when_flagged(
    client: TestClient,
    auth_settings: AuthSettings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.learner import router as learner_router

    class FakeClient:
        def generate_empathy_json(self, *, prompt: str) -> dict:
            return {
                "warmth": 48,
                "clarity": 50,
                "reassurance": 44,
                "feedback": "Lead with empathy.",
                "coaching_tip": "Name the caregiver worry first.",
                "sample_phrase": "I can see this is hard. Let us review the plan.",
            }

    monkeypatch.setattr(
        learner_router,
        "get_empathy_engine",
        lambda: GeminiEmpathyScorer(api_key="fake", client=FakeClient()),
    )

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
        files={"file": ("take.webm", b"x" * 64, "audio/webm")},
    )
    assert attempt.status_code == 201, attempt.text
    empathy = attempt.json()["empathy"]
    assert empathy["engine"] == "gemini"
    assert empathy["coaching_tip"]
    assert empathy["sample_phrase"]
    assert "counseling" in empathy["disclaimer"].lower()


def test_get_default_empathy_flag_off_is_synthetic() -> None:
    from app.learner.empathy import get_default_empathy

    engine = get_default_empathy(use_gemini=False, api_key="x")
    assert isinstance(engine, SyntheticEmpathyScorer)
