"""Application entry point for the Power BI Validation Tool."""

from __future__ import annotations

import logging
import sys

from PySide6.QtWidgets import QApplication

from app import APP_NAME, APP_VERSION
from app.ui.main_window import MainWindow
from app.ui.theme import APP_STYLESHEET


def configure_basic_logging(level: int = logging.INFO) -> None:
    """Set up basic console logging for Stage 0."""
    logging.basicConfig(
        level=level,
        format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


def create_application(argv: list[str] | None = None) -> QApplication:
    """Create and configure the QApplication instance."""
    qt_app = QApplication(argv if argv is not None else sys.argv)
    qt_app.setApplicationName(APP_NAME)
    qt_app.setApplicationVersion(APP_VERSION)
    qt_app.setStyle("Fusion")
    qt_app.setStyleSheet(APP_STYLESHEET)
    return qt_app


def main(argv: list[str] | None = None) -> int:
    """Launch the PySide6 desktop shell and return the process exit code."""
    configure_basic_logging()
    logger = logging.getLogger(__name__)
    logger.info("Starting %s v%s", APP_NAME, APP_VERSION)

    qt_app = create_application(argv)
    qt_app.aboutToQuit.connect(lambda: logger.info("%s exited cleanly.", APP_NAME))

    window = MainWindow()
    window.show()

    exit_code = qt_app.exec()
    logger.info("Event loop terminated with exit code %d.", exit_code)
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
