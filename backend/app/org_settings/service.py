from __future__ import annotations

from functools import lru_cache

from app.auth.settings import get_auth_settings
from app.org_settings.repository import OrgSettingsRepository, TtsOrgSettings


@lru_cache
def get_org_settings_repository() -> OrgSettingsRepository:
    return OrgSettingsRepository(get_auth_settings().database_path)


def get_tts_org_settings() -> TtsOrgSettings:
    return get_org_settings_repository().get_tts()
