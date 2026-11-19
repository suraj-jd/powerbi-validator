"""Application exception hierarchy and global uncaught exception handling."""

from __future__ import annotations

import logging
import sys
import threading
from collections.abc import Callable
from types import TracebackType

from app.core.logging_config import redact_secrets

logger = logging.getLogger(__name__)

ErrorCallback = Callable[[str], None]


class AppError(Exception):
    """Base exception for expected application-level failures."""

    def __init__(self, message: str, *, user_message: str | None = None) -> None:
        super().__init__(message)
        self.user_message = user_message or message


class ConfigurationError(AppError):
    """Raised when local application configuration is invalid or unreadable."""


class ValidationConfigError(AppError):
    """Raised when a validation rule or registration configuration is invalid."""


class PersistenceError(AppError):
    """Raised when local storage operations fail."""


class AuthenticationError(AppError):
    """Raised for sign-in or token acquisition errors (Stage 3+)."""


class PowerBIApiError(AppError):
    """Raised for Power BI REST or query execution errors (Stage 4+)."""


class ConcurrentRunError(AppError):
    """Raised when an execution run is triggered while another run is active for the same report."""


class ExecutionCancelledError(AppError):
    """Raised when an in-progress validation run is explicitly cancelled by the user."""


def format_safe_user_error(exc: BaseException) -> str:
    """Return a user-safe, redacted error message suitable for UI banners."""
    if isinstance(exc, AppError):
        return redact_secrets(exc.user_message)
    return redact_secrets(f"An unexpected error occurred: {type(exc).__name__}: {exc}")


def install_exception_hooks(
    on_unhandled_error: ErrorCallback | None = None,
) -> tuple[Callable[..., None], Callable[..., None]]:
    """Install application-wide uncaught exception hooks for main and worker threads.

    Returns the previous `(sys.excepthook, threading.excepthook)` so callers/tests
    can restore them if needed.
    """
    previous_sys_hook = sys.excepthook
    previous_thread_hook = threading.excepthook

    def _handle_sys_exception(
        exc_type: type[BaseException],
        exc_value: BaseException,
        exc_tb: TracebackType | None,
    ) -> None:
        if issubclass(exc_type, KeyboardInterrupt):
            previous_sys_hook(exc_type, exc_value, exc_tb)
            return

        logger.error(
            "Unhandled application exception: %s",
            redact_secrets(str(exc_value)),
            exc_info=(exc_type, exc_value, exc_tb),
        )
        if on_unhandled_error is not None:
            try:
                on_unhandled_error(format_safe_user_error(exc_value))
            except Exception:
                logger.exception("Failed to notify UI about unhandled exception.")

    def _handle_thread_exception(args: threading.ExceptHookArgs) -> None:
        if args.exc_value is None:
            return
        logger.error(
            "Unhandled exception in worker thread %s: %s",
            getattr(args.thread, "name", "unknown"),
            redact_secrets(str(args.exc_value)),
            exc_info=(args.exc_type, args.exc_value, args.exc_traceback),
        )
        if on_unhandled_error is not None:
            try:
                on_unhandled_error(format_safe_user_error(args.exc_value))
            except Exception:
                logger.exception("Failed to notify UI about worker thread exception.")

    sys.excepthook = _handle_sys_exception
    threading.excepthook = _handle_thread_exception
    return previous_sys_hook, previous_thread_hook
