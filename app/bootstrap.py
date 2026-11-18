"""Central application bootstrap wiring configuration, logging, exceptions, and UI."""

from __future__ import annotations

import logging
import sys
from dataclasses import dataclass
from pathlib import Path

from PySide6.QtWidgets import QApplication

from app import APP_NAME, APP_VERSION
from app.core.config import (
    AppConfig,
    get_app_data_dir,
    get_database_path,
    get_logs_dir,
    load_config,
)
from app.core.exceptions import ConfigurationError, install_exception_hooks
from app.core.logging_config import setup_logging
from app.core.status import NotificationLevel
from app.database.db import DatabaseManager
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
    data_dir: Path
    logs_dir: Path
    log_file: Path
    db_path: Path


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
) -> AppContext:
    """Initialize config, rotating secret-safe logging, exception hooks, and MainWindow."""
    resolved_data_dir = get_app_data_dir(data_dir)
    resolved_logs_dir = get_logs_dir(resolved_data_dir)
    resolved_db_path = get_database_path(resolved_data_dir)

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
    window = MainWindow(
        config=config,
        logs_dir=resolved_logs_dir,
        db_path=resolved_db_path,
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

    def _on_quit() -> None:
        db.dispose()
        logger.info("%s exited cleanly.", APP_NAME)

    qt_app.aboutToQuit.connect(_on_quit)

    return AppContext(
        qt_app=qt_app,
        window=window,
        config=config,
        db=db,
        data_dir=resolved_data_dir,
        logs_dir=resolved_logs_dir,
        log_file=log_file,
        db_path=resolved_db_path,
    )
