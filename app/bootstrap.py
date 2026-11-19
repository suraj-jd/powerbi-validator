"""Central application bootstrap wiring configuration, logging, exceptions, and UI."""

from __future__ import annotations

import logging
import sys
from dataclasses import dataclass
from pathlib import Path

from PySide6.QtWidgets import QApplication

from app import APP_NAME, APP_VERSION
from app.auth.azure_cli_auth import AzureCliAuthClient
from app.auth.msal_auth import AuthConfig, MsalAuthClient
from app.core.config import (
    AppConfig,
    get_app_data_dir,
    get_database_path,
    get_logs_dir,
    get_token_cache_path,
    load_config,
)
from app.core.exceptions import ConfigurationError, install_exception_hooks
from app.core.logging_config import setup_logging
from app.core.status import NotificationLevel
from app.database.db import DatabaseManager
from app.integrations.powerbi.metadata_client import MetadataClient
from app.integrations.powerbi.refresh_client import RefreshClient
from app.services.auth_service import AuthService
from app.services.metadata_service import MetadataService
from app.services.powerbi_service import PowerBIService
from app.services.refresh_service import RefreshService
from app.services.registry_service import RegistryService
from app.services.rule_service import RuleService
from app.ui.main_window import MainWindow
from app.ui.theme import APP_STYLESHEET

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class AppContext:
    """Runtime container holding initialized application objects."""

    qt_app: QApplication
    window: MainWindow
    config: AppConfig
    db: DatabaseManager
    auth_service: AuthService
    powerbi_service: PowerBIService
    registry_service: RegistryService
    metadata_service: MetadataService
    rule_service: RuleService
    refresh_service: RefreshService
    data_dir: Path
    logs_dir: Path
    log_file: Path
    db_path: Path
    token_cache_path: Path


def create_application(argv: list[str] | None = None) -> QApplication:
    """Create or reuse the QApplication instance with the enterprise theme."""
    existing = QApplication.instance()
    if isinstance(existing, QApplication):
        qt_app = existing
    else:
        qt_app = QApplication(argv if argv is not None else sys.argv)

    qt_app.setApplicationName(APP_NAME)
    qt_app.setApplicationVersion(APP_VERSION)
    qt_app.setStyle("Fusion")
    qt_app.setStyleSheet(APP_STYLESHEET)
    return qt_app


def bootstrap_application(
    argv: list[str] | None = None,
    *,
    data_dir: Path | None = None,
    install_hooks: bool = True,
    auto_restore_auth: bool = True,
) -> AppContext:
    """Initialize config, rotating secret-safe logging, SQLite, auth, exception hooks, and UI."""
    resolved_data_dir = get_app_data_dir(data_dir)
    resolved_logs_dir = get_logs_dir(resolved_data_dir)
    resolved_db_path = get_database_path(resolved_data_dir)
    resolved_token_cache_path = get_token_cache_path(resolved_data_dir)

    config_warning: str | None = None
    try:
        config = load_config(resolved_data_dir)
    except ConfigurationError as exc:
        config = AppConfig()
        config_warning = exc.user_message

    log_file = setup_logging(config, resolved_logs_dir)
    logger.info("Bootstrapping %s v%s (data_dir=%s)", APP_NAME, APP_VERSION, resolved_data_dir)
    if config_warning:
        logger.warning("Falling back to default configuration: %s", config_warning)

    db = DatabaseManager(resolved_db_path)
    db.run_migrations()

    qt_app = create_application(argv)

    auth_client = MsalAuthClient(
        config=AuthConfig(
            client_id=config.effective_client_id(),
            tenant_id=config.effective_tenant_id(),
        ),
        cache_path=resolved_token_cache_path,
    )
    auth_service = AuthService(
        auth_client=auth_client,
        azure_cli_client=AzureCliAuthClient(),
        app_config=config,
        data_dir=resolved_data_dir,
    )
    powerbi_service = PowerBIService(auth_service=auth_service)
    registry_service = RegistryService(db=db)
    rule_service = RuleService(db=db)
    metadata_client = MetadataClient(powerbi_service.rest_client)
    metadata_service = MetadataService(metadata_client=metadata_client)
    refresh_client = RefreshClient(powerbi_service.rest_client)
    refresh_service = RefreshService(db=db, refresh_client=refresh_client)

    window = MainWindow(
        config=config,
        logs_dir=resolved_logs_dir,
        db_path=resolved_db_path,
        token_cache_path=resolved_token_cache_path,
        auth_service=auth_service,
        powerbi_service=powerbi_service,
        registry_service=registry_service,
        metadata_service=metadata_service,
        rule_service=rule_service,
        refresh_service=refresh_service,
    )

    if config_warning:
        window.show_notification(
            config_warning,
            level=NotificationLevel.WARNING,
            title="Configuration",
        )

    if install_hooks:
        install_exception_hooks(
            on_unhandled_error=lambda msg: window.post_notification(
                msg,
                level=NotificationLevel.ERROR,
                title="Unexpected Error",
            )
        )

    if auto_restore_auth:
        auth_service.restore_session_async()

    def _on_quit() -> None:
        refresh_service.shutdown()
        metadata_service.shutdown()
        powerbi_service.shutdown()
        auth_service.shutdown()
        db.dispose()
        logger.info("%s exited cleanly.", APP_NAME)

    qt_app.aboutToQuit.connect(_on_quit)

    return AppContext(
        qt_app=qt_app,
        window=window,
        config=config,
        db=db,
        auth_service=auth_service,
        powerbi_service=powerbi_service,
        registry_service=registry_service,
        metadata_service=metadata_service,
        rule_service=rule_service,
        refresh_service=refresh_service,
        data_dir=resolved_data_dir,
        logs_dir=resolved_logs_dir,
        log_file=log_file,
        db_path=resolved_db_path,
        token_cache_path=resolved_token_cache_path,
    )
