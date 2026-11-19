"""Service managing dataset refresh history retrieval, persistence, and rule evaluation (Stage 8)."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable

from PySide6.QtCore import QObject, QThread, Signal

from app.core.status import RefreshStatus, ValidationStatus
from app.database.db import DatabaseManager
from app.database.models import RefreshRecord, utc_now
from app.database.repositories import RefreshRecordRepository
from app.integrations.powerbi.refresh_client import RefreshClient

logger = logging.getLogger(__name__)


def format_duration(duration_ms: int | None) -> str:
    """Format duration in milliseconds into a concise readable string."""
    if duration_ms is None:
        return "— (In Progress)"

    total_seconds = int(duration_ms / 1000)
    hours, remainder = divmod(total_seconds, 3600)
    minutes, seconds = divmod(remainder, 60)

    if hours > 0:
        return f"{hours}h {minutes}m {seconds}s"
    if minutes > 0:
        return f"{minutes}m {seconds}s"
    return f"{seconds}s"


@dataclass(frozen=True, slots=True)
class RefreshRecordDTO:
    """Detached immutable representation of one Power BI dataset refresh record."""

    id: int
    workspace_registration_id: int
    dataset_id: str
    refresh_id: str | None
    status: RefreshStatus
    start_time: datetime | None
    end_time: datetime | None
    duration_ms: int | None
    refresh_type: str | None
    error_details: str | None
    retrieved_at: datetime

    @property
    def duration_display(self) -> str:
        return format_duration(self.duration_ms)

    @property
    def start_time_display(self) -> str:
        if self.start_time is None:
            return "—"
        return self.start_time.strftime("%Y-%m-%d %H:%M:%S UTC")

    @property
    def end_time_display(self) -> str:
        if self.end_time is None:
            return "—"
        return self.end_time.strftime("%Y-%m-%d %H:%M:%S UTC")

    @property
    def age_hours(self) -> float | None:
        ref_time = self.end_time or self.start_time
        if ref_time is None:
            return None
        if ref_time.tzinfo is None:
            ref_time = ref_time.replace(tzinfo=timezone.utc)
        now = datetime.now(timezone.utc)
        diff = (now - ref_time).total_seconds()
        return round(max(0.0, diff / 3600.0), 1)

    @classmethod
    def from_orm(cls, model: RefreshRecord) -> RefreshRecordDTO:
        try:
            status_enum = RefreshStatus(model.status)
        except Exception:
            status_enum = RefreshStatus.UNKNOWN

        return cls(
            id=model.id,
            workspace_registration_id=model.workspace_registration_id,
            dataset_id=model.dataset_id,
            refresh_id=model.refresh_id,
            status=status_enum,
            start_time=model.start_time,
            end_time=model.end_time,
            duration_ms=model.duration_ms,
            refresh_type=model.refresh_type,
            error_details=model.error_details,
            retrieved_at=model.retrieved_at,
        )


@dataclass(frozen=True, slots=True)
class RefreshSummaryDTO:
    """Aggregate summary statistics for dataset refresh operations (BRD Section 7)."""

    workspace_registration_id: int
    latest_attempt: RefreshRecordDTO | None
    latest_successful: RefreshRecordDTO | None
    latest_completed: RefreshRecordDTO | None
    total_runs: int
    success_count: int
    failure_count: int
    in_progress_count: int

    @property
    def success_rate_pct(self) -> float | None:
        if self.total_runs == 0:
            return None
        return round((self.success_count / self.total_runs) * 100.0, 1)

    @property
    def success_rate_display(self) -> str:
        if self.total_runs == 0 or self.success_rate_pct is None:
            return "No History"
        return f"{self.success_rate_pct}% ({self.success_count}/{self.total_runs})"


@dataclass(frozen=True, slots=True)
class RefreshCheckEvaluation:
    """Outcome of evaluating a Refresh Check validation rule (BRD 5.3 G, Stage 8 Task 10)."""

    status: ValidationStatus
    actual_value: str
    expected_value: str
    deviation: str | None
    result_summary: str
    detailed_message: str | None
    refresh_record: RefreshRecordDTO | None = None


class _RefreshWorker(QThread):
    """Background worker fetching refresh history from Power BI REST API."""

    finished_records = Signal(int, list)  # reg_id, list[RefreshRecordDTO]
    failed = Signal(int, str)  # reg_id, error_message

    def __init__(
        self,
        service: RefreshService,
        reg_id: int,
        workspace_id: str,
        dataset_id: str,
        top: int,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._service = service
        self._reg_id = reg_id
        self._ws_id = workspace_id
        self._ds_id = dataset_id
        self._top = top

    def run(self) -> None:
        try:
            records = self._service.fetch_and_persist_refreshes(
                workspace_registration_id=self._reg_id,
                workspace_id=self._ws_id,
                dataset_id=self._ds_id,
                top=self._top,
            )
            self.finished_records.emit(self._reg_id, records)
        except Exception as exc:
            logger.error("Refresh fetch failed for reg %s: %s", self._reg_id, exc, exc_info=True)
            self.failed.emit(self._reg_id, str(exc))


class RefreshService(QObject):
    """Coordinates refresh history fetching, persistence in SQLite, and rule evaluation."""

    refresh_loaded = Signal(int, list)  # reg_id, list[RefreshRecordDTO]
    refresh_failed = Signal(int, str)  # reg_id, error_message
    busy_changed = Signal(bool)

    def __init__(
        self,
        *,
        db: DatabaseManager,
        refresh_client: RefreshClient,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._db = db
        self._client = refresh_client
        self._workers: list[_RefreshWorker] = []

    def fetch_and_persist_refreshes(
        self,
        *,
        workspace_registration_id: int,
        workspace_id: str,
        dataset_id: str,
        top: int = 15,
    ) -> list[RefreshRecordDTO]:
        """Fetch live refreshes from Power BI API and upsert into SQLite."""
        parsed_items = self._client.list_refreshes(workspace_id, dataset_id, top=top)

        with self._db.session_scope() as session:
            repo = RefreshRecordRepository(session)
            # Fetch existing records for this registration
            existing = repo.list_for_registration(workspace_registration_id, limit=top * 2)
            existing_by_ref_id = {r.refresh_id: r for r in existing if r.refresh_id}

            persisted_models: list[RefreshRecord] = []

            for p in parsed_items:
                # If already exists by refresh_id, update it (e.g. In Progress -> Completed)
                if p.refresh_id and p.refresh_id in existing_by_ref_id:
                    rec = existing_by_ref_id[p.refresh_id]
                    rec.status = p.status.value
                    rec.start_time = p.start_time
                    rec.end_time = p.end_time
                    rec.duration_ms = p.duration_ms
                    rec.refresh_type = p.refresh_type
                    rec.error_details = p.error_details
                    rec.retrieved_at = utc_now()
                    persisted_models.append(rec)
                else:
                    new_rec = repo.create(
                        workspace_registration_id=workspace_registration_id,
                        dataset_id=dataset_id,
                        refresh_id=p.refresh_id,
                        status=p.status.value,
                        start_time=p.start_time,
                        end_time=p.end_time,
                        duration_ms=p.duration_ms,
                        refresh_type=p.refresh_type,
                        error_details=p.error_details,
                        retrieved_at=utc_now(),
                    )
                    persisted_models.append(new_rec)

            session.flush()
            # Return ordered list
            all_records = repo.list_for_registration(workspace_registration_id, limit=top)
            return [RefreshRecordDTO.from_orm(r) for r in all_records]

    def list_history(
        self,
        workspace_registration_id: int,
        *,
        limit: int = 50,
    ) -> list[RefreshRecordDTO]:
        """Read persisted refresh records from SQLite."""
        with self._db.session_scope() as session:
            repo = RefreshRecordRepository(session)
            records = repo.list_for_registration(workspace_registration_id, limit=limit)
            return [RefreshRecordDTO.from_orm(r) for r in records]

    def get_latest_attempt(self, workspace_registration_id: int) -> RefreshRecordDTO | None:
        with self._db.session_scope() as session:
            repo = RefreshRecordRepository(session)
            record = repo.get_latest_attempt(workspace_registration_id)
            return RefreshRecordDTO.from_orm(record) if record is not None else None

    def get_latest_successful(self, workspace_registration_id: int) -> RefreshRecordDTO | None:
        with self._db.session_scope() as session:
            repo = RefreshRecordRepository(session)
            record = repo.get_latest_successful(workspace_registration_id)
            return RefreshRecordDTO.from_orm(record) if record is not None else None

    def get_latest_completed(self, workspace_registration_id: int) -> RefreshRecordDTO | None:
        with self._db.session_scope() as session:
            repo = RefreshRecordRepository(session)
            record = repo.get_latest_completed(workspace_registration_id)
            return RefreshRecordDTO.from_orm(record) if record is not None else None

    def get_refresh_summary(self, workspace_registration_id: int) -> RefreshSummaryDTO:
        """Calculate aggregate summary statistics for the specified dataset registration."""
        with self._db.session_scope() as session:
            repo = RefreshRecordRepository(session)
            records = repo.list_for_registration(workspace_registration_id, limit=100)
            dto_records = [RefreshRecordDTO.from_orm(r) for r in records]
            latest_attempt = dto_records[0] if dto_records else None
            latest_success = next((r for r in dto_records if r.status == RefreshStatus.SUCCESS), None)
            latest_completed = next((r for r in dto_records if r.end_time is not None), None)

            total = len(dto_records)
            successes = sum(1 for r in dto_records if r.status == RefreshStatus.SUCCESS)
            failures = sum(1 for r in dto_records if r.status == RefreshStatus.FAILED)
            in_progress = sum(1 for r in dto_records if r.status == RefreshStatus.IN_PROGRESS)

            return RefreshSummaryDTO(
                workspace_registration_id=workspace_registration_id,
                latest_attempt=latest_attempt,
                latest_successful=latest_success,
                latest_completed=latest_completed,
                total_runs=total,
                success_count=successes,
                failure_count=failures,
                in_progress_count=in_progress,
            )

    def fetch_refreshes_async(
        self,
        *,
        workspace_registration_id: int,
        workspace_id: str,
        dataset_id: str,
        top: int = 15,
    ) -> None:
        """Fetch refreshes in a background QThread to keep UI responsive."""
        worker = _RefreshWorker(
            service=self,
            reg_id=workspace_registration_id,
            workspace_id=workspace_id,
            dataset_id=dataset_id,
            top=top,
            parent=self,
        )
        self._workers.append(worker)

        def _on_done(reg_id: int, records: list) -> None:
            self.busy_changed.emit(False)
            self.refresh_loaded.emit(reg_id, records)
            if worker in self._workers:
                self._workers.remove(worker)

        def _on_failed(reg_id: int, err: str) -> None:
            self.busy_changed.emit(False)
            self.refresh_failed.emit(reg_id, err)
            if worker in self._workers:
                self._workers.remove(worker)

        worker.finished_records.connect(_on_done)
        worker.failed.connect(_on_failed)
        self.busy_changed.emit(True)
        worker.start()

    def evaluate_refresh_rule(
        self,
        workspace_registration_id: int,
        config: dict[str, Any],
    ) -> RefreshCheckEvaluation:
        """Evaluate a Power BI Refresh Check validation rule (BRD 5.3 G, Stage 8 Task 10)."""
        target_definition = str(config.get("definition") or "latest_attempt").strip().lower()
        if target_definition in ("latest_success", "success"):
            target_record = self.get_latest_successful(workspace_registration_id)
            target_label = "Latest Successful Refresh"
        elif target_definition in ("latest_completed", "completed"):
            target_record = self.get_latest_completed(workspace_registration_id)
            target_label = "Latest Completed Refresh"
        else:
            target_record = self.get_latest_attempt(workspace_registration_id)
            target_label = "Latest Refresh Attempt"

        expected_status = str(config.get("expected_status") or "Completed").strip()
        # Canonical comparison: 'Completed' matches 'Success'
        norm_expected = "success" if expected_status.lower() in ("completed", "success") else expected_status.lower()

        max_age_hours = config.get("max_age_hours")
        max_duration_min = config.get("max_duration_minutes")

        expected_parts = [f"Status = {expected_status}"]
        if max_age_hours is not None:
            expected_parts.append(f"Age <= {max_age_hours}h")
        if max_duration_min is not None:
            expected_parts.append(f"Duration <= {max_duration_min}m")
        expected_str = ", ".join(expected_parts)

        if target_record is None:
            return RefreshCheckEvaluation(
                status=ValidationStatus.WARNING,
                actual_value="No refresh history",
                expected_value=expected_str,
                deviation=None,
                result_summary="No refresh history found for this dataset.",
                detailed_message="Please run 'Fetch Refresh History' to retrieve observed refresh records.",
                refresh_record=None,
            )

        actual_status = target_record.status.value
        actual_parts = [f"Status: {actual_status}"]
        if target_record.duration_ms is not None:
            actual_parts.append(f"Duration: {target_record.duration_display}")
        if target_record.age_hours is not None:
            actual_parts.append(f"Age: {target_record.age_hours}h ago")
        actual_str = ", ".join(actual_parts)

        # 1. Check Failure status
        if target_record.status == RefreshStatus.FAILED:
            err_msg = target_record.error_details or "Power BI reported refresh failure."
            return RefreshCheckEvaluation(
                status=ValidationStatus.FAIL,
                actual_value=actual_str,
                expected_value=expected_str,
                deviation=f"Status mismatch: {actual_status}",
                result_summary=f"Latest refresh failed: {err_msg}",
                detailed_message=f"Start Time: {target_record.start_time_display}\nEnd Time: {target_record.end_time_display}\nError: {err_msg}",
                refresh_record=target_record,
            )

        # 2. Check In Progress status
        if target_record.status == RefreshStatus.IN_PROGRESS:
            return RefreshCheckEvaluation(
                status=ValidationStatus.WARNING,
                actual_value=actual_str,
                expected_value=expected_str,
                deviation="Refresh currently in progress",
                result_summary="A refresh is currently in progress on Power BI Service.",
                detailed_message=f"Started at: {target_record.start_time_display}",
                refresh_record=target_record,
            )

        # 3. Check Status mismatch
        if norm_expected != "any" and target_record.status.value.lower() != norm_expected:
            return RefreshCheckEvaluation(
                status=ValidationStatus.FAIL,
                actual_value=actual_str,
                expected_value=expected_str,
                deviation=f"Expected {expected_status}, got {actual_status}",
                result_summary=f"Refresh status is {actual_status} (expected {expected_status}).",
                detailed_message=None,
                refresh_record=target_record,
            )

        # 4. Check Age threshold
        if max_age_hours is not None and target_record.age_hours is not None:
            if target_record.age_hours > float(max_age_hours):
                diff = round(target_record.age_hours - float(max_age_hours), 1)
                return RefreshCheckEvaluation(
                    status=ValidationStatus.FAIL,
                    actual_value=actual_str,
                    expected_value=expected_str,
                    deviation=f"+{diff}h older than threshold",
                    result_summary=f"Refresh is stale ({target_record.age_hours}h old, exceeding {max_age_hours}h limit).",
                    detailed_message=f"Last completed: {target_record.end_time_display}",
                    refresh_record=target_record,
                )

        # 5. Check Duration threshold
        if max_duration_min is not None and target_record.duration_ms is not None:
            duration_min = target_record.duration_ms / 60000.0
            if duration_min > float(max_duration_min):
                diff = round(duration_min - float(max_duration_min), 1)
                return RefreshCheckEvaluation(
                    status=ValidationStatus.FAIL,
                    actual_value=actual_str,
                    expected_value=expected_str,
                    deviation=f"+{diff}m over duration limit",
                    result_summary=f"Refresh duration ({target_record.duration_display}) exceeded {max_duration_min}m limit.",
                    detailed_message=f"Duration was {target_record.duration_display}.",
                    refresh_record=target_record,
                )

        # All checks passed!
        return RefreshCheckEvaluation(
            status=ValidationStatus.PASS,
            actual_value=actual_str,
            expected_value=expected_str,
            deviation=None,
            result_summary=f"Refresh completed successfully ({target_record.duration_display}, {target_record.age_hours}h ago).",
            detailed_message=f"Refresh ID: {target_record.refresh_id or '—'}\nStart: {target_record.start_time_display}\nEnd: {target_record.end_time_display}",
            refresh_record=target_record,
        )

    def shutdown(self) -> None:
        """Wait for any active background workers to finish."""
        for worker in list(self._workers):
            if worker.isRunning():
                worker.quit()
                worker.wait(2000)
        self._workers.clear()
