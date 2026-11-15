from __future__ import annotations

from urllib.parse import parse_qs, urlparse

from fastapi.testclient import TestClient

from app.auth.settings import AuthSettings
from tests.conftest import MINIMAL_PDF, seed_admin_editor_learner, set_session_cookie


def test_upload_creates_case_draft_with_object(
    client: TestClient, auth_settings: AuthSettings
) -> None:
    _, editor, learner = seed_admin_editor_learner(auth_settings)
    set_session_cookie(client, auth_settings, editor)

    response = client.post(
        "/editor/cases/upload",
        data={
            "title": "Nelson bronchiolitis",
            "isbn": "978-0-323-52950-1",
            "edition": "22e",
        },
        files={"file": ("chapter.pdf", MINIMAL_PDF, "application/pdf")},
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["owner_user_id"] == editor.id
    assert body["isbn"] == "978-0-323-52950-1"
    assert body["edition"] == "22e"
    assert body["status"] == "draft"
    assert body["pdf_object_key"]
    assert body["pdf_byte_size"] == len(MINIMAL_PDF)

    set_session_cookie(client, auth_settings, learner)
    denied = client.post(
        "/editor/cases/upload",
        data={"title": "Nope", "isbn": "1", "edition": "1"},
        files={"file": ("chapter.pdf", MINIMAL_PDF, "application/pdf")},
    )
    assert denied.status_code == 403


def test_upload_rejects_non_pdf_and_oversized(
    client: TestClient, auth_settings: AuthSettings
) -> None:
    _, editor, _ = seed_admin_editor_learner(auth_settings)
    set_session_cookie(client, auth_settings, editor)

    bad_mime = client.post(
        "/editor/cases/upload",
        data={"title": "X", "isbn": "1", "edition": "1"},
        files={"file": ("notes.txt", b"hello", "text/plain")},
    )
    assert bad_mime.status_code == 400

    huge = b"%PDF-1.4\n" + (b"x" * (auth_settings.pdf_max_bytes + 10))
    oversized = client.post(
        "/editor/cases/upload",
        data={"title": "X", "isbn": "1", "edition": "1"},
        files={"file": ("big.pdf", huge, "application/pdf")},
    )
    assert oversized.status_code == 413


def test_upload_requires_isbn_and_edition(
    client: TestClient, auth_settings: AuthSettings
) -> None:
    _, editor, _ = seed_admin_editor_learner(auth_settings)
    set_session_cookie(client, auth_settings, editor)
    missing = client.post(
        "/editor/cases/upload",
        data={"title": "X", "isbn": "", "edition": "22e"},
        files={"file": ("chapter.pdf", MINIMAL_PDF, "application/pdf")},
    )
    assert missing.status_code == 422


def test_download_url_owner_ok_learner_forbidden(
    client: TestClient, auth_settings: AuthSettings
) -> None:
    _, editor, learner = seed_admin_editor_learner(auth_settings)
    set_session_cookie(client, auth_settings, editor)
    created = client.post(
        "/editor/cases/upload",
        data={"title": "X", "isbn": "978-1", "edition": "22e"},
        files={"file": ("chapter.pdf", MINIMAL_PDF, "application/pdf")},
    )
    case_id = created.json()["id"]

    url_resp = client.get(f"/editor/cases/{case_id}/download-url")
    assert url_resp.status_code == 200
    payload = url_resp.json()
    assert payload["expires_in"] == 300
    parsed = urlparse(payload["url"])
    assert parsed.path == "/storage/local"
    qs = parse_qs(parsed.query)

    client.cookies.clear()
    downloaded = client.get(
        "/storage/local",
        params={"key": qs["key"][0], "exp": qs["exp"][0], "sig": qs["sig"][0]},
    )
    assert downloaded.status_code == 200
    assert downloaded.content == MINIMAL_PDF

    set_session_cookie(client, auth_settings, learner)
    forbidden = client.get(f"/editor/cases/{case_id}/download-url")
    assert forbidden.status_code == 403

    bad = client.get(
        "/storage/local",
        params={"key": qs["key"][0], "exp": "1", "sig": "deadbeef"},
    )
    assert bad.status_code == 403
