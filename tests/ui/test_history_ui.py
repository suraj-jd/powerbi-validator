"""UI tests for Stage 14 History page, Run comparison dialog, and Backup maintenance dialog."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QHeaderView, QLabel, QPushButton
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

    # Verify status items render bold colorful text without cell widgets
    assert page.runs_table.item(0, 3).text() == "FAIL"
    assert page.runs_table.item(0, 3).font().bold() is True
    assert page.runs_table.cellWidget(0, 3) is None
    assert page.results_table.item(0, 0).text() == "FAIL"
    assert page.results_table.item(0, 0).font().bold() is True
    assert page.results_table.cellWidget(0, 0) is None


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
    assert dialog.diff_table.verticalHeader().defaultSectionSize() >= 34
    assert dialog.diff_table.item(0, 0).text() == "REGRESSION"
    assert dialog.diff_table.item(0, 0).font().bold() is True
    assert dialog.diff_table.item(0, 3).text() == "PASS"
    assert dialog.diff_table.item(0, 3).font().bold() is True
    assert dialog.diff_table.item(0, 4).text() == "FAIL"
    assert dialog.diff_table.item(0, 4).font().bold() is True


def test_run_comparison_dialog_up_to_4_runs_ui(qtbot):
    run1 = _make_dummy_run(1, ValidationStatus.PASS)
    run2 = _make_dummy_run(2, ValidationStatus.FAIL)
    run3 = _make_dummy_run(3, ValidationStatus.WARNING)
    run4 = _make_dummy_run(4, ValidationStatus.PASS)
    all_runs = [run1, run2, run3, run4]

    # Initial 4-run comparison
    cmp4 = compare_validation_runs(run1, run2, run3, run4)
    dialog = RunComparisonDialog(cmp4, all_runs=all_runs)
    qtbot.addWidget(dialog)
    dialog.show()

    # 12 columns: Change, Rule Name, Target, 4 Statuses, 4 Actuals, 1 Deviation
    assert dialog.diff_table.columnCount() == 12
    assert "Run #1 vs Run #2 vs Run #3 vs Run #4" in dialog.windowTitle()
    assert dialog.combo_run_a.currentData() == 1
    assert dialog.combo_run_b.currentData() == 2
    assert dialog.combo_run_c.currentData() == 3
    assert dialog.combo_run_d.currentData() == 4

    # Click clear optional (Run 3 and Run 4)
    dialog.btn_clear_optional.click()
    assert dialog.combo_run_c.currentData() is None
    assert dialog.combo_run_d.currentData() is None
    # Now drops to 8 columns (only Run 1 and Run 2 active)
    assert dialog.diff_table.columnCount() == 8
    assert "Run #1 vs Run #2" in dialog.windowTitle()

    # Select Run 3 back in combo_run_c
    idx3 = dialog.combo_run_c.findData(3)
    assert idx3 > 0
    dialog.combo_run_c.setCurrentIndex(idx3)
    # Now 10 columns (Run 1, Run 2, Run 3)
    assert dialog.diff_table.columnCount() == 10
    assert "Run #1 vs Run #2 vs Run #3" in dialog.windowTitle()


def test_backup_maintenance_dialog_ui(qtbot, tmp_path):
    db_file = tmp_path / "maint_test.db"
    db = DatabaseManager(db_file)
    db.run_migrations()

    dialog = BackupMaintenanceDialog(db)
    qtbot.addWidget(dialog)
    dialog.show()

    assert "Database Backup" in dialog.windowTitle()
    assert dialog.spin_retention.value() == 90

    # Verify Save Backup button has bold "Save" text with floppy disk icon
    save_btns = [btn for btn in dialog.findChildren(QPushButton) if "💾" in btn.text()]
    assert len(save_btns) == 1
    assert "Save" in save_btns[0].text()
    assert "font-weight: 700" in save_btns[0].styleSheet()

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


def test_run_comparison_dialog_run_switching_and_filtering(qtbot, tmp_path):
    run1 = _make_dummy_run(1, ValidationStatus.PASS)
    run2 = _make_dummy_run(2, ValidationStatus.FAIL)
    run3 = _make_dummy_run(3, ValidationStatus.WARNING)

    cmp = compare_validation_runs(run1, run2)
    dialog = RunComparisonDialog(cmp, all_runs=[run1, run2, run3])
    qtbot.addWidget(dialog)
    dialog.show()

    assert dialog.combo_run_a.count() == 3
    assert dialog.combo_run_b.count() == 3

    # Swap runs
    dialog._handle_swap_runs()
    assert dialog._cmp.run_a.id == 2
    assert dialog._cmp.run_b.id == 1

    # Filter by search text
    dialog.search_input.setText("NonExistent")
    assert dialog.diff_table.isRowHidden(0)

    dialog.search_input.clear()
    assert not dialog.diff_table.isRowHidden(0)

    # Filter by change type
    dialog._filter_by_card("REGRESSION")
    assert dialog._current_filter_change == "REGRESSION"

    # Reset filters
    dialog._handle_reset_filters()
    assert dialog._current_filter_change == "ALL"
    assert not dialog.diff_table.isRowHidden(0)

    # Test export diff to CSV
    csv_out = tmp_path / "diff_test.csv"
    from app.services.compare_service import export_comparison_to_csv
    export_comparison_to_csv(dialog._cmp, csv_out)
    assert csv_out.exists()
    assert "REGRESSION" in csv_out.read_text(encoding="utf-8") or "IMPROVEMENT" in csv_out.read_text(encoding="utf-8")


def test_backup_maintenance_dialog_stats_and_actions(qtbot, tmp_path):
    db_file = tmp_path / "maint_test_ext.db"
    db = DatabaseManager(db_file)
    db.run_migrations()

    dialog = BackupMaintenanceDialog(db)
    qtbot.addWidget(dialog)
    dialog.show()

    assert "Database File:" in dialog.lbl_path.text()
    assert "Runs: 0" in dialog.lbl_metrics.text()
    assert "Storage Size:" in dialog.lbl_metrics.text()

    # Prune preview updates
    dialog.spin_retention.setValue(30)
    assert "0 runs are older than 30 days" in dialog.lbl_prune_info.text()

    # Vacuum action executes cleanly
    dialog._handle_vacuum()
    assert "Database Compacted" in dialog.banner.current_message or "defragmented" in dialog.banner.current_message

    db.dispose()


def test_run_comparison_kpi_worsened_and_info_tooltips(qtbot):
    run1 = _make_dummy_run(1, ValidationStatus.PASS)
    run2 = _make_dummy_run(2, ValidationStatus.FAIL)
    cmp = compare_validation_runs(run1, run2)
    dialog = RunComparisonDialog(cmp)
    qtbot.addWidget(dialog)
    dialog.show()

    # Verify Worsened card header
    labels = dialog.c_reg.findChildren(QLabel)
    assert any(lbl.text() == "WORSENED" for lbl in labels)

    # Verify 'i' buttons exist with explanatory tooltips
    info_buttons = [b for b in dialog.findChildren(QPushButton) if b.text() == "i"]
    assert len(info_buttons) == 4
    for b in info_buttons:
        assert len(b.toolTip()) > 10

    # Verify tooltip explains degraded checks
    assert "failed or degraded" in dialog.c_reg.toolTip().lower()



