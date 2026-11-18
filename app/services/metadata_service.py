"""Service layer managing asynchronous Power BI semantic model metadata discovery.

Executes metadata discovery in background QThreads so network operations never
freeze the PySide6 UI, provides in-memory caching per dataset, and validates
target objects before rules are saved.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from PySide6.QtCore import QObject, QThread, Signal

from app.core.exceptions import format_safe_user_error
from app.integrations.powerbi.models import DatasetMetadata
from app.integrations.powerbi.workspace_client import MY_WORKSPACE_ID

if TYPE_CHECKING:
    from app.integrations.powerbi.metadata_client import MetadataClient

logger = logging.getLogger(__name__)


class _MetadataWorker(QThread):
    """Background worker for querying semantic model metadata off the Qt UI thread."""

    completed = Signal(object)  # DatasetMetadata
    failed = Signal(str, str)  # dataset_id, user_error_message

    def __init__(
        self,
        client: MetadataClient,
        dataset_id: str,
        workspace_id: str,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._client = client
        self._dataset_id = dataset_id
        self._workspace_id = workspace_id

    def run(self) -> None:
        try:
            metadata = self._client.discover_metadata(
                dataset_id=self._dataset_id,
                workspace_id=self._workspace_id,
            )
            self.completed.emit(metadata)
        except Exception as exc:
            user_msg = format_safe_user_error(exc)
            logger.warning(
                "Metadata discovery worker error for %s in %s: %s",
                self._dataset_id,
                self._workspace_id,
                user_msg,
            )
            self.failed.emit(self._dataset_id, user_msg)


class MetadataService(QObject):
    """Bridges Power BI metadata discovery client with PySide6 UI components."""

    metadata_loaded = Signal(object)  # DatasetMetadata
    metadata_failed = Signal(str, str)  # dataset_id, user_error_message
    busy_changed = Signal(bool)

    def __init__(
        self,
        metadata_client: MetadataClient,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._client = metadata_client
        self._cache: dict[tuple[str, str], DatasetMetadata] = {}
        self._active_worker: _MetadataWorker | None = None

    @property
    def is_busy(self) -> bool:
        return self._active_worker is not None and self._active_worker.isRunning()

    def get_cached_metadata(
        self,
        workspace_id: str,
        dataset_id: str,
    ) -> DatasetMetadata | None:
        """Return previously fetched metadata from memory if available."""
        key = (workspace_id.strip().lower() or MY_WORKSPACE_ID, dataset_id.strip())
        return self._cache.get(key)

    def fetch_metadata_async(
        self,
        workspace_id: str,
        dataset_id: str,
        *,
        force_refresh: bool = False,
    ) -> None:
        """Fetch metadata off the UI thread, or emit immediately if cached."""
        clean_ws = workspace_id.strip() or MY_WORKSPACE_ID
        clean_ds = dataset_id.strip()
        key = (clean_ws.lower(), clean_ds)

        if not clean_ds:
            self.metadata_failed.emit(clean_ds, "A valid Dataset ID is required to discover metadata.")
            return

        if not force_refresh and key in self._cache:
            logger.debug("Serving semantic model metadata from cache for %s", key)
            self.metadata_loaded.emit(self._cache[key])
            return

        if self.is_busy:
            logger.debug("Metadata discovery already in progress; skipping duplicate trigger.")
            return

        self.busy_changed.emit(True)
        worker = _MetadataWorker(
            client=self._client,
            dataset_id=clean_ds,
            workspace_id=clean_ws,
            parent=self,
        )
        worker.completed.connect(self._on_worker_completed)
        worker.failed.connect(self._on_worker_failed)
        worker.finished.connect(self._cleanup_worker)
        self._active_worker = worker
        worker.start()

    def _on_worker_completed(self, metadata: DatasetMetadata) -> None:
        key = (metadata.workspace_id.strip().lower() or MY_WORKSPACE_ID, metadata.dataset_id.strip())
        self._cache[key] = metadata
        self.metadata_loaded.emit(metadata)

    def _on_worker_failed(self, dataset_id: str, user_message: str) -> None:
        self.metadata_failed.emit(dataset_id, user_message)

    def _cleanup_worker(self) -> None:
        self.busy_changed.emit(False)
        if self._active_worker is not None:
            self._active_worker.deleteLater()
            self._active_worker = None

    def validate_object(
        self,
        workspace_id: str,
        dataset_id: str,
        target_type: str,
        table_name: str | None,
        column_or_measure: str | None,
    ) -> tuple[bool, str]:
        """Validate whether a table/column/measure exists in cached metadata."""
        meta = self.get_cached_metadata(workspace_id, dataset_id)
        if meta is None:
            return (
                True,
                "Model metadata not cached yet; manual entry will be verified during validation execution.",
            )
        return meta.validate_object(target_type, table_name, column_or_measure)

    def clear_cache(self) -> None:
        """Clear cached metadata entries (e.g. after schema change or sign-out)."""
        self._cache.clear()

    def shutdown(self) -> None:
        """Wait briefly for any in-flight background worker on application exit."""
        if self._active_worker is not None and self._active_worker.isRunning():
            self._active_worker.quit()
            self._active_worker.wait(1000)
