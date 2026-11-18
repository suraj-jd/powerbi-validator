"""Canonical status enumerations shared across the application."""

from __future__ import annotations

from enum import StrEnum


class ValidationStatus(StrEnum):
    """Four distinct validation outcomes defined in BRD Section 6."""

    PASS = "PASS"
    FAIL = "FAIL"
    WARNING = "WARNING"
    ERROR = "ERROR"


class RefreshStatus(StrEnum):
    """Normalized Power BI dataset refresh states defined in BRD Section 7."""

    SUCCESS = "Success"
    FAILED = "Failed"
    IN_PROGRESS = "In Progress"
    UNKNOWN = "Unknown"


class NotificationLevel(StrEnum):
    """Severity levels for UI notification banners."""

    INFO = "info"
    SUCCESS = "success"
    WARNING = "warning"
    ERROR = "error"
