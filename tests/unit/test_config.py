"""Unit tests for central application configuration handling."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.core.config import (
    DATA_DIR_ENV_VAR,
    AppConfig,
    get_app_data_dir,
    get_config_file_path,
    load_config,
    save_config,
)
from app.core.exceptions import ConfigurationError


def test_load_config_creates_defaults_on_first_run(tmp_path: Path) -> None:
    config = load_config(data_dir=tmp_path)

    assert config.log_level == "INFO"
    assert config.window_width == 1180
    assert config.window_height == 760
    assert get_config_file_path(tmp_path).exists()


def test_save_and_load_config_roundtrip(tmp_path: Path) -> None:
    updated = AppConfig(
        log_level="DEBUG",
        log_backup_count=3,
        window_width=1440,
        window_height=900,
        history_retention_days=180,
    )
    save_config(updated, data_dir=tmp_path)

    reloaded = load_config(data_dir=tmp_path)
    assert reloaded == updated


def test_load_config_rejects_unknown_fields_such_as_secrets(tmp_path: Path) -> None:
    config_file = get_config_file_path(tmp_path)
    config_file.write_text('{"access_token": "should-not-be-here"}', encoding="utf-8")

    with pytest.raises(ConfigurationError):
        load_config(data_dir=tmp_path)


def test_load_config_rejects_corrupt_json(tmp_path: Path) -> None:
    config_file = get_config_file_path(tmp_path)
    config_file.write_text("{not valid json", encoding="utf-8")

    with pytest.raises(ConfigurationError):
        load_config(data_dir=tmp_path)


def test_env_var_overrides_app_data_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    custom_dir = tmp_path / "custom_data"
    monkeypatch.setenv(DATA_DIR_ENV_VAR, str(custom_dir))

    resolved = get_app_data_dir()
    assert resolved == custom_dir
    assert custom_dir.exists()
