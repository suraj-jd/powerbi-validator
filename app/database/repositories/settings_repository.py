"""CRUD repository for non-secret local application settings."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.exceptions import PersistenceError
from app.database.models import AppSetting, utc_now

_FORBIDDEN_KEY_SUBSTRINGS = (
    "token",
    "secret",
    "password",
    "passwd",
    "credential",
    "authorization",
    "api_key",
)


def _assert_non_secret_key(key: str) -> None:
    normalized = key.strip().lower()
    if not normalized:
        raise PersistenceError("Setting key must not be empty.")
    for forbidden in _FORBIDDEN_KEY_SUBSTRINGS:
        if forbidden in normalized:
            raise PersistenceError(
                f"Refusing to store potential secret key '{key}' in SQLite app_settings.",
                user_message="Authentication tokens and secrets cannot be stored in the local database.",
            )


class AppSettingsRepository:
    """Repository for reading and writing non-secret `app_settings` entries."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def get(self, key: str) -> AppSetting | None:
        return self._session.get(AppSetting, key)

    def get_value(self, key: str, default: str | None = None) -> str | None:
        setting = self.get(key)
        return setting.value if setting is not None else default

    def set(self, key: str, value: str) -> AppSetting:
        _assert_non_secret_key(key)
        setting = self.get(key)
        if setting is None:
            setting = AppSetting(key=key, value=value, updated_at=utc_now())
            self._session.add(setting)
        else:
            setting.value = value
            setting.updated_at = utc_now()
        self._session.flush()
        return setting

    def list_all(self) -> list[AppSetting]:
        stmt = select(AppSetting).order_by(AppSetting.key.asc())
        return list(self._session.scalars(stmt).all())

    def delete(self, key: str) -> bool:
        setting = self.get(key)
        if setting is None:
            return False
        self._session.delete(setting)
        self._session.flush()
        return True
