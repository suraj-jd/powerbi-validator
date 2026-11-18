"""Unit tests for rotating file logging, secret redaction, and global exception hooks."""

from __future__ import annotations

import logging
import sys
import threading
from pathlib import Path

from app.core.config import AppConfig
from app.core.exceptions import AppError, install_exception_hooks
from app.core.logging_config import REDACTED, redact_secrets, setup_logging


def test_redact_secrets_masks_tokens_and_credentials() -> None:
    jwt = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.signatureValue12345"
    sample = (
        f"Authorization: Bearer abc123.token_value | "
        f"jwt={jwt} | "
        f'access_token="my-secret-token" | '
        f"refresh_token=ref_98765 | "
        f"client_secret=superSecret! | "
        f"password=MyPassword123"
    )

    cleaned = redact_secrets(sample)

    assert "abc123.token_value" not in cleaned
    assert jwt not in cleaned
    assert "my-secret-token" not in cleaned
    assert "ref_98765" not in cleaned
    assert "superSecret!" not in cleaned
    assert "MyPassword123" not in cleaned
    assert cleaned.count(REDACTED) >= 6


def test_rotating_file_logger_writes_redacted_logs(tmp_path: Path) -> None:
    config = AppConfig(log_level="DEBUG", log_max_bytes=10_240, log_backup_count=2)
    log_path = setup_logging(config, tmp_path / "logs", include_console=False)

    test_logger = logging.getLogger("tests.redaction")
    test_logger.error("Request failed with Bearer secret_bearer_xyz987 and client_secret=topsecret")

    # Flush handlers cleanly before reading
    for handler in logging.getLogger().handlers:
        handler.flush()

    log_content = log_path.read_text(encoding="utf-8")
    assert "secret_bearer_xyz987" not in log_content
    assert "topsecret" not in log_content
    assert REDACTED in log_content

    # Trigger rotation by writing >10KB of log entries
    for idx in range(180):
        test_logger.info("Log rotation test payload line %03d " + ("x" * 70), idx)
    for handler in logging.getLogger().handlers:
        handler.flush()

    rotated_files = list((tmp_path / "logs").glob("app.log*"))
    assert len(rotated_files) >= 2


def test_global_exception_hook_logs_and_notifies_without_leaking_secrets(tmp_path: Path) -> None:
    config = AppConfig(log_level="INFO")
    log_path = setup_logging(config, tmp_path / "logs", include_console=False)

    notified: list[str] = []
    prev_sys, prev_thread = install_exception_hooks(on_unhandled_error=notified.append)
    try:
        try:
            raise RuntimeError("Failed with access_token=leak_me_12345")
        except RuntimeError as exc:
            sys.excepthook(type(exc), exc, exc.__traceback__)
    finally:
        sys.excepthook = prev_sys
        threading.excepthook = prev_thread

    for handler in logging.getLogger().handlers:
        handler.flush()

    assert len(notified) == 1
    assert "leak_me_12345" not in notified[0]
    assert REDACTED in notified[0]

    log_content = log_path.read_text(encoding="utf-8")
    assert "leak_me_12345" not in log_content
    assert REDACTED in log_content


def test_app_error_preserves_friendly_user_message(tmp_path: Path) -> None:
    config = AppConfig(log_level="INFO")
    setup_logging(config, tmp_path / "logs", include_console=False)

    notified: list[str] = []
    prev_sys, prev_thread = install_exception_hooks(on_unhandled_error=notified.append)
    try:
        exc = AppError("internal detail", user_message="Friendly message for UI")
        sys.excepthook(type(exc), exc, None)
    finally:
        sys.excepthook = prev_sys
        threading.excepthook = prev_thread

    assert notified == ["Friendly message for UI"]
