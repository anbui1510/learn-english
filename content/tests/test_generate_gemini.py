import json

import pytest

from studio.generate import GeminiDialogueClient, generate_dialogues
from studio.ingest import ingest_case


def _ingest_otitis(tmp_path, monkeypatch):
    monkeypatch.setenv("STUDIO_DATA_ROOT", str(tmp_path))
    src = tmp_path / "in.txt"
    src.write_text(
        "Otitis media causes ear pain and fever in children. It is common in winter.",
        encoding="utf-8",
    )
    return ingest_case(title="Otitis demo", case_id="otitis-demo", text_file=src)


class FakeClient:
    def generate_one(self, **kwargs):
        return {
            "context": kwargs["context"],
            "cefr_level": kwargs["cefr"],
            "status": "needs_review",
            "lines": [
                {
                    "speaker": "doctor",
                    "text": "Fever can mean infection.",
                    "source_quote": "fever",
                    "page": 1,
                }
            ],
        }


class TargetedClient:
    def __init__(self, target_context: str, target_cefr: str) -> None:
        self.target = (target_context, target_cefr)

    def generate_one(self, **kwargs):
        key = (kwargs["context"], kwargs["cefr"])
        if key == self.target:
            return {
                "context": kwargs["context"],
                "cefr_level": kwargs["cefr"],
                "status": "needs_review",
                "lines": [],
            }
        return _valid_payload(kwargs["context"], kwargs["cefr"])


def _valid_payload(context: str, cefr: str) -> dict:
    return {
        "context": context,
        "cefr_level": cefr,
        "status": "needs_review",
        "lines": [
            {
                "speaker": "doctor",
                "text": f"Clinical note for {context}/{cefr}.",
                "source_quote": "ear pain",
            }
        ],
    }


def test_generate_uses_client(tmp_path, monkeypatch):
    _ingest_otitis(tmp_path, monkeypatch)
    paths = generate_dialogues("otitis-demo", mock=False, client=FakeClient())
    assert len(paths) == 9
    data = json.loads(paths[0].read_text())
    assert data["lines"][0]["text"] == "Fever can mean infection."


def test_generate_missing_api_key_raises(tmp_path, monkeypatch):
    _ingest_otitis(tmp_path, monkeypatch)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    with pytest.raises(RuntimeError, match="GEMINI_API_KEY"):
        generate_dialogues("otitis-demo", mock=False)


def test_generate_client_retries_then_writes(tmp_path, monkeypatch):
    case_dir = _ingest_otitis(tmp_path, monkeypatch)
    invalid = {
        "context": "patient_family",
        "cefr_level": "A2",
        "status": "needs_review",
        "lines": [],
    }
    class RetryClient:
        def __init__(self):
            self.attempts = 0

        def generate_one(self, **kwargs):
            if kwargs["context"] == "patient_family" and kwargs["cefr"] == "A2":
                self.attempts += 1
                if self.attempts == 1:
                    return invalid
            return _valid_payload(kwargs["context"], kwargs["cefr"])

    client = RetryClient()
    paths = generate_dialogues("otitis-demo", mock=False, client=client)
    assert len(paths) == 9
    stem = "patient_family__A2"
    dialogue_path = case_dir / "dialogues" / f"{stem}.json"
    assert json.loads(dialogue_path.read_text())["lines"][0]["text"].startswith(
        "Clinical note"
    )
    error_path = case_dir / "dialogues" / f"{stem}.generate_error.json"
    assert not error_path.is_file()
    assert client.attempts >= 2


def test_generate_client_failure_writes_error_file(tmp_path, monkeypatch):
    case_dir = _ingest_otitis(tmp_path, monkeypatch)
    invalid = {
        "context": "patient_family",
        "cefr_level": "A2",
        "status": "needs_review",
        "lines": [],
    }
    client = TargetedClient("patient_family", "A2")
    paths = generate_dialogues("otitis-demo", mock=False, client=client)
    stem = "patient_family__A2"
    error_path = case_dir / "dialogues" / f"{stem}.generate_error.json"
    assert error_path.is_file()
    err = json.loads(error_path.read_text())
    assert err["stem"] == stem
    assert err["attempts"] == 2
    dialogue_path = case_dir / "dialogues" / f"{stem}.json"
    assert not dialogue_path.is_file()
    assert len(paths) == 8


def test_generate_client_skips_accepted(tmp_path, monkeypatch):
    case_dir = _ingest_otitis(tmp_path, monkeypatch)
    generate_dialogues("otitis-demo", mock=False, client=FakeClient())
    stem = "patient_family__A2"
    dialogue_path = case_dir / "dialogues" / f"{stem}.json"
    data = json.loads(dialogue_path.read_text())
    data["status"] = "accepted"
    data["lines"][0]["text"] = "KEEP_ACCEPTED"
    dialogue_path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")

    class TrackingClient(FakeClient):
        def __init__(self):
            self.accepted_calls = 0

        def generate_one(self, **kwargs):
            if kwargs["context"] == "patient_family" and kwargs["cefr"] == "A2":
                self.accepted_calls += 1
            return super().generate_one(**kwargs)

    tracker = TrackingClient()
    generate_dialogues("otitis-demo", mock=False, client=tracker)
    kept = json.loads(dialogue_path.read_text())
    assert kept["lines"][0]["text"] == "KEEP_ACCEPTED"
    assert tracker.accepted_calls == 0


def test_gemini_client_rejects_empty_response(monkeypatch):
    class EmptyText:
        text = "   "

    class FakeModels:
        def generate_content(self, **_kwargs):
            return EmptyText()

    class FakeGenaiClient:
        models = FakeModels()

    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    client = GeminiDialogueClient(api_key="test-key", genai_client=FakeGenaiClient())
    with pytest.raises(ValueError, match="empty"):
        client.generate_one(
            source_text="Fever.",
            case_meta={"title": "Otitis"},
            context="patient_family",
            cefr="A2",
        )