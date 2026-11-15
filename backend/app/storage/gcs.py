from __future__ import annotations

from datetime import timedelta

from app.storage.base import StoredObject


class GcsStorage:
    """Google Cloud Storage backend. Requires google-cloud-storage when used."""

    def __init__(self, bucket_name: str, *, location: str | None = None) -> None:
        try:
            # Optional runtime dep — Decision 2.5: keep ignore until GCS is a required dep.
            from google.cloud import storage  # type: ignore[import-untyped]
        except ImportError as exc:  # pragma: no cover - exercised when dep missing
            raise RuntimeError(
                "GCS_BUCKET is set but google-cloud-storage is not installed. "
                "Add the dependency or unset GCS_BUCKET to use local storage."
            ) from exc

        self._client = storage.Client()
        self._bucket = self._client.bucket(bucket_name)
        self._location = location

    def put(
        self,
        key: str,
        data: bytes,
        *,
        content_type: str = "application/octet-stream",
    ) -> StoredObject:
        blob = self._bucket.blob(key)
        blob.upload_from_string(data, content_type=content_type)
        return StoredObject(key=key, size=len(data), content_type=content_type)

    def get(self, key: str) -> bytes:
        blob = self._bucket.blob(key)
        return blob.download_as_bytes()

    def exists(self, key: str) -> bool:
        return bool(self._bucket.blob(key).exists())

    def signed_url(self, key: str, *, expires_in: int) -> str:
        blob = self._bucket.blob(key)
        return blob.generate_signed_url(
            version="v4",
            expiration=timedelta(seconds=max(1, expires_in)),
            method="GET",
        )
