"""UI tests for Stage 14 History page, Run comparison dialog, and Backup maintenance dialog."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QHeaderView
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


def _make_dummy_run(
    run_id: int,
    status: ValidationStatus,
    started_at: datetime | None = None,
) -> ValidationRunSummaryDTO:
    now = started_at or datetime(2026, 11, 19, 12, 0, 0, tzinfo=timezone.utc)
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

    # Verify no ghost text is rendered behind status pills in either table
    assert page.runs_table.item(0, 3).text() == ""
    assert page.runs_table.cellWidget(0, 3) is not None
    assert page.results_table.item(0, 0).text() == ""
    assert page.results_table.cellWidget(0, 0) is not None


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


def test_history_page_column_resize_modes_and_widths(qtbot):
    page = HistoryPage()
    qtbot.addWidget(page)
    page.show()

    runs_header = page.runs_table.horizontalHeader()
    # Check that column 1 is NOT Stretch, but Interactive so user can freely resize
    assert runs_header.sectionResizeMode(1) == QHeaderView.ResizeMode.Interactive
    assert runs_header.minimumSectionSize() >= 65
    assert page.runs_table.columnWidth(1) >= 150
    assert page.runs_table.isSortingEnabled()

    # Check results drawer table
    results_header = page.results_table.horizontalHeader()
    assert results_header.sectionResizeMode(1) == QHeaderView.ResizeMode.Interactive
    assert results_header.minimumSectionSize() >= 65
    assert page.results_table.columnWidth(1) >= 180
    assert page.results_table.isSortingEnabled()


def test_history_page_sorting_and_date_filtering(qtbot):
    page = HistoryPage()
    qtbot.addWidget(page)
    page.show()

    now = datetime.now(timezone.utc)
    old = now - timedelta(days=45)

    run_new = _make_dummy_run(10, ValidationStatus.PASS, started_at=now)
    run_old = _make_dummy_run(2, ValidationStatus.FAIL, started_at=old)

    page._runs = [run_new, run_old]
    page._render_runs_table()

    assert page.runs_table.rowCount() == 2
    assert "Showing all 2 runs" in page.lbl_filtered_count.text()

    # Filter to Last 30 Days (index 3) -> should hide run_old (45 days ago)
    page.date_filter_combo.setCurrentIndex(3)
    assert not page.runs_table.isRowHidden(0)
    assert page.runs_table.isRowHidden(1)
    assert "Showing 1 of 2 runs (filtered)" in page.lbl_filtered_count.text()

    # Test Clear Filters button
    page.btn_clear_filters.click()
    assert page.date_filter_combo.currentIndex() == 0
    assert not page.runs_table.isRowHidden(0)
    assert not page.runs_table.isRowHidden(1)
    assert "Showing all 2 runs" in page.lbl_filtered_count.text()


def test_history_drawer_filtering(qtbot):
    page = HistoryPage()
    qtbot.addWidget(page)
    page.show()

    now = datetime.now(timezone.utc)
    res_pass = ValidationResultDTO(
        id=101,
        validation_run_id=1,
        rule_id=1,
        rule_name="Sales Blanks",
        validation_type="null_check",
        target_type="COLUMN",
        target_display="Sales[Amount]",
        status=ValidationStatus.PASS,
        actual_value="0",
        expected_value="0",
        deviation="None",
        result_summary="Passed",
        detailed_message="",
        duration_ms=20,
        started_at=now,
        completed_at=now,
    )
    res_fail = ValidationResultDTO(
        id=102,
        validation_run_id=1,
        rule_id=2,
        rule_name="Customer Duplicates",
        validation_type="duplicate_check",
        target_type="COLUMN",
        target_display="Customer[ID]",
        status=ValidationStatus.FAIL,
        actual_value="5",
        expected_value="0",
        deviation="+5",
        result_summary="Failed",
        detailed_message="",
        duration_ms=30,
        started_at=now,
        completed_at=now,
    )

    run = ValidationRunSummaryDTO(
        id=1,
        workspace_registration_id=1,
        overall_status=ValidationStatus.FAIL,
        passed_count=1,
        failed_count=1,
        warning_count=0,
        error_count=0,
        total_rules=2,
        duration_ms=50,
        app_version="0.1.0",
        started_at=now,
        completed_at=now,
        results=[res_pass, res_fail],
    )

    page._runs = [run]
    page._render_runs_table()
    page.runs_table.selectRow(0)

    assert not page.results_table.isHidden()
    assert page.results_table.rowCount() == 2

    # Filter drawer by rule search
    page.results_search_input.setText("Customer")
    assert page.results_table.isRowHidden(0)
    assert not page.results_table.isRowHidden(1)

    # Clear search and filter by status FAIL only (index 1)
    page.results_search_input.clear()
    page.results_status_combo.setCurrentIndex(1)
    assert page.results_table.isRowHidden(0)
    assert not page.results_table.isRowHidden(1)

