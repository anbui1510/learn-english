from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from jsonschema.exceptions import ValidationError

from app.auth.settings import AuthSettings
from app.dialogues.duration import DURATION_WARN_SECONDS, duration_warning, estimate_seconds
from app.dialogues.generator import TemplateDialogueGenerator
from app.dialogues.repository import DialogueRepository
from app.facts.repository import FactRecord
from tests.conftest import seed_admin_editor_learner, set_session_cookie
from tests.test_fact_extraction import FIXTURE_PDF


def _editor_and_learner(auth_settings: AuthSettings):
    _, editor, learner = seed_admin_editor_learner(auth_settings)
    return editor, learner


def _published_case(client: TestClient, auth_settings: AuthSettings) -> int:
    editor, _ = _editor_and_learner(auth_settings)
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
    published = client.post(f"/editor/cases/{case_id}/publish")
    assert published.status_code == 200, published.text
    return case_id


def test_dialogue_repository_validates(tmp_path) -> None:
    from app.cases.repository import CaseRepository
    from app.users.repository import UserRepository

    db = str(tmp_path / "dlg.sqlite3")
    users = UserRepository(db)
    admin = users.upsert_google_user(
        google_sub="a",
        email="a@example.com",
        name="A",
        bootstrap_admin_emails={"a@example.com"},
    )
    editor = users.upsert_google_user(
        google_sub="e",
        email="e@example.com",
        name="E",
        bootstrap_admin_emails=set(),
    )
    editor = users.set_role(user_id=editor.id, new_role="editor", actor_user_id=admin.id)
    case = CaseRepository(db).create_case(
        owner=editor, title="T", isbn="1", edition="22e"
    )
    repo = DialogueRepository(db)
    saved = repo.insert_dialogue(
        case_id=case.id,
        payload={
            "context": "patient_family",
            "cefr_level": "A2",
            "lines": [
                {
                    "speaker": "doctor",
                    "text": "Your child has wheezing.",
                    "fact_ids": ["1"],
                }
            ],
        },
        estimated_seconds=5.0,
        duration_warning=False,
    )
    assert saved.payload["id"] == str(saved.id)
    assert len(repo.list_for_case(case.id)) == 1

    with pytest.raises(ValidationError):
        repo.insert_dialogue(
            case_id=case.id,
            payload={
                "context": "patient_family",
                "cefr_level": "A2",
                "lines": [
                    {"speaker": "doctor", "text": "x", "fact_ids": []},
                ],
            },
            estimated_seconds=1.0,
            duration_warning=False,
        )


def test_template_generator_cites_verified_facts() -> None:
    facts = [
        FactRecord(
            id=11,
            case_id=1,
            source_quote="quote",
            atomic_fact="Bronchiolitis presents with wheezing in infants.",
            category="Clinical Manifestations",
            status="verified",
            page=1,
            chapter=None,
            section=None,
            isbn="978-1",
            edition="22e",
            created_at="t",
            updated_at="t",
        )
    ]
    payload = TemplateDialogueGenerator().generate(
        facts=facts,
        context="colleague_sbar",
        cefr_level="B1",
        include_vi=True,
    )
    assert payload["context"] == "colleague_sbar"
    assert payload["cefr_level"] == "B1"
    assert all(line["fact_ids"] == ["11"] for line in payload["lines"])
    assert all("text_vi" in line for line in payload["lines"])
    assert "SBAR" in payload["lines"][0]["text"]


def test_duration_helpers() -> None:
    short = estimate_seconds([{"text": "one two three"}])
    assert short < DURATION_WARN_SECONDS
    assert duration_warning(short) is False
    long_line = {"text": "word " * 400}
    long = estimate_seconds([long_line])
    assert duration_warning(long) is True


def test_generate_dialogues_api(
    client: TestClient, auth_settings: AuthSettings
) -> None:
    case_id = _published_case(client, auth_settings)

    created = client.post(
        f"/editor/cases/{case_id}/generate-dialogues",
        json={
            "contexts": ["patient_family", "colleague_sbar", "expert_cme"],
            "cefr_level": "C1",
            "include_vi": True,
        },
    )
    assert created.status_code == 200, created.text
    body = created.json()
    assert len(body) == 3
    contexts = {item["context"] for item in body}
    assert contexts == {"patient_family", "colleague_sbar", "expert_cme"}
    for item in body:
        assert item["cefr_level"] == "C1"
        assert item["estimated_seconds"] >= 0
        assert "duration_warning" in item
        assert len(item["lines"]) >= 1
        for line in item["lines"]:
            assert line["fact_ids"]
            assert line.get("text_vi")

    listed = client.get(f"/editor/cases/{case_id}/dialogues")
    assert listed.status_code == 200
    assert len(listed.json()) == 3

    _, learner = _editor_and_learner(auth_settings)
    set_session_cookie(client, auth_settings, learner)
    assert (
        client.post(
            f"/editor/cases/{case_id}/generate-dialogues",
            json={"contexts": ["patient_family"], "cefr_level": "A2"},
        ).status_code
        == 403
    )
