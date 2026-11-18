"""Settings placeholder page (Stage 0)."""

from __future__ import annotations

from PySide6.QtWidgets import QWidget

from app.ui.pages.placeholder_page import PlaceholderPage


class SettingsPage(PlaceholderPage):
    """Validation settings placeholder for Stage 0."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(
            title="Validation Settings",
            subtitle="Configure workspace registrations, validation rules, and per-rule conditions.",
            planned_items=[
                "Workspace, Report, and Semantic Model registry with manual entry and CSV/XLSX import (Stage 5)",
                "Semantic model table, column, and measure discovery (Stage 6)",
                "Row-based validation rule editor with independent per-rule Advanced Settings (Stage 7)",
                "Local SQLite persistence for registrations and rules (Stages 2, 5 & 7)",
            ],
            stage_note=(
                "Configuration persistence and Power BI verification will be added incrementally "
                "in Stages 2 through 7."
            ),
            parent=parent,
        )
