"""Application service for running DAX queries asynchronously in background QThreads (Stage 9)."""

from __future__ import annotations

import logging
from typing import Callable

from PySide6.QtCore import QObject, QThread, Signal

from app.integrations.powerbi.dax_client import DaxQueryClient, DaxQueryResult

logger = logging.getLogger(__name__)


class _DaxWorker(QThread):
    """Background worker executing DAX queries without stalling the GUI."""

    finished_result = Signal(object)  # DaxQueryResult
    failed = Signal(str)  # error message

    def __init__(
        self,
        client: DaxQueryClient,
        workspace_id: str,
        dataset_id: str,
        query: str,
        timeout_seconds: int = 30,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._client = client
        self._workspace_id = workspace_id
        self._dataset_id = dataset_id
        self._query = query
        self._timeout = timeout_seconds

    def run(self) -> None:
        try:
            res = self._client.execute_raw_dax(
                workspace_id=self._workspace_id,
                dataset_id=self._dataset_id,
                query=self._query,
                timeout_seconds=self._timeout,
            )
            self.finished_result.emit(res)
        except Exception as exc:
            logger.error("DaxWorker failed: %s", exc, exc_info=True)
            self.failed.emit(str(exc))


class DaxQueryService(QObject):
    """Service providing asynchronous DAX query execution for measures and test probes."""

    query_completed = Signal(object)  # DaxQueryResult
    query_failed = Signal(str)  # error_message
    busy_changed = Signal(bool)

    def __init__(
        self,
        dax_client: DaxQueryClient,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._client = dax_client
        self._workers: list[_DaxWorker] = []

    @property
    def client(self) -> DaxQueryClient:
        return self._client

    def execute_measure_async(
        self,
        *,
        workspace_id: str,
        dataset_id: str,
        measure_name: str,
        filter_context: str | None = None,
        timeout_seconds: int = 30,
        on_complete: Callable[[DaxQueryResult], None] | None = None,
    ) -> None:
        """Asynchronously query a measure and dispatch results to callback / signals."""
        from app.integrations.powerbi.dax_client import build_measure_query

        query = build_measure_query(measure_name, filter_context)
        self.execute_query_async(
            workspace_id=workspace_id,
            dataset_id=dataset_id,
            query=query,
            timeout_seconds=timeout_seconds,
            on_complete=on_complete,
        )

    def test_connection_async(
        self,
        *,
        workspace_id: str,
        dataset_id: str,
        timeout_seconds: int = 15,
        on_complete: Callable[[DaxQueryResult], None] | None = None,
    ) -> None:
        """Asynchronously test Execute Queries eligibility for a dataset."""
        from app.integrations.powerbi.dax_client import build_test_query

        self.execute_query_async(
            workspace_id=workspace_id,
            dataset_id=dataset_id,
            query=build_test_query(),
            timeout_seconds=timeout_seconds,
            on_complete=on_complete,
        )

    def execute_query_async(
        self,
        *,
        workspace_id: str,
        dataset_id: str,
        query: str,
        timeout_seconds: int = 30,
        on_complete: Callable[[DaxQueryResult], None] | None = None,
    ) -> None:
        """Run any DAX query in a background worker."""
        worker = _DaxWorker(
            client=self._client,
            workspace_id=workspace_id,
            dataset_id=dataset_id,
            query=query,
            timeout_seconds=timeout_seconds,
            parent=self,
        )
        self._workers.append(worker)

        def _on_done(res: DaxQueryResult) -> None:
            self.busy_changed.emit(False)
            self.query_completed.emit(res)
            if on_complete is not None:
                on_complete(res)
            if worker in self._workers:
                self._workers.remove(worker)

        def _on_failed(err_msg: str) -> None:
            self.busy_changed.emit(False)
            self.query_failed.emit(err_msg)
            if worker in self._workers:
                self._workers.remove(worker)

        worker.finished_result.connect(_on_done)
        worker.failed.connect(_on_failed)
        self.busy_changed.emit(True)
        worker.start()

    def shutdown(self) -> None:
        """Terminate all background query workers cleanly."""
        for worker in list(self._workers):
            if worker.isRunning():
                worker.quit()
                worker.wait(1500)
        self._workers.clear()
