"""Qt-friendly authentication service supporting both Microsoft Entra MSAL and Azure CLI."""

from __future__ import annotations

import logging
from collections.abc import Callable
from pathlib import Path
from typing import Protocol

from PySide6.QtCore import QObject, QThread, Signal

from app.auth.azure_cli_auth import AzureCliAuthClient
from app.auth.msal_auth import AuthConfig, AuthStateSnapshot, AuthStatus, MsalAuthClient
from app.core.config import AppConfig, save_config
from app.core.exceptions import format_safe_user_error

logger = logging.getLogger(__name__)


class AuthProvider(Protocol):
    """Common interface implemented by MsalAuthClient and AzureCliAuthClient."""

    @property
    def state(self) -> AuthStateSnapshot: ...

    def restore_session(self) -> AuthStateSnapshot: ...

    def sign_in_interactive(self, *, force_select_account: bool = False) -> AuthStateSnapshot: ...

    def switch_account(self) -> AuthStateSnapshot: ...

    def get_access_token(
        self,
        *,
        scopes: list[str] | None = None,
        allow_interactive_fallback: bool = False,
    ) -> str: ...

    def sign_out(self) -> AuthStateSnapshot: ...


class _AuthWorker(QThread):
    """Background thread executing blocking auth calls without freezing Qt UI."""

    completed = Signal(object, bool)
    failed = Signal(str, bool)

    def __init__(
        self,
        action: Callable[[], AuthStateSnapshot],
        *,
        is_interactive: bool = False,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._action = action
        self._is_interactive = is_interactive

    def run(self) -> None:
        try:
            snapshot = self._action()
            self.completed.emit(snapshot, self._is_interactive)
        except Exception as exc:
            logger.warning("Authentication operation failed: %s", format_safe_user_error(exc))
            self.failed.emit(format_safe_user_error(exc), self._is_interactive)


class AuthService(QObject):
    """Bridges MSAL and Azure CLI auth providers with PySide6 widgets."""

    state_changed = Signal(object)
    error_occurred = Signal(str)
    interactive_login_completed = Signal(bool)

    def __init__(
        self,
        *,
        auth_client: MsalAuthClient,
        app_config: AppConfig,
        data_dir: Path,
        azure_cli_client: AzureCliAuthClient | None = None,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._msal_client = auth_client
        self._azure_cli_client = azure_cli_client
        self._app_config = app_config
        self._data_dir = data_dir
        self._active_worker: _AuthWorker | None = None

    @property
    def client(self) -> MsalAuthClient:
        """Return the underlying MSAL client (for Entra configuration checks)."""
        return self._msal_client

    @property
    def active_provider(self) -> AuthProvider:
        """Select Entra MSAL when configured/forced, otherwise use Azure CLI when available."""
        mode = self._app_config.auth_mode
        if mode == "entra_msal":
            return self._msal_client
        if mode == "azure_cli" and self._azure_cli_client is not None:
            return self._azure_cli_client
        # Auto mode: prefer configured Entra MSAL; otherwise use Azure CLI for one-click login
        if self._msal_client.config.is_configured:
            return self._msal_client
        if self._azure_cli_client is not None:
            return self._azure_cli_client
        return self._msal_client

    @property
    def is_ready_for_one_click_signin(self) -> bool:
        """Return True when clicking Sign In can immediately launch browser login."""
        provider = self.active_provider
        if isinstance(provider, AzureCliAuthClient):
            return provider.is_available
        return self._msal_client.config.is_configured

    @property
    def state(self) -> AuthStateSnapshot:
        return self.active_provider.state

    @property
    def is_busy(self) -> bool:
        return self._active_worker is not None and self._active_worker.isRunning()

    def configure_entra_app(self, client_id: str, tenant_id: str) -> AuthStateSnapshot:
        """Save non-secret Entra Client ID and Tenant ID and switch to Entra MSAL."""
        cleaned_client = client_id.strip()
        cleaned_tenant = tenant_id.strip() or "organizations"

        self._app_config.auth_client_id = cleaned_client
        self._app_config.auth_tenant_id = cleaned_tenant
        self._app_config.auth_mode = "entra_msal" if cleaned_client else "auto"
        save_config(self._app_config, data_dir=self._data_dir)

        new_auth_config = AuthConfig(
            client_id=cleaned_client,
            tenant_id=cleaned_tenant,
            scopes=self._msal_client.config.scopes,
        )
        snapshot = self._msal_client.reconfigure(new_auth_config)
        self.state_changed.emit(self.state)
        return snapshot

    def restore_session_async(self) -> None:
        """Attempt silent session restoration in the background on startup."""
        provider = self.active_provider
        if isinstance(provider, MsalAuthClient) and not provider.config.is_configured:
            self.state_changed.emit(provider.state)
            return
        if isinstance(provider, AzureCliAuthClient) and not provider.is_available:
            self.state_changed.emit(provider.state)
            return
        self._run_async(provider.restore_session, busy_message="Checking saved Microsoft session...")

    def sign_in_async(self) -> None:
        """Launch interactive Microsoft browser sign-in off the UI thread."""
        provider = self.active_provider
        self._run_async(
            lambda: provider.sign_in_interactive(force_select_account=False),
            busy_message="Opening Microsoft sign-in in your browser...",
            is_interactive=True,
        )

    def switch_account_async(self) -> None:
        """Launch interactive Microsoft account picker off the UI thread."""
        provider = self.active_provider
        self._run_async(
            provider.switch_account,
            busy_message="Opening Microsoft account chooser in your browser...",
            is_interactive=True,
        )

    def sign_out(self) -> AuthStateSnapshot:
        """Sign out of the active provider and emit updated state."""
        snapshot = self.active_provider.sign_out()
        self.state_changed.emit(snapshot)
        return snapshot

    def get_access_token(self, scopes: list[str] | None = None) -> str:
        """Acquire a valid Power BI access token from the active auth provider."""
        return self.active_provider.get_access_token(scopes=scopes)

    def _run_async(
        self,
        action: Callable[[], AuthStateSnapshot],
        *,
        busy_message: str,
        is_interactive: bool = False,
    ) -> None:
        if self.is_busy:
            logger.debug("Authentication operation already in progress; ignoring duplicate trigger.")
            return

        current = self.state
        self.state_changed.emit(
            AuthStateSnapshot(
                status=AuthStatus.SIGNING_IN,
                account=current.account,
                status_message=busy_message,
                client_id_configured=current.client_id_configured,
                tenant_id=current.tenant_id,
            )
        )

        worker = _AuthWorker(action, is_interactive=is_interactive, parent=self)
        worker.completed.connect(self._on_worker_completed)
        worker.failed.connect(self._on_worker_failed)
        worker.finished.connect(self._cleanup_worker)
        self._active_worker = worker
        worker.start()

    def _on_worker_completed(self, snapshot: AuthStateSnapshot, is_interactive: bool) -> None:
        self.state_changed.emit(snapshot)
        if is_interactive:
            self.interactive_login_completed.emit(True)

    def _on_worker_failed(self, user_message: str, is_interactive: bool) -> None:
        self.state_changed.emit(self.state)
        self.error_occurred.emit(user_message)
        if is_interactive:
            self.interactive_login_completed.emit(False)

    def _cleanup_worker(self) -> None:
        if self._active_worker is not None:
            self._active_worker.deleteLater()
            self._active_worker = None

    def shutdown(self) -> None:
        """Wait briefly for any in-flight background worker on clean app exit."""
        if self._active_worker is not None and self._active_worker.isRunning():
            self._active_worker.quit()
            self._active_worker.wait(1000)
