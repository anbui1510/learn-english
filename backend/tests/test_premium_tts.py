from __future__ import annotations

from fastapi.testclient import TestClient

from app.auth.settings import AuthSettings
from app.speech.tts import (
    AzureTtsEngine,
    ElevenLabsTtsEngine,
    SyntheticTtsEngine,
    resolve_tts,
)
from tests.conftest import seed_admin_editor_learner, set_session_cookie


def test_resolve_tts_defaults_synthetic() -> None:
    engine = resolve_tts(provider="synthetic", premium_enabled=True)
    assert isinstance(engine, SyntheticTtsEngine)


def test_elevenlabs_uses_injected_client() -> None:
    class FakeHttp:
        def post_tts(self, *, text: str, voice_id: str) -> bytes:
            assert "bronchiolitis" in text.lower() or text
            assert voice_id
            # Minimal RIFF header so callers can detect wav-ish payload
            return b"RIFF....WAVEfmt " + text.encode("utf-8")[:20]

    engine = ElevenLabsTtsEngine(
        api_key="fake",
        voice_id="voice-1",
        client=FakeHttp(),  # type: ignore[arg-type]
    )
    result = engine.synthesize(text="Supportive care first.", speaker="doctor")
    assert result.engine == "elevenlabs"
    assert result.voice == "voice-1"
    assert result.audio.startswith(b"RIFF")
    assert result.words


def test_azure_tts_uses_injected_client() -> None:
    class FakeAzure:
        def synthesize(self, *, text: str, voice: str) -> bytes:
            return b"ID3" + text.encode("utf-8")[:10]

    engine = AzureTtsEngine(
        key="k",
        region="eastasia",
        client=FakeAzure(),  # type: ignore[arg-type]
    )
    result = engine.synthesize(text="Hello team", speaker="nurse")
    assert result.engine == "azure"
    assert "Jenny" in result.voice or result.voice
    assert result.audio.startswith(b"ID3")


def test_premium_disabled_falls_back_even_if_provider_set() -> None:
    engine = resolve_tts(
        provider="elevenlabs",
        premium_enabled=False,
        elevenlabs_api_key="x",
    )
    assert isinstance(engine, SyntheticTtsEngine)


def test_admin_tts_settings_api(
    client: TestClient, auth_settings: AuthSettings
) -> None:
    admin, _, _ = seed_admin_editor_learner(auth_settings)
    set_session_cookie(client, auth_settings, admin)

    current = client.get("/admin/tts-settings")
    assert current.status_code == 200, current.text
    body = current.json()
    assert body["provider"] in {"synthetic", "edge", "azure", "elevenlabs"}
    assert "premium_enabled" in body

    patched = client.patch(
        "/admin/tts-settings",
        json={"provider": "elevenlabs", "premium_enabled": True},
    )
    assert patched.status_code == 200, patched.text
    assert patched.json()["provider"] == "elevenlabs"
    assert patched.json()["premium_enabled"] is True

    again = client.get("/admin/tts-settings")
    assert again.json()["provider"] == "elevenlabs"
    assert again.json()["premium_enabled"] is True
