from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any, Protocol

from jsonschema import ValidationError

from studio.models import CEFR_LEVELS, CONTEXTS, dialogue_stem
from studio.paths import cases_root, repo_root
from studio.prompts import system_instruction, user_prompt
from studio.schema_validate import validate_studio_dialogue

_SPEAKERS: dict[str, tuple[str, str]] = {
    "patient_family": ("doctor", "parent"),
    "colleague_sbar": ("doctor", "colleague"),
    "expert_cme": ("expert", "learner"),
}

_LINE_COUNTS = {"A2": 4, "B1": 5, "C1": 6}

_DEFAULT_GEMINI_MODEL = "gemini-3.5-flash-lite"
_MAX_SOURCE_CHARS = 120_000
_SCHEMA_FILE = repo_root() / "schemas" / "studio-dialogue.schema.json"


class DialogueClient(Protocol):
    def generate_one(
        self,
        *,
        source_text: str,
        case_meta: dict[str, Any],
        context: str,
        cefr: str,
    ) -> dict[str, object]: ...


def _first_sentence(source_text: str) -> str:
    text = source_text.strip()
    if not text:
        return ""
    match = re.split(r"(?<=[.!?])\s+", text, maxsplit=1)
    return match[0].strip()


def _short_quote(sentence: str, max_len: int = 80) -> str:
    quote = sentence.strip()
    if len(quote) <= max_len:
        return quote
    return quote[: max_len - 3].rstrip() + "..."


def _truncate_source(source_text: str) -> str:
    text = source_text.strip()
    if len(text) <= _MAX_SOURCE_CHARS:
        return text
    return text[: _MAX_SOURCE_CHARS - 3].rstrip() + "..."


def dialogue_json_schema() -> dict[str, object]:
    raw = json.loads(_SCHEMA_FILE.read_text(encoding="utf-8"))
    line_def = raw["definitions"]["studioDialogueLine"]
    return {
        "type": "object",
        "additionalProperties": False,
        "required": list(raw["required"]),
        "properties": {
            **raw["properties"],
            "lines": {
                "type": "array",
                "minItems": 1,
                "items": line_def,
            },
        },
    }


class GeminiDialogueClient:
    """Live Gemini structured-json client with injectable SDK client for tests."""

    def __init__(
        self,
        api_key: str,
        *,
        model: str | None = None,
        genai_client: Any | None = None,
    ) -> None:
        if not api_key:
            raise RuntimeError("GEMINI_API_KEY is not configured")
        self.api_key = api_key
        self.model = model or os.environ.get("STUDIO_GEMINI_MODEL", _DEFAULT_GEMINI_MODEL)
        self._genai_client = genai_client

    def _client(self) -> Any:
        if self._genai_client is not None:
            return self._genai_client
        from google import genai

        return genai.Client(api_key=self.api_key)

    def generate_one(
        self,
        *,
        source_text: str,
        case_meta: dict[str, Any],
        context: str,
        cefr: str,
    ) -> dict[str, object]:
        client = self._client()
        truncated = _truncate_source(source_text)
        instruction = system_instruction(context, cefr)
        prompt = user_prompt(
            source_text=truncated,
            case_meta=case_meta,
            context=context,
            cefr=cefr,
        )
        response = client.models.generate_content(
            model=self.model,
            contents=prompt,
            config={
                "system_instruction": instruction,
                "response_mime_type": "application/json",
                "response_json_schema": dialogue_json_schema(),
            },
        )
        raw = (response.text or "").strip()
        if not raw:
            raise ValueError("Gemini returned empty dialogue JSON")
        data = json.loads(raw)
        if not isinstance(data, dict):
            raise ValueError("Gemini dialogue JSON must be an object")
        data.setdefault("status", "needs_review")
        data["context"] = context
        data["cefr_level"] = cefr
        return data


def _mock_dialogue_payload(
    context: str, cefr: str, source_quote: str
) -> dict[str, object]:
    speaker_a, speaker_b = _SPEAKERS[context]
    n_lines = _LINE_COUNTS[cefr]
    lines: list[dict[str, object]] = []
    for i in range(n_lines):
        speaker = speaker_a if i % 2 == 0 else speaker_b
        line: dict[str, object] = {
            "speaker": speaker,
            "text": f"[{context}/{cefr}] Line {i + 1}: {source_quote}",
        }
        if i == 0:
            line["source_quote"] = source_quote
        if i % 2 == 0:
            line["text_vi"] = f"(VI) {source_quote[:40]}"
        lines.append(line)
    return {
        "context": context,
        "cefr_level": cefr,
        "status": "needs_review",
        "lines": lines,
    }


