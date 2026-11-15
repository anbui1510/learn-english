from __future__ import annotations

from fastapi.testclient import TestClient

from app.auth.settings import AuthSettings
from app.facts.repository import FactRepository
from app.users.service import bootstrap_admin_emails, get_user_repository
from tests.conftest import set_session_cookie
from tests.test_fact_extraction import FIXTURE_PDF


def _editor_and_learner(auth_settings: AuthSettings):
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


def _upload_and_extract(
    client: TestClient, auth_settings: AuthSettings
) -> tuple[int, list[dict]]:
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
    assert len(facts) >= 1
    return case_id, facts


def test_patch_verify_reject_and_audit(
    client: TestClient, auth_settings: AuthSettings, tmp_db_path: str
) -> None:
    case_id, facts = _upload_and_extract(client, auth_settings)
    fact_id = facts[0]["id"]

    verified = client.patch(
        f"/editor/cases/{case_id}/facts/{fact_id}",
        json={"status": "verified"},
    )
    assert verified.status_code == 200, verified.text
    assert verified.json()["status"] == "verified"

    rejected = client.patch(
        f"/editor/cases/{case_id}/facts/{fact_id}",
        json={"status": "rejected"},
    )
    assert rejected.status_code == 200
    assert rejected.json()["status"] == "rejected"

    bad = client.patch(
        f"/editor/cases/{case_id}/facts/{fact_id}",
        json={"source_quote": ""},
    )
    assert bad.status_code in {400, 422}

    repo = FactRepository(tmp_db_path)
    audit = repo.list_status_audit(fact_id)
    assert len(audit) >= 2
    assert audit[-1].new_status == "rejected"

    _, learner = _editor_and_learner(auth_settings)
    set_session_cookie(client, auth_settings, learner)
    assert (
        client.patch(
            f"/editor/cases/{case_id}/facts/{fact_id}",
            json={"status": "verified"},
        ).status_code
        == 403
    )


def test_publish_gate_and_generate_dialogues(
    client: TestClient, auth_settings: AuthSettings
) -> None:
    case_id, facts = _upload_and_extract(client, auth_settings)

    blocked = client.post(f"/editor/cases/{case_id}/publish")
    assert blocked.status_code == 409

    gen_draft = client.post(f"/editor/cases/{case_id}/generate-dialogues")
    assert gen_draft.status_code == 409

    # Verify all facts; reject none — publish needs ≥1 verified and 0 needs_review
    for fact in facts:
        resp = client.patch(
            f"/editor/cases/{case_id}/facts/{fact['id']}",
            json={"status": "verified"},
        )
        assert resp.status_code == 200, resp.text

    published = client.post(f"/editor/cases/{case_id}/publish")
    assert published.status_code == 200, published.text
    body = published.json()
    assert body["status"] == "published"
    assert body["published_at"]
    assert body["published_by_user_id"]

    gen_published = client.post(f"/editor/cases/{case_id}/generate-dialogues")
    assert gen_published.status_code == 501

    _, learner = _editor_and_learner(auth_settings)
    set_session_cookie(client, auth_settings, learner)
    assert client.post(f"/editor/cases/{case_id}/publish").status_code == 403
    assert (
        client.post(f"/editor/cases/{case_id}/generate-dialogues").status_code
        == 403
    )


def test_publish_allows_rejected_when_verified_present(
    client: TestClient, auth_settings: AuthSettings
) -> None:
    case_id, facts = _upload_and_extract(client, auth_settings)
    assert len(facts) >= 2
    assert (
        client.patch(
            f"/editor/cases/{case_id}/facts/{facts[0]['id']}",
            json={"status": "verified"},
        ).status_code
        == 200
    )
    for fact in facts[1:]:
        assert (
            client.patch(
                f"/editor/cases/{case_id}/facts/{fact['id']}",
                json={"status": "rejected"},
            ).status_code
            == 200
        )
    published = client.post(f"/editor/cases/{case_id}/publish")
    assert published.status_code == 200, published.text
    assert published.json()["status"] == "published"
