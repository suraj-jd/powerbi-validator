"""CRUD repository for immutable validation runs and per-rule validation results."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.exceptions import PersistenceError
from app.database.models import ValidationResult, ValidationRun, utc_now


class ValidationRunRepository:
    """Repository managing `validation_runs` and `validation_results` records."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def create_run(
        self,
        *,
        workspace_registration_id: int,
        app_version: str,
        overall_status: str = "RUNNING",
        started_at: datetime | None = None,
    ) -> ValidationRun:
        run = ValidationRun(
            workspace_registration_id=workspace_registration_id,
            started_at=started_at or utc_now(),
            overall_status=overall_status,
            passed_count=0,
            failed_count=0,
            warning_count=0,
            error_count=0,
            app_version=app_version,
        )
        self._session.add(run)
        self._session.flush()
        return run

    def complete_run(
        self,
        run_id: int,
        *,
        overall_status: str,
        passed_count: int,
        failed_count: int,
        warning_count: int,
        error_count: int,
        duration_ms: int,
        completed_at: datetime | None = None,
    ) -> ValidationRun:
        run = self.get_run(run_id)
        if run is None:
            raise PersistenceError(f"Validation run {run_id} not found.")

        run.overall_status = overall_status
        run.passed_count = passed_count
        run.failed_count = failed_count
        run.warning_count = warning_count
        run.error_count = error_count
        run.duration_ms = duration_ms
        run.completed_at = completed_at or utc_now()
        self._session.flush()
        return run

    def get_run(self, run_id: int) -> ValidationRun | None:
        return self._session.get(ValidationRun, run_id)

    def list_runs(
        self,
        *,
        workspace_registration_id: int | None = None,
        limit: int | None = None,
    ) -> list[ValidationRun]:
        stmt = select(ValidationRun)
        if workspace_registration_id is not None:
            stmt = stmt.where(
                ValidationRun.workspace_registration_id == workspace_registration_id
            )
        stmt = stmt.order_by(ValidationRun.started_at.desc(), ValidationRun.id.desc())
        if limit is not None:
            stmt = stmt.limit(limit)
        return list(self._session.scalars(stmt).all())

    def add_result(
        self,
        *,
        validation_run_id: int,
        status: str,
        result_summary: str,
        validation_rule_id: int | None = None,
        actual_value: str | None = None,
        expected_value: str | None = None,
        deviation: str | None = None,
        detailed_message: str | None = None,
        started_at: datetime | None = None,
        completed_at: datetime | None = None,
    ) -> ValidationResult:
        result = ValidationResult(
            validation_run_id=validation_run_id,
            validation_rule_id=validation_rule_id,
            status=status,
            actual_value=actual_value,
            expected_value=expected_value,
            deviation=deviation,
            result_summary=result_summary,
            detailed_message=detailed_message,
            started_at=started_at or utc_now(),
            completed_at=completed_at or utc_now(),
        )
        self._session.add(result)
        self._session.flush()
        return result

    def list_results_for_run(self, validation_run_id: int) -> list[ValidationResult]:
        stmt = (
            select(ValidationResult)
            .where(ValidationResult.validation_run_id == validation_run_id)
            .order_by(ValidationResult.id.asc())
        )
        return list(self._session.scalars(stmt).all())

    def delete_run(self, run_id: int) -> bool:
        run = self.get_run(run_id)
        if run is None:
            return False
        self._session.delete(run)
        self._session.flush()
        return True