def _case_dir(case_id: str) -> Path:
    case_dir = cases_root() / case_id
    if not (case_dir / "source.txt").is_file():
        raise FileNotFoundError(f"Case not found or missing source: {case_id}")
    return case_dir


def _existing_status(dialogue_path: Path) -> str | None:
    if not dialogue_path.is_file():
        return None
    try:
        data = json.loads(dialogue_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    status = data.get("status")
    return str(status) if isinstance(status, str) else None


def _write_dialogue(path: Path, payload: dict[str, object]) -> None:
    validate_studio_dialogue(payload)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _touch_review(case_dir: Path, stem: str) -> None:
    review_path = case_dir / "review.json"
    review = json.loads(review_path.read_text(encoding="utf-8"))
    review[stem] = {
        "status": "needs_review",
        "notes": "",
        "reviewed_at": "",
    }
    review_path.write_text(json.dumps(review, indent=2) + "\n", encoding="utf-8")


def _write_generate_error(dialogues_dir: Path, stem: str, message: str) -> None:
    error_path = dialogues_dir / f"{stem}.generate_error.json"
    payload = {
        "stem": stem,
        "error": message,
        "attempts": 2,
    }
    error_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _generate_and_validate(
    *,
    dialogues_dir: Path,
    case_dir: Path,
    stem: str,
    out_path: Path,
    client: DialogueClient,
    source_text: str,
    case_meta: dict[str, Any],
    context: str,
    cefr: str,
) -> Path | None:
    error_path = dialogues_dir / f"{stem}.generate_error.json"
    last_error = ""
    for _ in range(2):
        try:
            payload = client.generate_one(
                source_text=source_text,
                case_meta=case_meta,
                context=context,
                cefr=cefr,
            )
            _write_dialogue(out_path, payload)
            if error_path.is_file():
                error_path.unlink()
            _touch_review(case_dir, stem)
            return out_path
        except (ValidationError, ValueError, json.JSONDecodeError, TypeError) as exc:
            last_error = str(exc)
        except Exception as exc:  # Gemini/API errors (404, 503, …)
            last_error = str(exc)

    _write_generate_error(dialogues_dir, stem, last_error)
    return None


def _resolve_client(client: DialogueClient | None) -> DialogueClient:
    if client is not None:
        return client
    api_key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError(
            "GEMINI_API_KEY is not configured; set it or use mock=True / inject client="
        )
    return GeminiDialogueClient(api_key=api_key)


def generate_dialogues(
    case_id: str,
    *,
    mock: bool = False,
    client: DialogueClient | None = None,
) -> list[Path]:
    case_dir = _case_dir(case_id)
    source_text = (case_dir / "source.txt").read_text(encoding="utf-8")
    source_quote = _short_quote(_first_sentence(source_text))
    if not source_quote:
        raise ValueError(f"Case {case_id} has empty source.txt")

    case_meta = json.loads((case_dir / "case.json").read_text(encoding="utf-8"))

    dialogues_dir = case_dir / "dialogues"
    dialogues_dir.mkdir(parents=True, exist_ok=True)

    live_client: DialogueClient | None = None
    if not mock:
        live_client = _resolve_client(client)

    written: list[Path] = []
    for context in CONTEXTS:
        for cefr in CEFR_LEVELS:
            stem = dialogue_stem(context, cefr)
            out_path = dialogues_dir / f"{stem}.json"
            if _existing_status(out_path) == "accepted":
                written.append(out_path)
                continue

            if mock:
                payload = _mock_dialogue_payload(context, cefr, source_quote)
                _write_dialogue(out_path, payload)
                _touch_review(case_dir, stem)
                written.append(out_path)
                continue

            assert live_client is not None
            result = _generate_and_validate(
                dialogues_dir=dialogues_dir,
                case_dir=case_dir,
                stem=stem,
                out_path=out_path,
                client=live_client,
                source_text=source_text,
                case_meta=case_meta,
                context=context,
                cefr=cefr,
            )
            if result is not None:
                written.append(result)
            elif out_path.is_file():
                written.append(out_path)

    return written