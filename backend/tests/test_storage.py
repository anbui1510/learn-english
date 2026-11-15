from __future__ import annotations

from urllib.parse import parse_qs, urlparse

from app.auth.settings import AuthSettings
from app.storage.factory import get_storage
from app.storage.local import LocalFilesystemStorage


def test_factory_uses_local_when_gcs_unset(auth_settings: AuthSettings) -> None:
    storage = get_storage()
    assert isinstance(storage, LocalFilesystemStorage)


def test_local_put_get_exists_and_signed_url(auth_settings: AuthSettings) -> None:
    storage = get_storage()
    assert isinstance(storage, LocalFilesystemStorage)

    key = "cases/1/sample.pdf"
    payload = b"%PDF-1.4 test"
    stored = storage.put(key, payload, content_type="application/pdf")
    assert stored.key == key
    assert stored.size == len(payload)
    assert storage.exists(key)
    assert storage.get(key) == payload

    url = storage.signed_url(key, expires_in=60)
    parsed = urlparse(url)
    assert parsed.path == "/storage/local"
    qs = parse_qs(parsed.query)
    assert qs["key"][0] == key
    assert storage.verify_signature(key, int(qs["exp"][0]), qs["sig"][0])
