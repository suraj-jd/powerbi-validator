"""Standard evaluation result models for the validation engine (Stage 10)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from app.core.status import ValidationStatus
from app.database.models import utc_now


@dataclass(frozen=True, slots=True)
class CheckEvaluationResult:
    """Standardized result returned by any validation check in the engine."""

    rule_id: int
    rule_name: str
    validation_type: str
    target_type: str
    status: ValidationStatus
    actual_value: str
    expected_value: str
    deviation: str | None
    result_summary: str
    detailed_message: str | None
    started_at: datetime
    completed_at: datetime
    duration_ms: int
    metadata_snapshot: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def create_error(
        cls,
        *,
        rule_id: int,
        rule_name: str,
        validation_type: str,
        target_type: str,
        error_message: str,
        started_at: datetime,
        expected_value: str = "-",
        detailed_message: str | None = None,
        duration_ms: int | None = None,
    ) -> CheckEvaluationResult:
        """Helper to create standard ERROR result for execution, connectivity, or query failures."""
        now = utc_now()
        dur = duration_ms if duration_ms is not None else int((now - started_at).total_seconds() * 1000)
        return cls(
            rule_id=rule_id,
            rule_name=rule_name,
            validation_type=validation_type,
            target_type=target_type,
            status=ValidationStatus.ERROR,
            actual_value="Error",
            expected_value=expected_value,
            deviation="Execution Error",
            result_summary=error_message,
            detailed_message=detailed_message or error_message,
            started_at=started_at,
            completed_at=now,
            duration_ms=max(0, dur),
            metadata_snapshot={"error": error_message},
        )
