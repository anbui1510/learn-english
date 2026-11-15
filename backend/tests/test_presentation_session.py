from __future__ import annotations

from fastapi.testclient import TestClient

from app.auth.settings import AuthSettings
from app.dialogues.duration import (
    PRESENTATION_TARGET_SECONDS,
    estimate_seconds,
    session_duration_warning,
)
from app.dialogues.generator import TemplateDialogueGenerator
from app.facts.repository import FactRecord
from tests.conftest import seed_admin_editor_learner, set_session_cookie
from tests.test_dialogue_generation import _published_case


def _facts(n: int = 3) -> list[FactRecord]:
    rows: list[FactRecord] = []
    for i in range(1, n + 1):
        rows.append(
            FactRecord(
                id=i,
                case_id=1,
                source_quote=f"quote {i}",
                atomic_fact=(
                    f"Supportive care is first-line for bronchiolitis fact number {i} "
                    "including hydration and oxygen when needed."
                ),
                category="management",
                status="verified",
                page=10,
                chapter="Respiratory",
                section="Bronchiolitis",
                isbn="978-0-323-52950-1",
                edition="22e",
                created_at="2026-01-01T00:00:00+00:00",
                updated_at="2026-01-01T00:00:00+00:00",
            )
        )
    return rows


def test_presentation_template_reaches_near_ten_minutes() -> None:
    payload = TemplateDialogueGenerator().generate(
        facts=_facts(4),
        context="expert_cme",
        cefr_level="B1",
        include_vi=False,
        session_kind="presentation",
        target_seconds=PRESENTATION_TARGET_SECONDS,
    )
    assert payload["session_kind"] == "presentation"
    assert payload["target_seconds"] == PRESENTATION_TARGET_SECONDS
    seconds = estimate_seconds(payload["lines"])
    assert seconds >= PRESENTATION_TARGET_SECONDS * 0.85
    assert all(line.get("fact_ids") for line in payload["lines"])


def test_session_duration_warning_bands() -> None:
    assert not session_duration_warning(600, session_kind="presentation")
    assert session_duration_warning(200, session_kind="presentation")
    assert session_duration_warning(200, session_kind="standard")
    assert not session_duration_warning(100, session_kind="standard")


def test_generate_presentation_api_and_learner_progress(
    client: TestClient, auth_settings: AuthSettings
) -> None:
    case_id = _published_case(client, auth_settings)
    editor, learner = seed_admin_editor_learner(auth_settings)[1:]
    set_session_cookie(client, auth_settings, editor)
    generated = client.post(
        f"/editor/cases/{case_id}/generate-dialogues",
        json={
            "contexts": ["expert_cme"],
            "cefr_level": "B1",
            "include_vi": False,
            "session_kind": "presentation",
        },
    )
    assert generated.status_code == 200, generated.text
    body = generated.json()
    assert len(body) == 1
    assert body[0]["estimated_seconds"] >= PRESENTATION_TARGET_SECONDS * 0.85
    dialogue_id = body[0]["id"]
    assert (
        client.post(
            f"/editor/cases/{case_id}/dialogues/{dialogue_id}/synthesize"
        ).status_code
        == 200
    )

    set_session_cookie(client, auth_settings, learner)
    lesson = client.get(f"/learner/dialogues/{dialogue_id}/lesson")
    assert lesson.status_code == 200, lesson.text
    data = lesson.json()
    assert data["session_kind"] == "presentation"
    assert data["target_seconds"] == PRESENTATION_TARGET_SECONDS
    assert data["estimated_seconds"] >= PRESENTATION_TARGET_SECONDS * 0.85
    assert len(data["playlist"]) >= 5
    total_ms = sum(item["duration_ms"] for item in data["playlist"])
    assert total_ms > 0
