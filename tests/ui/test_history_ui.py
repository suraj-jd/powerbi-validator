"""UI tests for Stage 14 History page, Run comparison dialog, and Backup maintenance dialog."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock

from PySide6.QtCore import Qt
import pytest

from app.core.status import ValidationStatus
from app.database.db import DatabaseManager
from app.services.compare_service import compare_validation_runs
from app.services.orchestrator_service import (
    OrchestratorService,
    ValidationResultDTO,
    ValidationRunSummaryDTO,
)
from app.ui.dialogs.backup_maintenance_dialog import BackupMaintenanceDialog
from app.ui.dialogs.run_comparison_dialog import RunComparisonDialog
from app.ui.pages.history_page import HistoryPage


def _make_dummy_run(run_id: int, status: ValidationStatus) -> ValidationRunSummaryDTO:
    now = datetime(2026, 11, 19, 12, 0, 0, tzinfo=timezone.utc)
    res = [
        ValidationResultDTO(
            id=run_id * 10 + 1,
            validation_run_id=run_id,
            rule_id=1,
            rule_name="Sales Null Check",
            validation_type="null_check",
            target_type="COLUMN",
            target_display="Sales[Amount]",
            status=status,
            actual_value="0 blanks",
            expected_value="<= 0 blanks",
            deviation="None",
            result_summary="Passed null check",
            detailed_message="Details...",
            duration_ms=40,
            started_at=now,
            completed_at=now,
        )
    ]
    return ValidationRunSummaryDTO(
        id=run_id,
        workspace_registration_id=1,
        overall_status=status,
        passed_count=1 if status == ValidationStatus.PASS else 0,
        failed_count=1 if status == ValidationStatus.FAIL else 0,
        warning_count=0,
        error_count=0,
        total_rules=1,
        duration_ms=100,
        app_version="0.1.0",
        started_at=now,
        completed_at=now,
        results=res,
    )


def test_history_page_renders_runs_and_drawer(qtbot):
    page = HistoryPage()
    qtbot.addWidget(page)
    page.show()

    assert page.btn_refresh.text() == "↻  Refresh History"
    assert page.btn_compare.text() == "⚖  Compare Runs..."

    # Inject mock runs
    run1 = _make_dummy_run(1, ValidationStatus.PASS)
    run2 = _make_dummy_run(2, ValidationStatus.FAIL)
    page._runs = [run2, run1]
    page._render_runs_table()

    assert not page.runs_table.isHidden()
    assert page.runs_table.rowCount() == 2
    assert page.runs_table.item(0, 0).text() == "#2"
    assert page.runs_table.item(1, 0).text() == "#1"

    # Selecting run 2 loads drawer
    page.runs_table.selectRow(0)
    assert not page.results_table.isHidden()
    assert page.results_table.rowCount() == 1
    assert page.results_table.item(0, 1).text() == "Sales Null Check"


def test_history_page_filtering(qtbot):
    page = HistoryPage()
    qtbot.addWidget(page)
    page.show()

    run1 = _make_dummy_run(1, ValidationStatus.PASS)
    run2 = _make_dummy_run(2, ValidationStatus.FAIL)
    page._runs = [run2, run1]
    page._render_runs_table()

    # Filter to "Failed Runs Only" (index 1)
    page.status_filter_combo.setCurrentIndex(1)
    assert not page.runs_table.isRowHidden(0)  # Run 2 is FAIL
    assert page.runs_table.isRowHidden(1)      # Run 1 is PASS

    # Filter to "Passed Runs Only" (index 2)
    page.status_filter_combo.setCurrentIndex(2)
    assert page.runs_table.isRowHidden(0)
    assert not page.runs_table.isRowHidden(1)


def test_run_comparison_dialog_ui(qtbot):
    run1 = _make_dummy_run(1, ValidationStatus.PASS)
    run2 = _make_dummy_run(2, ValidationStatus.FAIL)

    cmp = compare_validation_runs(run1, run2)
    dialog = RunComparisonDialog(cmp)
    qtbot.addWidget(dialog)
    dialog.show()

    assert "Run #1 vs Run #2" in dialog.windowTitle()
    assert dialog.diff_table.rowCount() == 1
    assert dialog.diff_table.item(0, 1).text() == "Sales Null Check"


def test_backup_maintenance_dialog_ui(qtbot, tmp_path):
    db_file = tmp_path / "maint_test.db"
    db = DatabaseManager(db_file)
    db.run_migrations()

    dialog = BackupMaintenanceDialog(db)
    qtbot.addWidget(dialog)
    dialog.show()

    assert "Database Backup" in dialog.windowTitle()
    assert dialog.spin_retention.value() == 90

    db.dispose()
