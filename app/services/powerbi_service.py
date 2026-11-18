"""Qt-friendly Power BI connectivity service executing REST API calls off the UI thread."""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

from PySide6.QtCore import QObject, QThread, Signal

from app.core.exceptions import format_safe_user_error
from app.integrations.powerbi.dataset_client import DatasetClient
from app.integrations.powerbi.models import (
    AccessVerificationResult,
    PowerBIDataset,
    PowerBIReport,
    PowerBIWorkspace,
)
from app.integrations.powerbi.rest_client import PowerBIRestClient
from app.integrations.powerbi.workspace_client import WorkspaceClient
from app.services.auth_service import AuthService

logger = logging.getLogger(__name__)


class _PbiWorker(QThread):
    """Background worker executing Power BI REST API calls without blocking Qt UI."""

    completed = Signal(object)
    failed = Signal(str)

    def __init__(self, action: Callable[[], Any], parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._action = action

    def run(self) -> None:
        try:
            payload = self._action()
            self.completed.emit(payload)
        except Exception as exc:
            safe_msg = format_safe_user_error(exc)
            logger.warning("Power BI service operation failed: %s", safe_msg)
            self.failed.emit(safe_msg)


class PowerBIService(QObject):
    """High-level application service for Power BI connectivity and permission verification."""

    workspaces_loaded = Signal(list)
    workspace_assets_loaded = Signal(str, list, list)
    access_verified = Signal(object)
    error_occurred = Signal(str)
    busy_changed = Signal(bool)

    def __init__(
        self,
        *,
        auth_service: AuthService,
        rest_client: PowerBIRestClient | None = None,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._auth_service = auth_service
        self._rest_client = rest_client or PowerBIRestClient(
            token_provider=auth_service.get_access_token
        )
        self._workspace_client = WorkspaceClient(self._rest_client)
        self._dataset_client = DatasetClient(self._rest_client, self._workspace_client)
        self._active_worker: _PbiWorker | None = None
        self._cached_workspaces: list[PowerBIWorkspace] = []
        self._cached_datasets: dict[str, list[PowerBIDataset]] = {}
        self._cached_reports: dict[str, list[PowerBIReport]] = {}

    @property
    def rest_client(self) -> PowerBIRestClient:
        return self._rest_client

    @property
    def workspace_client(self) -> WorkspaceClient:
        return self._workspace_client

    @property
    def dataset_client(self) -> DatasetClient:
        return self._dataset_client

    @property
    def cached_workspaces(self) -> list[PowerBIWorkspace]:
        return list(self._cached_workspaces)

    def get_cached_datasets(self, workspace_id: str) -> list[PowerBIDataset]:
        return list(self._cached_datasets.get(workspace_id.lower(), []))

    def get_cached_reports(self, workspace_id: str) -> list[PowerBIReport]:
        return list(self._cached_reports.get(workspace_id.lower(), []))

    def list_workspaces_sync(self) -> list[PowerBIWorkspace]:
        """Fetch or return cached workspaces synchronously."""
        if not self._cached_workspaces:
            workspaces = self._workspace_client.list_workspaces()
            self._cached_workspaces = list(workspaces)
        return list(self._cached_workspaces)

    def list_workspace_assets_sync(
        self, workspace_id: str
    ) -> tuple[list[PowerBIDataset], list[PowerBIReport]]:
        """Fetch or return cached datasets and reports for a workspace synchronously."""
        key = workspace_id.lower()
        if key not in self._cached_datasets or key not in self._cached_reports:
            datasets = self._dataset_client.list_datasets(workspace_id)
            reports = self._workspace_client.list_reports(workspace_id)
            self._cached_datasets[key] = list(datasets)
            self._cached_reports[key] = list(reports)
        return (
            list(self._cached_datasets.get(key, [])),
            list(self._cached_reports.get(key, [])),
        )

    @property
    def is_busy(self) -> bool:
        return self._active_worker is not None and self._active_worker.isRunning()

    def list_workspaces_async(self) -> None:
        """Fetch accessible Power BI workspaces in the background."""
        self._start_worker(
            self._workspace_client.list_workspaces,
            on_success=self._emit_workspaces,
        )

    def list_workspace_assets_async(self, workspace_id: str) -> None:
        """Fetch datasets and reports inside a workspace in the background."""

        def _fetch() -> tuple[str, list[PowerBIDataset], list[PowerBIReport]]:
            datasets = self._dataset_client.list_datasets(workspace_id)
            reports = self._workspace_client.list_reports(workspace_id)
            return workspace_id, datasets, reports

        self._start_worker(_fetch, on_success=self._emit_workspace_assets)

    def verify_access_async(
        self,
        *,
        workspace_id: str,
        dataset_id: str,
        report_id: str | None = None,
    ) -> None:
        """Verify workspace, dataset, and optional report permissions off the UI thread."""
        acct = self._auth_service.state.account
        signed_in_email = acct.username if acct is not None else None

        def _verify() -> AccessVerificationResult:
            return self._dataset_client.verify_access(
                workspace_id=workspace_id,
                dataset_id=dataset_id,
                report_id=report_id,
                signed_in_email=signed_in_email,
            )

        self._start_worker(_verify, on_success=self._emit_access_verified)

    def _emit_workspaces(self, workspaces: list[PowerBIWorkspace]) -> None:
        self._cached_workspaces = list(workspaces)
        self.workspaces_loaded.emit(workspaces)

    def _emit_workspace_assets(
        self,
        payload: tuple[str, list[PowerBIDataset], list[PowerBIReport]],
    ) -> None:
        ws_id, datasets, reports = payload
        self._cached_datasets[ws_id.lower()] = list(datasets)
        self._cached_reports[ws_id.lower()] = list(reports)
        self.workspace_assets_loaded.emit(ws_id, datasets, reports)

    def _emit_access_verified(self, result: AccessVerificationResult) -> None:
        self.access_verified.emit(result)

    def _start_worker(
        self,
        action: Callable[[], Any],
        *,
        on_success: Callable[[Any], None],
    ) -> None:
        if self.is_busy:
            logger.debug("Power BI operation already running; ignoring duplicate request.")
            return

        self.busy_changed.emit(True)
        worker = _PbiWorker(action, parent=self)
        worker.completed.connect(on_success)
        worker.failed.connect(self.error_occurred.emit)
        worker.finished.connect(self._cleanup_worker)
        self._active_worker = worker
        worker.start()

    def _cleanup_worker(self) -> None:
        if self._active_worker is not None:
            self._active_worker.deleteLater()
            self._active_worker = None
        self.busy_changed.emit(False)

    def shutdown(self) -> None:
        """Wait briefly for in-flight requests and close the HTTP client cleanly."""
        if self._active_worker is not None and self._active_worker.isRunning():
            self._active_worker.quit()
            self._active_worker.wait(1000)
        self._rest_client.close()
