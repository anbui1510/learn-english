from __future__ import annotations

import hashlib
import hmac
import time
from pathlib import Path
from urllib.parse import quote

from app.storage.base import StoredObject


class LocalFilesystemStorage:
    """Stores objects under a local root; signed URLs use HMAC query tokens."""

    def __init__(
        self,
        root: str | Path,
        *,
        signing_secret: str,
        public_base_url: str,
    ) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.signing_secret = signing_secret.encode("utf-8")
        self.public_base_url = public_base_url.rstrip("/")

    def _path_for(self, key: str) -> Path:
        # Prevent path traversal
        safe = Path(key)
        if safe.is_absolute() or ".." in safe.parts:
            raise ValueError(f"Invalid object key: {key!r}")
        return self.root / safe

    def put(
        self,
        key: str,
        data: bytes,
        *,
        content_type: str = "application/octet-stream",
    ) -> StoredObject:
        path = self._path_for(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        meta = path.with_suffix(path.suffix + ".content_type")
        meta.write_text(content_type, encoding="utf-8")
        return StoredObject(key=key, size=len(data), content_type=content_type)

    def get(self, key: str) -> bytes:
        path = self._path_for(key)
        if not path.is_file():
            raise FileNotFoundError(key)
        return path.read_bytes()

    def exists(self, key: str) -> bool:
        return self._path_for(key).is_file()

    def content_type(self, key: str) -> str:
        path = self._path_for(key)
        meta = path.with_suffix(path.suffix + ".content_type")
        if meta.is_file():
            return meta.read_text(encoding="utf-8").strip() or "application/octet-stream"
        return "application/octet-stream"

    def signed_url(self, key: str, *, expires_in: int) -> str:
        exp = int(time.time()) + max(1, expires_in)
        sig = self.sign(key, exp)
        return (
            f"{self.public_base_url}/storage/local"
            f"?key={quote(key, safe='')}"
            f"&exp={exp}&sig={sig}"
        )

    def sign(self, key: str, exp: int) -> str:
        msg = f"{key}:{exp}".encode("utf-8")
        return hmac.new(self.signing_secret, msg, hashlib.sha256).hexdigest()

    def verify_signature(self, key: str, exp: int, sig: str) -> bool:
        if exp < int(time.time()):
            return False
        expected = self.sign(key, exp)
        return hmac.compare_digest(expected, sig)
