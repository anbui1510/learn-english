from __future__ import annotations

import json
import wave
from io import BytesIO

from app.learner.pronunciation import (
    AzurePaEngine,
    SyntheticPaEngine,
    parse_azure_pa_json,
    to_wav_pcm16,
)


SAMPLE_AZURE_JSON = {
    "NBest": [
        {
            "PronunciationAssessment": {
                "AccuracyScore": 88.0,
                "FluencyScore": 80.0,
                "CompletenessScore": 92.5,
                "PronScore": 86.0,
                "ProsodyScore": 79.0,
            },
            "Words": [
                {
                    "Word": "bronchiolitis",
                    "PronunciationAssessment": {
                        "AccuracyScore": 55.0,
                        "ErrorType": "Mispronunciation",
                    },
                },
                {
                    "Word": "supportive",
                    "PronunciationAssessment": {
                        "AccuracyScore": 91.0,
                        "ErrorType": "None",
                    },
                },
                {
                    "Word": "care",
                    "PronunciationAssessment": {
                        "AccuracyScore": 70.0,
                        "ErrorType": "None",
                    },
                },
            ],
        }
    ]
}


def _silent_wav(ms: int = 200) -> bytes:
    frames = max(1, int(16000 * ms / 1000))
    buf = BytesIO()
    with wave.open(buf, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(16000)
        wav.writeframes(b"\x00\x00" * frames)
    return buf.getvalue()


def test_parse_azure_pa_json_maps_scores_and_bands() -> None:
    result = parse_azure_pa_json(
        json.dumps(SAMPLE_AZURE_JSON),
        cefr_level="C1",
        stress_pattern=[3, 1, 1],
        reference_text="bronchiolitis supportive care",
    )
    assert result.engine == "azure"
    assert result.pronunciation == 86.0
    assert result.completeness == 92.5
    assert result.prosody == 79.0
    assert [w.band for w in result.words] == ["red", "green", "yellow"]
    # Peak stress on red "bronchiolitis" → gated hint fires.
    assert result.stress_hint is not None
    assert "bronchiolitis" in result.stress_hint.lower()


def test_azure_engine_uses_injected_client() -> None:
    class FakeClient:
        def assess_wav(self, *, wav_bytes: bytes, reference_text: str) -> str:
            assert wav_bytes[:4] == b"RIFF"
            assert "supportive" in reference_text
            return json.dumps(SAMPLE_AZURE_JSON)

    engine = AzurePaEngine(
        key="fake",
        region="eastasia",
        client=FakeClient(),  # type: ignore[arg-type]
    )
    result = engine.assess(
        audio=_silent_wav(),
        reference_text="bronchiolitis supportive care",
        cefr_level="B1",
    )
    assert result.engine == "azure"
    assert result.pronunciation == 86.0


def test_azure_engine_falls_back_when_client_fails() -> None:
    class Boom:
        def assess_wav(self, *, wav_bytes: bytes, reference_text: str) -> str:
            raise RuntimeError("network")

    engine = AzurePaEngine(
        key="fake",
        region="eastasia",
        client=Boom(),  # type: ignore[arg-type]
        fallback=SyntheticPaEngine(),
    )
    result = engine.assess(
        audio=_silent_wav(),
        reference_text="hello world",
        cefr_level="A2",
    )
    assert result.engine == "synthetic"


def test_to_wav_pcm16_passthrough_wav() -> None:
    raw = _silent_wav()
    out = to_wav_pcm16(raw)
    assert out[:4] == b"RIFF"
    assert len(out) >= len(raw) - 100
