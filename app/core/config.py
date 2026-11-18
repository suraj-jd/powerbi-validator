"""Central non-secret application configuration and local directory paths."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.core.exceptions import ConfigurationError

APP_DIR_NAME = "PowerBIValidationTool"
DATA_DIR_ENV_VAR = "PBI_VALIDATOR_DATA_DIR"
CLIENT_ID_ENV_VAR = "PBI_VALIDATOR_CLIENT_ID"
TENANT_ID_ENV_VAR = "PBI_VALIDATOR_TENANT_ID"

LogLevelName = Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
AuthModeName = Literal["auto", "azure_cli", "entra_msal"]


class AppConfig(BaseModel):
    """Validated non-secret application settings.

    Tokens, client secrets, and passwords must NEVER be stored here.
    """

    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    log_level: LogLevelName = Field(default="INFO")
    log_max_bytes: int = Field(default=2 * 1024 * 1024, ge=10_240, le=50 * 1024 * 1024)
    log_backup_count: int = Field(default=5, ge=1, le=20)
    timezone_name: str = Field(default="Local")
    window_width: int = Field(default=1180, ge=900, le=3840)
    window_height: int = Field(default=760, ge=600, le=2160)
    history_retention_days: int = Field(default=90, ge=7, le=3650)
    # Authentication mode: "auto" uses Entra MSAL if a Client ID is configured, else Azure CLI
    auth_mode: AuthModeName = Field(default="auto")
    # Public OAuth client identifiers (non-secret; desktop apps use PKCE with no client secret)
    auth_client_id: str = Field(default="")
    auth_tenant_id: str = Field(default="organizations")

    def effective_client_id(self) -> str:
        """Return the Entra Client ID from env override or saved config."""
        return os.environ.get(CLIENT_ID_ENV_VAR, self.auth_client_id).strip()

    def effective_tenant_id(self) -> str:
        """Return the Entra Tenant ID / authority segment from env override or saved config."""
        value = os.environ.get(TENANT_ID_ENV_VAR, self.auth_tenant_id).strip()
        return value or "organizations"


def get_app_data_dir(override_dir: Path | None = None) -> Path:
    """Resolve and ensure the local application data directory exists."""
    if override_dir is not None:
        base = Path(override_dir)
    elif env_dir := os.environ.get(DATA_DIR_ENV_VAR):
        base = Path(env_dir)
    else:
        local_app_data = os.environ.get("LOCALAPPDATA")
        if local_app_data:
            base = Path(local_app_data) / APP_DIR_NAME
        else:
            base = Path.home() / f".{APP_DIR_NAME.lower()}"

    base.mkdir(parents=True, exist_ok=True)
    return base


def get_logs_dir(data_dir: Path | None = None) -> Path:
    """Return the local directory used for rotating log files."""
    logs_dir = get_app_data_dir(data_dir) / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    return logs_dir


def get_database_path(data_dir: Path | None = None) -> Path:
    """Return the path to the local SQLite database file."""
    db_dir = get_app_data_dir(data_dir) / "data"
    db_dir.mkdir(parents=True, exist_ok=True)
    return db_dir / "validation_tool.db"


def get_token_cache_path(data_dir: Path | None = None) -> Path:
    """Return the path to the Windows DPAPI-protected MSAL token cache file."""
    auth_dir = get_app_data_dir(data_dir) / "auth"
    auth_dir.mkdir(parents=True, exist_ok=True)
    return auth_dir / "msal_token_cache.bin"


def get_config_file_path(data_dir: Path | None = None) -> Path:
    """Return the path to the local JSON configuration file."""
    return get_app_data_dir(data_dir) / "config.json"


def load_config(data_dir: Path | None = None) -> AppConfig:
    """Load application config from disk, or create defaults on first run."""
    config_path = get_config_file_path(data_dir)
    if not config_path.exists():
        config = AppConfig()
        save_config(config, data_dir=data_dir)
        return config

    try:
        raw_text = config_path.read_text(encoding="utf-8")
        raw_data = json.loads(raw_text)
        return AppConfig.model_validate(raw_data)
    except (OSError, json.JSONDecodeError, ValidationError) as exc:
        raise ConfigurationError(
            f"Failed to load application configuration from {config_path}: {exc}",
            user_message=(
                "Application configuration could not be loaded. Check or reset config.json."
            ),
        ) from exc


def save_config(config: AppConfig, data_dir: Path | None = None) -> Path:
    """Persist validated non-secret configuration to disk."""
    config_path = get_config_file_path(data_dir)
    try:
        config_path.parent.mkdir(parents=True, exist_ok=True)
        config_path.write_text(
            config.model_dump_json(indent=2) + "\n",
            encoding="utf-8",
        )
        return config_path
    except OSError as exc:
        raise ConfigurationError(
            f"Failed to save application configuration to {config_path}: {exc}",
            user_message="Could not save application configuration to disk.",
        ) from exc
