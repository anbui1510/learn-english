"""Case ownership model: owner must be editor/admin user id."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.auth.settings import AuthSettings
from app.cases.ownership import CaseOwnershipError, assert_can_own_case
from app.cases.service import get_case_repository
from tests.conftest import seed_admin_editor_learner, set_session_cookie


def test_assert_can_own_case_rejects_learner(auth_settings: AuthSettings) -> None:
    _, _, learner = seed_admin_editor_learner(auth_settings)
    with pytest.raises(CaseOwnershipError, match="editor or admin"):
        assert_can_own_case(learner)


def test_create_case_rejects_learner_owner(auth_settings: AuthSettings) -> None:
    _, _, learner = seed_admin_editor_learner(auth_settings)
    repo = get_case_repository()
    with pytest.raises(CaseOwnershipError):
        repo.create_case(owner=learner, title="Should fail")


def test_reassign_to_learner_rejected(auth_settings: AuthSettings) -> None:
    _, editor, learner = seed_admin_editor_learner(auth_settings)
    cases = get_case_repository()
    case = cases.create_case(owner=editor, title="Owned by editor")
    with pytest.raises(CaseOwnershipError):
        cases.reassign_owner(case_id=case.id, new_owner=learner)
    still = cases.get_by_id(case.id)
    assert still is not None
    assert still.owner_user_id == editor.id


def test_editor_creates_case_via_api(
    client: TestClient, auth_settings: AuthSettings
) -> None:
    _, editor, learner = seed_admin_editor_learner(auth_settings)
    set_session_cookie(client, auth_settings, editor)
    response = client.post(
        "/editor/cases",
        json={"title": "Nelson bronchiolitis draft", "isbn": "978-0-323-52950-1"},
    )
    assert response.status_code == 201
    body = response.json()
    assert body["owner_user_id"] == editor.id
    assert body["status"] == "draft"
    assert body["title"] == "Nelson bronchiolitis draft"

    listed = client.get("/editor/cases")
    assert listed.status_code == 200
    assert any(row["id"] == body["id"] for row in listed.json())

    set_session_cookie(client, auth_settings, learner)
    denied = client.post("/editor/cases", json={"title": "Nope"})
    assert denied.status_code == 403
