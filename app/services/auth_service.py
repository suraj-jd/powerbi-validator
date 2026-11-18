"""Qt-friendly authentication service running MSAL operations off the UI thread."""

from __future__ import annotations

import logging
from collections.abc import Callable
from pathlib import Path

from PySide6.QtCore import QObject, QThread, Signal

from app.auth.msal_auth import AuthConfig, AuthStateSnapshot, AuthStatus, MsalAuthClient
from app.core.config import AppConfig, save_config
from app.core.exceptions import format_safe_user_error

logger = logging.getLogger(__name__)


class _AuthWorker(QThread):
    """Background thread executing blocking MSAL calls without freezing Qt UI."""

    completed = Signal(object)
    failed = Signal(str)

    def __init__(self, action: Callable[[], AuthStateSnapshot], parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._action = action

    def run(self) -> None:
        try:
            snapshot = self._action()
            self.completed.emit(snapshot)
        except Exception as exc:
            logger.warning("Authentication operation failed: %s", format_safe_user_error(exc))
            self.failed.emit(format_safe_user_error(exc))


class AuthService(QObject):
    """Bridges `MsalAuthClient` with PySide6 widgets and persisted Entra app settings."""

    state_changed = Signal(object)
    error_occurred = Signal(str)

    def __init__(
        self,
        *,
        auth_client: MsalAuthClient,
        app_config: AppConfig,
        data_dir: Path,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._client = auth_client
        self._app_config = app_config
        self._data_dir = data_dir
        self._active_worker: _AuthWorker | None = None

    @property
    def client(self) -> MsalAuthClient:
        return self._client

    @property
    def state(self) -> AuthStateSnapshot:
        return self._client.state

    @property
    def is_busy(self) -> bool:
        return self._active_worker is not None and self._active_worker.isRunning()

    def configure_entra_app(self, client_id: str, tenant_id: str) -> AuthStateSnapshot:
        """Save non-secret Entra Client ID and Tenant ID and refresh auth state."""
        cleaned_client = client_id.strip()
        cleaned_tenant = tenant_id.strip() or "organizations"

        self._app_config.auth_client_id = cleaned_client
        self._app_config.auth_tenant_id = cleaned_tenant
        save_config(self._app_config, data_dir=self._data_dir)

        new_auth_config = AuthConfig(
            client_id=cleaned_client,
            tenant_id=cleaned_tenant,
            scopes=self._client.config.scopes,
        )
        snapshot = self._client.reconfigure(new_auth_config)
        self.state_changed.emit(snapshot)
        return snapshot

    def restore_session_async(self) -> None:
        """Attempt silent session restoration in the background on startup."""
        if not self._client.config.is_configured:
            self.state_changed.emit(self._client.state)
            return
        self._run_async(self._client.restore_session, busy_message="Checking saved Microsoft session...")

    def sign_in_async(self) -> None:
        """Launch interactive Microsoft browser sign-in off the UI thread."""
        self._run_async(
            lambda: self._client.sign_in_interactive(force_select_account=False),
            busy_message="Opening Microsoft sign-in in your browser...",
        )

    def switch_account_async(self) -> None:
        """Launch interactive Microsoft account picker off the UI thread."""
        self._run_async(
            self._client.switch_account,
            busy_message="Opening Microsoft account chooser in your browser...",
        )

    def sign_out(self) -> AuthStateSnapshot:
        """Clear local DPAPI token cache and sign out synchronously."""
        snapshot = self._client.sign_out()
        self.state_changed.emit(snapshot)
        return snapshot

    def get_access_token(self, scopes: list[str] | None = None) -> str:
        """Acquire a valid access token for downstream Power BI API clients."""
        return self._client.get_access_token(scopes=scopes)

    def _run_async(
        self,
        action: Callable[[], AuthStateSnapshot],
        *,
        busy_message: str,
    ) -> None:
        if self.is_busy:
            logger.debug("Authentication operation already in progress; ignoring duplicate trigger.")
            return

        current = self._client.state
        self.state_changed.emit(
            AuthStateSnapshot(
                status=AuthStatus.SIGNING_IN,
                account=current.account,
                status_message=busy_message,
                client_id_configured=current.client_id_configured,
                tenant_id=current.tenant_id,
            )
        )

        worker = _AuthWorker(action, parent=self)
        worker.completed.connect(self._on_worker_completed)
        worker.failed.connect(self._on_worker_failed)
        worker.finished.connect(self._cleanup_worker)
        self._active_worker = worker
        worker.start()

    def _on_worker_completed(self, snapshot: AuthStateSnapshot) -> None:
        self.state_changed.emit(snapshot)

    def _on_worker_failed(self, user_message: str) -> None:
        self.state_changed.emit(self._client.state)
        self.error_occurred.emit(user_message)

    def _cleanup_worker(self) -> None:
        if self._active_worker is not None:
            self._active_worker.deleteLater()
            self._active_worker = None

    def shutdown(self) -> None:
        """Wait briefly for any in-flight background worker on clean app exit."""
        if self._active_worker is not None and self._active_worker.isRunning():
            self._active_worker.quit()
            self._active_worker.wait(1000)
