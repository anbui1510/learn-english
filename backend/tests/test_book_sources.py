from __future__ import annotations

from fastapi.testclient import TestClient

from app.auth.settings import AuthSettings
from app.books.repository import BookSourceRepository, DEFAULT_SOURCES
from tests.conftest import seed_admin_editor_learner, set_session_cookie


def test_default_sources_seeded(tmp_path) -> None:
    db = str(tmp_path / "books.sqlite3")
    repo = BookSourceRepository(db)
    listed = repo.list_sources()
    slugs = {s.slug for s in listed}
    assert "nelson-pediatrics" in slugs
    assert "harriet-lane" in slugs
    assert "who-guidelines" in slugs
    assert len(listed) >= len(DEFAULT_SOURCES)


def test_admin_crud_and_case_link(
    client: TestClient, auth_settings: AuthSettings
) -> None:
    admin, editor, _ = seed_admin_editor_learner(auth_settings)
    set_session_cookie(client, auth_settings, admin)

    listed = client.get("/admin/book-sources")
    assert listed.status_code == 200
    assert len(listed.json()) >= 3

    created = client.post(
        "/admin/book-sources",
        json={
            "slug": "local-guideline",
            "title": "Local Pediatric Guideline",
            "publisher": "Hospital CME",
            "default_isbn": "978-1-111-11111-1",
            "notes": "Internal handbook",
        },
    )
    assert created.status_code == 201, created.text
    source_id = created.json()["id"]
    assert created.json()["slug"] == "local-guideline"

    patched = client.patch(
        f"/admin/book-sources/{source_id}",
        json={"notes": "Updated notes"},
    )
    assert patched.status_code == 200
    assert patched.json()["notes"] == "Updated notes"

    set_session_cookie(client, auth_settings, editor)
    case = client.post(
        "/editor/cases",
        json={
            "title": "Guideline fever case",
            "isbn": "978-1-111-11111-1",
            "edition": "2024",
            "book_source_id": source_id,
        },
    )
    assert case.status_code == 201, case.text
    assert case.json()["book_source_id"] == source_id
    assert case.json()["book_source_slug"] == "local-guideline"

    # Learners/editors can list sources read-only for picker
    sources = client.get("/editor/book-sources")
    assert sources.status_code == 200
    assert any(s["id"] == source_id for s in sources.json())
