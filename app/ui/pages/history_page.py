"""Validation History placeholder page (Stage 0)."""

from __future__ import annotations

from PySide6.QtWidgets import QWidget

from app.ui.pages.placeholder_page import PlaceholderPage


class HistoryPage(PlaceholderPage):
    """Validation history placeholder for Stage 0."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(
            title="Validation History",
            subtitle="Inspect past validation runs, compare results over time, and export reports.",
            planned_items=[
                "Immutable local run log stored in SQLite (Stages 2 & 12)",
                "Run filtering by date, report, and overall status (Stage 14)",
                "Side-by-side run comparison and detailed result inspection (Stage 14)",
                "CSV/XLSX result export, sanitized diagnostic logs, and local database backup (Stage 14)",
            ],
            stage_note=(
                "History storage and export workflows will become available after local SQLite "
                "persistence and validation orchestration are implemented."
            ),
            parent=parent,
        )
