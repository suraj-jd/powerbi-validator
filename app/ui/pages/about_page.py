"""About placeholder page (Stage 0)."""

from __future__ import annotations

import platform
import sys

from PySide6 import __version__ as pyside_version
from PySide6.QtWidgets import QWidget

from app import APP_NAME, APP_STAGE, APP_VERSION
from app.ui.pages.placeholder_page import PlaceholderPage


class AboutPage(PlaceholderPage):
    """Application information page for Stage 0."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(
            title=f"About {APP_NAME}",
            subtitle="Local-first Windows desktop application for Power BI report validation.",
            planned_items=[
                f"Application Version: v{APP_VERSION}",
                f"Current Milestone: {APP_STAGE}",
                f"Python Runtime: {sys.version.split()[0]} ({platform.system()} {platform.release()})",
                f"UI Framework: PySide6 {pyside_version}",
            ],
            stage_note=(
                "Built incrementally following the Power BI Validation Tool BRD & Development Plan. "
                "No telemetry, cloud backend, or stored passwords."
            ),
            parent=parent,
        )
