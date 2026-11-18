"""Rotating file logging with automatic secret and token redaction."""

from __future__ import annotations

import logging
import re
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.core.config import AppConfig

REDACTED = "[REDACTED]"
LOG_FILE_NAME = "app.log"

# Patterns matching sensitive credentials, tokens, and authorization headers.
_SECRET_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    # Authorization: Bearer <token> or raw Bearer <token>
    (
        re.compile(r"(?i)(Bearer\s+)[A-Za-z0-9\-._~+/]+=*"),
        rf"\1{REDACTED}",
    ),
    # JSON Web Tokens (header.payload.signature)
    (
        re.compile(r"\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\b"),
        REDACTED,
    ),
    # Key-value or JSON pairs for sensitive keys
    (
        re.compile(
            r'(?i)(["\']?(?:access_token|refresh_token|id_token|client_secret|password|passwd|secret|authorization|api_key)["\']?\s*[:=]\s*["\']?)([^"\'\s,;}\]]+)'
        ),
        rf"\1{REDACTED}",
    ),
)


def redact_secrets(text: str) -> str:
    """Scrub tokens, secrets, and passwords from a log message or traceback."""
    sanitized = text
    for pattern, replacement in _SECRET_PATTERNS:
        sanitized = pattern.sub(replacement, sanitized)
    return sanitized


class RedactingFormatter(logging.Formatter):
    """Log formatter that redacts secrets from formatted messages and tracebacks."""

    def format(self, record: logging.LogRecord) -> str:
        formatted = super().format(record)
        return redact_secrets(formatted)


def setup_logging(
    config: AppConfig,
    logs_dir: Path,
    *,
    include_console: bool = True,
) -> Path:
    """Configure root logging with a rotating local file handler and secret redaction."""
    logs_dir.mkdir(parents=True, exist_ok=True)
    log_path = logs_dir / LOG_FILE_NAME

    formatter = RedactingFormatter(
        fmt="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, config.log_level, logging.INFO))

    # Close and replace existing handlers cleanly so repeated setup does not duplicate logs.
    for existing in list(root_logger.handlers):
        root_logger.removeHandler(existing)
        try:
            existing.close()
        except Exception:
            pass

    file_handler = RotatingFileHandler(
        filename=log_path,
        maxBytes=config.log_max_bytes,
        backupCount=config.log_backup_count,
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)
    root_logger.addHandler(file_handler)

    if include_console:
        console_handler = logging.StreamHandler(stream=sys.stderr)
        console_handler.setFormatter(formatter)
        root_logger.addHandler(console_handler)

    return log_path
