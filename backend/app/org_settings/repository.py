from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal

from app.users.db import connect, init_db

TtsProvider = Literal["synthetic", "edge", "azure", "elevenlabs"]
VALID_PROVIDERS = {"synthetic", "edge", "azure", "elevenlabs"}


@dataclass(frozen=True)
class TtsOrgSettings:
    provider: TtsProvider
    premium_enabled: bool
    updated_at: str | None


def _now() -> str:
    return datetime.now(UTC).isoformat()


class OrgSettingsRepository:
    def __init__(self, db_path: str) -> None:
        self.db_path = db_path
        with connect(db_path) as conn:
            init_db(conn)

    def _conn(self) -> sqlite3.Connection:
        return connect(self.db_path)

    def get_tts(self) -> TtsOrgSettings:
        with self._conn() as conn:
            provider_row = conn.execute(
                "SELECT value, updated_at FROM org_settings WHERE key = 'tts_provider'"
            ).fetchone()
            premium_row = conn.execute(
                "SELECT value, updated_at FROM org_settings WHERE key = 'tts_premium_enabled'"
            ).fetchone()
        provider = "synthetic"
        if provider_row and provider_row["value"] in VALID_PROVIDERS:
            provider = provider_row["value"]
        premium = False
        if premium_row and str(premium_row["value"]).lower() in {"1", "true", "yes"}:
            premium = True
        updated = None
        for row in (provider_row, premium_row):
            if row and row["updated_at"]:
                updated = row["updated_at"]
        return TtsOrgSettings(
            provider=provider,  # type: ignore[arg-type]
            premium_enabled=premium,
            updated_at=updated,
        )

    def set_tts(
        self,
        *,
        provider: TtsProvider | None = None,
        premium_enabled: bool | None = None,
    ) -> TtsOrgSettings:
        now = _now()
        with self._conn() as conn:
            if provider is not None:
                if provider not in VALID_PROVIDERS:
                    raise ValueError(f"Invalid TTS provider: {provider}")
                conn.execute(
                    """
                    INSERT INTO org_settings (key, value, updated_at)
                    VALUES ('tts_provider', ?, ?)
                    ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at
                    """,
                    (provider, now),
                )
            if premium_enabled is not None:
                conn.execute(
                    """
                    INSERT INTO org_settings (key, value, updated_at)
                    VALUES ('tts_premium_enabled', ?, ?)
                    ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at
                    """,
                    ("true" if premium_enabled else "false", now),
                )
            conn.commit()
        return self.get_tts()
