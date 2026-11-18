"""Application entry point for the Power BI Validation Tool."""

from __future__ import annotations

import logging

from app.bootstrap import bootstrap_application

logger = logging.getLogger(__name__)


def main(argv: list[str] | None = None) -> int:
    """Bootstrap and run the PySide6 desktop application."""
    context = bootstrap_application(argv)
    context.window.show()

    exit_code = context.qt_app.exec()
    logger.info("Event loop terminated with exit code %d.", exit_code)
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
