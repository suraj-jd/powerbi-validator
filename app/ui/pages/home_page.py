"""Home / Dashboard placeholder page (Stage 0)."""

from __future__ import annotations

from PySide6.QtWidgets import QWidget

from app.ui.pages.placeholder_page import PlaceholderPage


class HomePage(PlaceholderPage):
    """Dashboard placeholder for Stage 0."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(
            title="Power BI Report Health Monitor",
            subtitle="Validate. Detect. Ensure Data Integrity.",
            planned_items=[
                "Microsoft authentication banner and workspace access status (Stages 3–4)",
                "Run summary KPI cards: Passed, Failed, Warning, and Health Score (Stage 13)",
                "Report overview and latest refresh status, start/end time, and duration (Stages 8 & 13)",
                "Row-by-row validation results table with status filtering and detail inspection (Stage 13)",
                "One-click Run Validation connected to the validation orchestrator (Stage 12)",
            ],
            stage_note=(
                "Stage 0 shell active — no Power BI credentials, network calls, or local "
                "database connections are executed in this stage."
            ),
            parent=parent,
        )
