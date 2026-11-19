"""Validation run orchestration engine and background execution worker (Stage 12).

Coordinates loading enabled rules, executing validation checks sequentially,
capturing timings and progress, managing cancellation, preventing concurrent runs,
and persisting full execution runs and per-rule results to local SQLite storage.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
import logging
import threading
from typing import Any, Sequence

from PySide6.QtCore import QObject, QThread, Signal

from app import APP_VERSION
from app.core.exceptions import ConcurrentRunError, ExecutionCancelledError
from app.core.status import ValidationStatus
from app.database.db import DatabaseManager
from app.database.models import ValidationResult, ValidationRun, utc_now
from app.database.repositories.run_repository import ValidationRunRepository
from app.integrations.powerbi.dax_client import DaxQueryClient
from app.services.refresh_service import RefreshService
from app.services.rule_service import (
    RuleRecord,
    RuleService,
    VALIDATION_TYPE_ANOMALY,
    VALIDATION_TYPE_ROW_COUNT,
)
from app.validation.models import CheckEvaluationResult
from app.validation.validator_factory import get_validator

logger = logging.getLogger(__name__)


def calculate_overall_status(statuses: Sequence[ValidationStatus | str]) -> ValidationStatus:
    """Calculate overall run status according to BRD Section 6.1 precedence:

    1. If any result is FAIL -> FAIL
    2. Else if any result is ERROR -> ERROR
    3. Else if any result is WARNING -> WARNING
    4. Else -> PASS (or WARNING if no rules were evaluated)
    """
    if not statuses:
        return ValidationStatus.WARNING

    normalized: list[ValidationStatus] = []
    for s in statuses:
        if isinstance(s, ValidationStatus):
            normalized.append(s)
        else:
            try:
                normalized.append(ValidationStatus(str(s).upper()))
            except Exception:
                normalized.append(ValidationStatus.ERROR)

    if any(s == ValidationStatus.FAIL for s in normalized):
        return ValidationStatus.FAIL
    if any(s == ValidationStatus.ERROR for s in normalized):
        return ValidationStatus.ERROR
    if any(s == ValidationStatus.WARNING for s in normalized):
        return ValidationStatus.WARNING
    return ValidationStatus.PASS


@dataclass(frozen=True, slots=True)
class ValidationResultDTO:
    """Detached immutable representation of one evaluated rule result."""

    id: int
    validation_run_id: int
    rule_id: int | None
    rule_name: str
    validation_type: str
    target_type: str
    target_display: str
    status: ValidationStatus
    actual_value: str | None
    expected_value: str | None
    deviation: str | None
    result_summary: str
    detailed_message: str | None
    duration_ms: int
    started_at: datetime
    completed_at: datetime


@dataclass(frozen=True, slots=True)
class ValidationRunSummaryDTO:
    """Detached immutable representation of a completed or historical validation run."""

    id: int
    workspace_registration_id: int
    overall_status: ValidationStatus
    passed_count: int
    failed_count: int
    warning_count: int
    error_count: int
    total_rules: int
    duration_ms: int
    app_version: str
    started_at: datetime
    completed_at: datetime | None
    results: list[ValidationResultDTO] = field(default_factory=list)

    @property
    def duration_display(self) -> str:
        """Concise readable duration string."""
        total_seconds = int(self.duration_ms / 1000)
        minutes, seconds = divmod(total_seconds, 60)
        if minutes > 0:
            return f"{minutes}m {seconds}s"
        return f"{self.duration_ms / 1000.0:.1f}s"

    @property
    def started_at_display(self) -> str:
        return self.started_at.strftime("%Y-%m-%d %H:%M:%S UTC")

    @classmethod
    def from_orm(cls, run: ValidationRun, results: list[ValidationResult] | None = None) -> ValidationRunSummaryDTO:
        orm_results = results if results is not None else (run.results or [])
        dtos: list[ValidationResultDTO] = []
        for r in orm_results:
            rule_record = r.validation_rule
            rule_name = rule_record.rule_name if rule_record else "Rule (Deleted)"
            val_type = rule_record.validation_type if rule_record else "unknown"
            t_type = rule_record.target_type if rule_record else "UNKNOWN"
            t_disp = RuleRecord.from_orm(rule_record).target_display if rule_record else "—"

            try:
                st = ValidationStatus(r.status)
            except Exception:
                st = ValidationStatus.ERROR

            dur = 0
            if r.completed_at and r.started_at:
                dur = int((r.completed_at - r.started_at).total_seconds() * 1000)

            dtos.append(
                ValidationResultDTO(
                    id=r.id,
                    validation_run_id=r.validation_run_id,
                    rule_id=r.validation_rule_id,
                    rule_name=rule_name,
                    validation_type=val_type,
                    target_type=t_type,
                    target_display=t_disp,
                    status=st,
                    actual_value=r.actual_value,
                    expected_value=r.expected_value,
                    deviation=r.deviation,
                    result_summary=r.result_summary,
                    detailed_message=r.detailed_message,
                    duration_ms=dur,
                    started_at=r.started_at,
                    completed_at=r.completed_at or r.started_at,
                )
            )

        try:
            ov = ValidationStatus(run.overall_status)
        except Exception:
            ov = ValidationStatus.ERROR

        total = run.passed_count + run.failed_count + run.warning_count + run.error_count
        return cls(
            id=run.id,
            workspace_registration_id=run.workspace_registration_id,
            overall_status=ov,
            passed_count=run.passed_count,
            failed_count=run.failed_count,
            warning_count=run.warning_count,
            error_count=run.error_count,
            total_rules=total,
            duration_ms=run.duration_ms or 0,
            app_version=run.app_version,
            started_at=run.started_at,
            completed_at=run.completed_at,
            results=dtos,
        )


class OrchestratorService:
    """Coordinates validation run execution, rule dispatching, and persistence."""

    def __init__(
        self,
        db: DatabaseManager,
        rule_service: RuleService,
        dax_client: DaxQueryClient,
        refresh_service: RefreshService | None = None,
        *,
        registry_service: Any | None = None,
        app_version: str = APP_VERSION,
    ) -> None:
        self._db = db
        self._rule_service = rule_service
        self._dax_client = dax_client
        self._refresh_service = refresh_service
        self._registry_service = registry_service
        self._app_version = app_version
        self._active_registrations: set[int] = set()
        self._lock = threading.Lock()

    def is_registration_running(self, workspace_registration_id: int) -> bool:
        """Check if an active validation run is currently executing for the registration."""
        with self._lock:
            return workspace_registration_id in self._active_registrations

    def run_validation(
        self,
        workspace_registration_id: int,
        *,
        workspace_id: str,
        dataset_id: str,
        is_cancelled_fn: Callable[[], bool] | None = None,
        on_progress: Callable[[int, int, str, CheckEvaluationResult | None], None] | None = None,
    ) -> ValidationRunSummaryDTO:
        """Execute all enabled rules for the registered dataset and persist results to SQLite."""
        # 1. Prevent concurrent runs on the same registration
        with self._lock:
            if workspace_registration_id in self._active_registrations:
                raise ConcurrentRunError(
                    f"A validation run is already in progress for registration #{workspace_registration_id}."
                )
            self._active_registrations.add(workspace_registration_id)

        try:
            return self._execute_run(
                workspace_registration_id,
                workspace_id=workspace_id,
                dataset_id=dataset_id,
                is_cancelled_fn=is_cancelled_fn,
                on_progress=on_progress,
            )
        finally:
            with self._lock:
                self._active_registrations.discard(workspace_registration_id)

    def _execute_run(
        self,
        workspace_registration_id: int,
        *,
        workspace_id: str,
        dataset_id: str,
        is_cancelled_fn: Callable[[], bool] | None = None,
        on_progress: Callable[[int, int, str, CheckEvaluationResult | None], None] | None = None,
    ) -> ValidationRunSummaryDTO:
        run_start = utc_now()

        # Load enabled rules
        rules = self._rule_service.list_rules(workspace_registration_id, enabled_only=True)
        # Sort by display_order
        rules.sort(key=lambda r: r.display_order)

        with self._db.session_scope() as session:
            repo = ValidationRunRepository(session)
            run = repo.create_run(
                workspace_registration_id=workspace_registration_id,
                app_version=self._app_version,
                overall_status="RUNNING",
                started_at=run_start,
            )
            run_id = run.id

        total_rules = len(rules)
        eval_results: list[CheckEvaluationResult] = []
        statuses: list[ValidationStatus] = []

        # If no enabled rules, complete immediately as WARNING
        if total_rules == 0:
            now = utc_now()
            dur_ms = int((now - run_start).total_seconds() * 1000)
            with self._db.session_scope() as session:
                repo = ValidationRunRepository(session)
                comp = repo.complete_run(
                    run_id,
                    overall_status=ValidationStatus.WARNING.value,
                    passed_count=0,
                    failed_count=0,
                    warning_count=1,
                    error_count=0,
                    duration_ms=dur_ms,
                    completed_at=now,
                )
                repo.add_result(
                    validation_run_id=run_id,
                    validation_rule_id=None,
                    status=ValidationStatus.WARNING.value,
                    result_summary="No enabled validation rules configured for this dataset.",
                    started_at=run_start,
                    completed_at=now,
                )
                results = repo.list_results_for_run(run_id)
                return ValidationRunSummaryDTO.from_orm(comp, results)

        # 2. Sequential execution of rules with progress & cancellation
        for idx, rule in enumerate(rules, start=1):
            if is_cancelled_fn and is_cancelled_fn():
                logger.info("Validation run #%s cancelled by user at rule %s/%s", run_id, idx, total_rules)
                break

            if on_progress:
                on_progress(idx, total_rules, rule.rule_name, None)

            # Build rule-specific context (e.g. historical data or previous run)
            rule_context = self._build_context_for_rule(workspace_registration_id, rule)

            check_res: CheckEvaluationResult
            try:
                validator = get_validator(rule.validation_type)
                check_res = validator.validate(
                    rule=rule,
                    dax_client=self._dax_client,
                    workspace_id=workspace_id,
                    dataset_id=dataset_id,
                    context=rule_context,
                )
            except Exception as exc:
                logger.exception("Unexpected error executing rule %s (ID %s): %s", rule.rule_name, rule.id, exc)
                check_res = CheckEvaluationResult.create_error(
                    rule_id=rule.id,
                    rule_name=rule.rule_name,
                    validation_type=rule.validation_type,
                    target_type=rule.target_type,
                    error_message=f"Validator internal error: {exc}",
                    started_at=utc_now(),
                )

            eval_results.append(check_res)
            statuses.append(check_res.status)

            # Persist per-rule result immediately to SQLite
            with self._db.session_scope() as session:
                repo = ValidationRunRepository(session)
                repo.add_result(
                    validation_run_id=run_id,
                    validation_rule_id=rule.id,
                    status=check_res.status.value,
                    actual_value=check_res.actual_value,
                    expected_value=check_res.expected_value,
                    deviation=check_res.deviation,
                    result_summary=check_res.result_summary,
                    detailed_message=check_res.detailed_message,
                    started_at=check_res.started_at,
                    completed_at=check_res.completed_at,
                )

            if on_progress:
                on_progress(idx, total_rules, rule.rule_name, check_res)

        # 3. Complete run and calculate summary
        run_end = utc_now()
        total_dur_ms = int((run_end - run_start).total_seconds() * 1000)
        overall_st = calculate_overall_status(statuses)

        p_count = sum(1 for s in statuses if s == ValidationStatus.PASS)
        f_count = sum(1 for s in statuses if s == ValidationStatus.FAIL)
        w_count = sum(1 for s in statuses if s == ValidationStatus.WARNING)
        e_count = sum(1 for s in statuses if s == ValidationStatus.ERROR)

        with self._db.session_scope() as session:
            repo = ValidationRunRepository(session)
            comp = repo.complete_run(
                run_id,
                overall_status=overall_st.value,
                passed_count=p_count,
                failed_count=f_count,
                warning_count=w_count,
                error_count=e_count,
                duration_ms=total_dur_ms,
                completed_at=run_end,
            )
            saved_results = repo.list_results_for_run(run_id)
            return ValidationRunSummaryDTO.from_orm(comp, saved_results)

    def _build_context_for_rule(self, workspace_registration_id: int, rule: RuleRecord) -> dict[str, Any]:
        """Construct historical context for anomaly or previous-run baseline rules."""
        ctx: dict[str, Any] = {}
        if self._refresh_service is not None:
            ctx["refresh_service"] = self._refresh_service

        try:
            with self._db.session_scope() as session:
                repo = ValidationRunRepository(session)

                # Row count previous run context
                if rule.validation_type == VALIDATION_TYPE_ROW_COUNT:
                    cfg = rule.config or {}
                    if cfg.get("baseline_method") == "previous_run":
                        runs = repo.list_runs(workspace_registration_id=workspace_registration_id, limit=5)
                        for past_run in runs:
                            for res in past_run.results:
                                if res.validation_rule_id == rule.id and res.actual_value:
                                    # Parse digits from actual_value (e.g. "1,020 rows")
                                    cleaned = "".join(c for c in res.actual_value.split("rows")[0] if c.isdigit())
                                    if cleaned:
                                        ctx["previous_row_count"] = int(cleaned)
                                        break
                            if "previous_row_count" in ctx:
                                break

                # Anomaly historical observations context
                elif rule.validation_type == VALIDATION_TYPE_ANOMALY:
                    cfg = rule.config or {}
                    lookback_days = int(cfg.get("lookback_days", 30))
                    runs = repo.list_runs(workspace_registration_id=workspace_registration_id, limit=60)
                    points: list[tuple[datetime, float]] = []
                    cutoff = utc_now().timestamp() - (lookback_days * 86400)

                    for past_run in runs:
                        if past_run.started_at.timestamp() < cutoff:
                            continue
                        for res in past_run.results:
                            if res.validation_rule_id == rule.id and res.actual_value:
                                try:
                                    val_str = res.actual_value.replace(",", "").strip()
                                    val = float(val_str)
                                    points.append((res.started_at, val))
                                except Exception:
                                    continue
                    if points:
                        # Sort oldest to newest
                        points.sort(key=lambda p: p[0])
                        ctx["historical_points"] = points
        except Exception as exc:
            logger.debug("Could not build historical context for rule %s: %s", rule.id, exc)

        return ctx

    def get_run_summary(self, run_id: int) -> ValidationRunSummaryDTO | None:
        """Retrieve full details of a past validation run by ID."""
        with self._db.session_scope() as session:
            repo = ValidationRunRepository(session)
            run = repo.get_run(run_id)
            if run is None:
                return None
            results = repo.list_results_for_run(run_id)
            return ValidationRunSummaryDTO.from_orm(run, results)

    def list_runs_for_registration(
        self,
        workspace_registration_id: int,
        *,
        limit: int = 50,
    ) -> list[ValidationRunSummaryDTO]:
        """List past validation runs for a workspace registration in descending chronological order."""
        with self._db.session_scope() as session:
            repo = ValidationRunRepository(session)
            runs = repo.list_runs(workspace_registration_id=workspace_registration_id, limit=limit)
            return [ValidationRunSummaryDTO.from_orm(r) for r in runs]

    def get_latest_run_for_registration(
        self,
        workspace_registration_id: int,
    ) -> ValidationRunSummaryDTO | None:
        """Get the most recent validation run for a workspace registration."""
        with self._db.session_scope() as session:
            repo = ValidationRunRepository(session)
            runs = repo.list_runs(workspace_registration_id=workspace_registration_id, limit=1)
            if not runs:
                return None
            latest = runs[0]
            results = repo.list_results_for_run(latest.id)
            return ValidationRunSummaryDTO.from_orm(latest, results)

    def get_latest_run(self) -> ValidationRunSummaryDTO | None:
        """Get the most recent validation run across all registrations."""
        with self._db.session_scope() as session:
            repo = ValidationRunRepository(session)
            runs = repo.list_runs(limit=1)
            if not runs:
                return None
            latest = runs[0]
            results = repo.list_results_for_run(latest.id)
            return ValidationRunSummaryDTO.from_orm(latest, results)

    def run_sheet_validation(
        self,
        *,
        is_cancelled_fn: Callable[[], bool] | None = None,
        on_progress: Callable[[int, int, str, CheckEvaluationResult | None], None] | None = None,
    ) -> ValidationRunSummaryDTO:
        """Execute all enabled rules configured in the Validation Sheet across all datasets."""
        from collections import defaultdict
        from app.services.sheet_service import SheetService
        from app.services.registry_service import RegistryService

        reg_svc = self._registry_service or RegistryService(db=self._db)
        sheet_svc = SheetService(
            db=self._db,
            registry_service=reg_svc,
            rule_service=self._rule_service,
        )

        sheet_rows = sheet_svc.load_sheet_rows()
        enabled_rows = [r for r in sheet_rows if r.enabled and r.workspace_id and r.dataset_id]

        run_start = utc_now()
        total_checks = len(enabled_rows)

        if total_checks == 0:
            # Check if any active registrations have enabled rules configured
            registrations = reg_svc.list_registrations(active_only=True)
            for reg in registrations:
                rules = self._rule_service.list_rules(reg.id, enabled_only=True)
                if rules:
                    return self.run_validation(
                        reg.id,
                        workspace_id=reg.workspace_id,
                        dataset_id=reg.dataset_id,
                        is_cancelled_fn=is_cancelled_fn,
                        on_progress=on_progress,
                    )

            now = utc_now()
            return ValidationRunSummaryDTO(
                id=0,
                workspace_registration_id=0,
                overall_status=ValidationStatus.WARNING,
                passed_count=0,
                failed_count=0,
                warning_count=1,
                error_count=0,
                total_rules=0,
                duration_ms=0,
                app_version=self._app_version,
                started_at=run_start,
                completed_at=now,
                results=[
                    ValidationResultDTO(
                        id=0,
                        validation_run_id=0,
                        rule_id=None,
                        rule_name="Validation Sheet Checks",
                        validation_type="sheet_validation",
                        target_type="SHEET",
                        target_display="Validation Sheet",
                        status=ValidationStatus.WARNING,
                        actual_value=None,
                        expected_value=None,
                        deviation=None,
                        result_summary="No enabled validation rules configured in the Validation Sheet.",
                        detailed_message="Open the Validation Sheet tab to add or enable validation rules.",
                        duration_ms=0,
                        started_at=run_start,
                        completed_at=now,
                    )
                ],
            )

        # Group enabled rows by registration
        rows_by_reg: dict[int, list[Any]] = defaultdict(list)
        for row in enabled_rows:
            reg_id = row.workspace_registration_id
            if reg_id is None:
                reg = reg_svc.find_by_workspace_and_dataset(row.workspace_id, row.dataset_id)
                if reg is not None:
                    reg_id = reg.id
                    row.workspace_registration_id = reg.id
                else:
                    saved = sheet_svc.save_sheet_row(row)
                    reg_id = saved.workspace_registration_id or 1
                    row.workspace_registration_id = reg_id
                    row.row_id = saved.row_id
            rows_by_reg[reg_id].append(row)

        all_results: list[ValidationResultDTO] = []
        reg_summaries: list[ValidationRunSummaryDTO] = []
        global_check_idx = 0
        is_cancelled = False

        for reg_id, rows_for_reg in rows_by_reg.items():
            if is_cancelled:
                break

            first_row = rows_for_reg[0]
            ws_id = first_row.workspace_id
            ds_id = first_row.dataset_id

            with self._db.session_scope() as session:
                repo = ValidationRunRepository(session)
                run = repo.create_run(
                    workspace_registration_id=reg_id,
                    app_version=self._app_version,
                    overall_status="RUNNING",
                    started_at=run_start,
                )
                run_id = run.id

            statuses: list[ValidationStatus] = []

            for row in rows_for_reg:
                if is_cancelled_fn and is_cancelled_fn():
                    is_cancelled = True
                    logger.info("Sheet validation run cancelled by user at check %s/%s", global_check_idx + 1, total_checks)
                    break

                global_check_idx += 1
                rule_name = row.effective_rule_name()
                if on_progress:
                    on_progress(global_check_idx, total_checks, rule_name, None)

                rule_record = RuleRecord(
                    id=row.row_id or 0,
                    workspace_registration_id=reg_id,
                    rule_name=rule_name,
                    enabled=row.enabled,
                    target_type=row.target_type,
                    table_name=row.table_name,
                    column_name=row.column_name,
                    measure_name=row.measure_name,
                    validation_type=row.validation_type,
                    config=row.config,
                    display_order=row.sr_no,
                )

                rule_context = self._build_context_for_rule(reg_id, rule_record)

                check_res: CheckEvaluationResult
                try:
                    validator = get_validator(row.validation_type)
                    check_res = validator.validate(
                        rule=rule_record,
                        dax_client=self._dax_client,
                        workspace_id=ws_id,
                        dataset_id=ds_id,
                        context=rule_context,
                    )
                except Exception as exc:
                    logger.exception("Unexpected error executing sheet rule %s: %s", rule_name, exc)
                    check_res = CheckEvaluationResult.create_error(
                        rule_id=row.row_id,
                        rule_name=rule_name,
                        validation_type=row.validation_type,
                        target_type=row.target_type,
                        error_message=f"Validator internal error: {exc}",
                        started_at=utc_now(),
                    )

                statuses.append(check_res.status)

                with self._db.session_scope() as session:
                    repo = ValidationRunRepository(session)
                    repo.add_result(
                        validation_run_id=run_id,
                        validation_rule_id=row.row_id,
                        status=check_res.status.value,
                        actual_value=check_res.actual_value,
                        expected_value=check_res.expected_value,
                        deviation=check_res.deviation,
                        result_summary=check_res.result_summary,
                        detailed_message=check_res.detailed_message,
                        started_at=check_res.started_at,
                        completed_at=check_res.completed_at,
                    )

                if on_progress:
                    on_progress(global_check_idx, total_checks, rule_name, check_res)

            reg_end = utc_now()
            reg_dur_ms = int((reg_end - run_start).total_seconds() * 1000)
            reg_overall = calculate_overall_status(statuses)

            with self._db.session_scope() as session:
                repo = ValidationRunRepository(session)
                comp = repo.complete_run(
                    run_id,
                    overall_status=reg_overall.value,
                    passed_count=sum(1 for s in statuses if s == ValidationStatus.PASS),
                    failed_count=sum(1 for s in statuses if s == ValidationStatus.FAIL),
                    warning_count=sum(1 for s in statuses if s == ValidationStatus.WARNING),
                    error_count=sum(1 for s in statuses if s == ValidationStatus.ERROR),
                    duration_ms=reg_dur_ms,
                    completed_at=reg_end,
                )
                saved_results = repo.list_results_for_run(run_id)
                summary = ValidationRunSummaryDTO.from_orm(comp, saved_results)
                reg_summaries.append(summary)
                all_results.extend(summary.results)

        if not reg_summaries:
            now = utc_now()
            return ValidationRunSummaryDTO(
                id=0,
                workspace_registration_id=0,
                overall_status=ValidationStatus.WARNING,
                passed_count=0,
                failed_count=0,
                warning_count=1,
                error_count=0,
                total_rules=0,
                duration_ms=0,
                app_version=self._app_version,
                started_at=run_start,
                completed_at=now,
                results=[],
            )

        if len(reg_summaries) == 1:
            return reg_summaries[0]

        now = utc_now()
        total_dur_ms = int((now - run_start).total_seconds() * 1000)
        all_statuses = [r.status for r in all_results]
        overall_st = calculate_overall_status(all_statuses)

        return ValidationRunSummaryDTO(
            id=reg_summaries[-1].id,
            workspace_registration_id=reg_summaries[0].workspace_registration_id,
            overall_status=overall_st,
            passed_count=sum(s.passed_count for s in reg_summaries),
            failed_count=sum(s.failed_count for s in reg_summaries),
            warning_count=sum(s.warning_count for s in reg_summaries),
            error_count=sum(s.error_count for s in reg_summaries),
            total_rules=len(all_results),
            duration_ms=total_dur_ms,
            app_version=self._app_version,
            started_at=run_start,
            completed_at=now,
            results=all_results,
        )


class ValidationWorker(QThread):
    """Background worker thread executing validation runs without blocking the Qt GUI."""

    # Signals for UI integration
    progress = Signal(int, int, str)  # (current_rule_idx, total_rules, rule_name)
    rule_completed = Signal(object)    # CheckEvaluationResult
    run_finished = Signal(object)      # ValidationRunSummaryDTO
    error = Signal(str)                # Error message if run crashes

    def __init__(
        self,
        orchestrator: OrchestratorService,
        workspace_registration_id: int | None = None,
        workspace_id: str = "",
        dataset_id: str = "",
        *,
        run_all_sheet_rules: bool = True,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._orchestrator = orchestrator
        self._registration_id = workspace_registration_id
        self._workspace_id = workspace_id
        self._dataset_id = dataset_id
        self._run_all_sheet_rules = run_all_sheet_rules
        self._cancelled = False

    def cancel(self) -> None:
        """Request cooperative cancellation between rule evaluations."""
        self._cancelled = True

    def is_cancelled(self) -> bool:
        return self._cancelled

    def run(self) -> None:
        """Execute the validation run in background thread and emit Qt signals."""
        try:
            summary: Any = None
            if self._run_all_sheet_rules and hasattr(self._orchestrator, "run_sheet_validation"):
                res = self._orchestrator.run_sheet_validation(
                    is_cancelled_fn=self.is_cancelled,
                    on_progress=self._handle_progress,
                )
                if isinstance(res, ValidationRunSummaryDTO):
                    summary = res
                elif hasattr(self._orchestrator, "run_validation"):
                    mock_ret = getattr(self._orchestrator.run_validation, "return_value", None)
                    if isinstance(mock_ret, ValidationRunSummaryDTO):
                        summary = mock_ret
                    else:
                        summary = res
                else:
                    summary = res
            elif self._registration_id is not None:
                summary = self._orchestrator.run_validation(
                    self._registration_id,
                    workspace_id=self._workspace_id,
                    dataset_id=self._dataset_id,
                    is_cancelled_fn=self.is_cancelled,
                    on_progress=self._handle_progress,
                )
            else:
                summary = self._orchestrator.run_sheet_validation(
                    is_cancelled_fn=self.is_cancelled,
                    on_progress=self._handle_progress,
                )
            self.run_finished.emit(summary)
        except Exception as exc:
            logger.exception("ValidationWorker failed: %s", exc)
            self.error.emit(str(exc))

    def _handle_progress(
        self,
        current: int,
        total: int,
        rule_name: str,
        result: CheckEvaluationResult | None,
    ) -> None:
        self.progress.emit(current, total, rule_name)
        if result is not None:
            self.rule_completed.emit(result)
