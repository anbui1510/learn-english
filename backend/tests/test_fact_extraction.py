from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from jsonschema.exceptions import ValidationError

from app.auth.settings import AuthSettings
from app.facts.parser import HeuristicPdfParser
from app.facts.repository import FactRepository
from tests.conftest import seed_admin_editor_learner, set_session_cookie

CLINICAL_TEXT = """
Clinical Manifestations
Bronchiolitis presents with wheezing and tachypnea in infants.
Diagnosis
Diagnosis is clinical based on history and physical examination.
Treatment
Supportive care including hydration and oxygen as needed.
""".strip()

# Minimal PDF structure + latin-1 clinical payload for heuristic fallback.
FIXTURE_PDF = (
    b"%PDF-1.4\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF\n"
    + CLINICAL_TEXT.encode("latin-1")
)


def _editor_and_learner(auth_settings: AuthSettings):
    _, editor, learner = seed_admin_editor_learner(auth_settings)
    return editor, learner


def test_fact_repository_validates_and_lists(tmp_path) -> None:
    db = str(tmp_path / "facts.sqlite3")
    # Need a case row for FK — use CaseRepository
    from app.cases.repository import CaseRepository
    from app.users.repository import UserRepository

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
    cases = CaseRepository(db)
    case = cases.create_case(
        owner=editor,
        title="T",
        isbn="978-1",
        edition="22e",
    )
    facts = FactRepository(db)
    saved = facts.insert_fact(
        case_id=case.id,
        source_quote="Wheezing in infants with bronchiolitis.",
        atomic_fact="Bronchiolitis presents with wheezing in infants.",
        category="Clinical Manifestations",
        page=12,
        isbn="978-1",
        edition="22e",
    )
    assert saved.status == "needs_review"
    listed = facts.list_for_case(case.id, status="needs_review")
    assert len(listed) == 1
    assert listed[0].source_quote.startswith("Wheezing")

    with pytest.raises(ValidationError):
        facts.insert_fact(
            case_id=case.id,
            source_quote="",
            atomic_fact="x",
            category="Diagnosis",
            page=1,
            isbn="978-1",
            edition="22e",
        )


def test_heuristic_parser_extracts_headed_segments() -> None:
    segments = HeuristicPdfParser().parse(FIXTURE_PDF)
    assert len(segments) >= 1
    categories = {s.category for s in segments}
    assert "Clinical Manifestations" in categories
    assert all(s.source_quote for s in segments)
    assert all(s.page >= 1 for s in segments)


def test_extract_job_produces_needs_review_facts(
    client: TestClient, auth_settings: AuthSettings
) -> None:
    editor, learner = _editor_and_learner(auth_settings)
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
    assert created.json()["extract_status"] == "none"

    started = client.post(f"/editor/cases/{case_id}/extract")
    assert started.status_code == 200, started.text
    # TestClient runs BackgroundTasks before returning
    case = client.get(f"/editor/cases/{case_id}")
    assert case.status_code == 200
    assert case.json()["extract_status"] == "succeeded"

    facts = client.get(
        f"/editor/cases/{case_id}/facts",
        params={"status": "needs_review"},
    )
    assert facts.status_code == 200
    body = facts.json()
    assert len(body) >= 1
    assert all(f["status"] == "needs_review" for f in body)
    assert all(f["page"] >= 1 for f in body)
    assert all(f["source_quote"] for f in body)
    assert all(f["isbn"] == "978-0-323-52950-1" for f in body)

    filtered = client.get(
        f"/editor/cases/{case_id}/facts",
        params={"category": "Diagnosis"},
    )
    assert filtered.status_code == 200
    assert all(f["category"] == "Diagnosis" for f in filtered.json())

    set_session_cookie(client, auth_settings, learner)
    assert client.post(f"/editor/cases/{case_id}/extract").status_code == 403
    assert client.get(f"/editor/cases/{case_id}/facts").status_code == 403


def test_extract_fails_closed_without_pdf(
    client: TestClient, auth_settings: AuthSettings
) -> None:
    editor, _ = _editor_and_learner(auth_settings)
    set_session_cookie(client, auth_settings, editor)
    created = client.post(
        "/editor/cases",
        json={"title": "No PDF", "isbn": "978-1", "edition": "22e"},
    )
    assert created.status_code == 201
    case_id = created.json()["id"]
    failed = client.post(f"/editor/cases/{case_id}/extract")
    assert failed.status_code == 400
