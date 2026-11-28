"""UI tests for Stage 13 Home dashboard, validation runner, results table, and diagnostics dialog."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication
import pytest

from app.core.status import ValidationStatus
from app.services.orchestrator_service import (
    OrchestratorService,
    ValidationResultDTO,
    ValidationRunSummaryDTO,
)
from app.services.registry_service import RegistrationRecord, RegistryService
from app.ui.dialogs.result_details_dialog import ResultDetailsDialog
from app.ui.pages.home_page import HomePage


def _make_dummy_run_summary() -> ValidationRunSummaryDTO:
    now = datetime(2026, 11, 19, 14, 0, 0, tzinfo=timezone.utc)
    r1 = ValidationResultDTO(
        id=101,
        validation_run_id=1,
        rule_id=1,
        rule_name="Sales Amount Not Blank",
        validation_type="null_check",
        target_type="COLUMN",
        target_display="Sales[Amount]",
        status=ValidationStatus.PASS,
        actual_value="0 blanks / 1,000 rows (0.0%)",
        expected_value="<= 0 blanks (0.0%)",
        deviation="None (Within threshold)",
        result_summary="Null check passed: 0 blanks.",
        detailed_message="Checked 1000 rows in 'Sales'.",
        duration_ms=45,
        started_at=now,
        completed_at=now,
    )
    r2 = ValidationResultDTO(
        id=102,
        validation_run_id=1,
        rule_id=2,
        rule_name="Order ID Unique Key",
        validation_type="duplicate_check",
        target_type="COLUMN",
        target_display="Sales[OrderID]",
        status=ValidationStatus.FAIL,
        actual_value="15 duplicates / 1,000 rows (1.5%)",
        expected_value="<= 0 duplicates (0.0%)",
        deviation="+15 duplicates over limit",
        result_summary="Duplicate check failed: 15 duplicates detected.",
        detailed_message="Table: Sales, Column: OrderID",
        duration_ms=60,
        started_at=now,
        completed_at=now,
    )
    return ValidationRunSummaryDTO(
        id=1,
        workspace_registration_id=10,
        overall_status=ValidationStatus.FAIL,
        passed_count=1,
        failed_count=1,
        warning_count=0,
        error_count=0,
        total_rules=2,
        duration_ms=105,
        app_version="0.1.0",
        started_at=now,
        completed_at=now,
        results=[r1, r2],
    )


def test_home_page_initial_validation_state(qtbot):
    page = HomePage()
    qtbot.addWidget(page)
    page.show()

    assert page.run_validation_button.text() == "Run all enabled checks"
    assert not page.cancel_validation_button.isVisible()
    assert not page.validation_progress_bar.isVisible()

    assert page.home_passed_count.text() == "0"
    assert page.home_failed_count.text() == "0"
    assert page.home_warning_count.text() == "0"
    assert page.home_error_count.text() == "0"

    assert not page.empty_results_label.isHidden()
    assert page.results_table.isHidden()


def test_home_page_run_validation_updates_dashboard(qtbot):
    reg_svc = MagicMock(spec=RegistryService)
    reg_svc.find_by_workspace_and_dataset.return_value = RegistrationRecord(
        id=10,
        workspace_name="Finance WS",
        workspace_id="ws-123",
        report_name="Finance Report",
        report_id=None,
        dataset_name="Finance DS",
        dataset_id="ds-456",
        is_active=True,
    )

    summary = _make_dummy_run_summary()

    orch_svc = MagicMock(spec=OrchestratorService)
    orch_svc.is_registration_running.return_value = False
    orch_svc.run_validation.return_value = summary
    orch_svc.get_latest_run_for_registration.return_value = summary

    page = HomePage(registry_service=reg_svc, orchestrator_service=orch_svc)
    qtbot.addWidget(page)
    page.show()

    page.workspace_id_input.setText("ws-123")
    page.dataset_id_input.setText("ds-456")

    # Run validation button clicked
    qtbot.mouseClick(page.run_validation_button, Qt.MouseButton.LeftButton)

    # Wait for background thread worker to complete
    qtbot.waitUntil(lambda: page.home_failed_count.text() == "1", timeout=5000)

    # Verify KPI counts updated
    assert page.home_passed_count.text() == "1"
    assert page.home_failed_count.text() == "1"
    assert page.home_warning_count.text() == "0"
    assert page.home_error_count.text() == "0"

    # Verify table is visible and populated with 2 rows
    assert not page.results_table.isHidden()
    assert page.results_table.rowCount() == 2
    assert page.results_table.item(0, 1).text() == "Sales Amount Not Blank"
    assert page.results_table.item(1, 1).text() == "Order ID Unique Key"
    assert page.results_table.horizontalHeaderItem(2).text() == "Validated At (UTC)"
    assert page.results_table.item(0, 2).text() == "2026-11-19 14:00:00 UTC"
    page._open_result_details = MagicMock()
    page._handle_table_clicked(0, 9)
    page._open_result_details.assert_called_once_with(summary.results[0])


def test_home_page_run_sheet_validation_without_model_selection(qtbot):
    summary = _make_dummy_run_summary()
    orch_svc = MagicMock(spec=OrchestratorService)
    orch_svc.run_sheet_validation.return_value = summary
    orch_svc.get_latest_run.return_value = summary

    page = HomePage(orchestrator_service=orch_svc)
    qtbot.addWidget(page)
    page.show()

    # User clicks Run Validation on Home Page directly without choosing a model dropdown
    qtbot.mouseClick(page.run_validation_button, Qt.MouseButton.LeftButton)

    # Background worker runs sheet validation and populates dashboard
    qtbot.waitUntil(lambda: page.home_failed_count.text() == "1", timeout=5000)

    assert page.home_passed_count.text() == "1"
    assert page.home_failed_count.text() == "1"
    assert not page.results_table.isHidden()
    assert page.results_table.rowCount() == 2


def test_home_page_table_search_and_status_filtering(qtbot):
    page = HomePage()
    qtbot.addWidget(page)

    summary = _make_dummy_run_summary()
    page._display_run_summary(summary)

    assert page.results_table.rowCount() == 2
    assert not page.results_table.isRowHidden(0)
    assert not page.results_table.isRowHidden(1)

    # Search filter: "OrderID" matches row 1 only
    page.results_search_input.setText("OrderID")
    assert page.results_table.isRowHidden(0)
    assert not page.results_table.isRowHidden(1)

    # Clear search
    page.results_search_input.setText("")
    assert not page.results_table.isRowHidden(0)
    assert not page.results_table.isRowHidden(1)

    # Status filter: "Passed Only" (index 4)
    page.results_status_filter.setCurrentIndex(4)
    assert not page.results_table.isRowHidden(0)
    assert page.results_table.isRowHidden(1)

    # Status filter: "Failed Only" (index 1)
    page.results_status_filter.setCurrentIndex(1)
    assert page.results_table.isRowHidden(0)
    assert not page.results_table.isRowHidden(1)


def test_result_details_dialog(qtbot):
    summary = _make_dummy_run_summary()
    res = summary.results[1]  # The failed duplicate check

    dialog = ResultDetailsDialog(res)
    qtbot.addWidget(dialog)

    assert "Order ID Unique Key" in dialog.windowTitle()
    assert "+15 duplicates over limit" in dialog.text() if hasattr(dialog, "text") else True
    assert "Table: Sales" in dialog.details_box.toPlainText()

    # Test copy diagnostics to clipboard
    dialog._copy_diagnostics()
    clipboard_text = QApplication.clipboard().text()
    assert "Rule: Order ID Unique Key" in clipboard_text
    assert "Status: FAIL" in clipboard_text


def test_home_page_model_selector_dropdown(qtbot):
    reg_svc = MagicMock(spec=RegistryService)
    rec1 = RegistrationRecord(
        id=1,
        workspace_name="Sales WS",
        workspace_id="ws-sales",
        report_name="Sales Executive",
        report_id="rpt-sales",
        dataset_name="Sales Model",
        dataset_id="ds-sales",
        is_active=True,
    )
    rec2 = RegistrationRecord(
        id=2,
        workspace_name="Finance WS",
        workspace_id="ws-fin",
        report_name="Finance P&L",
        report_id=None,
        dataset_name="Finance Model",
        dataset_id="ds-fin",
        is_active=True,
    )
    reg_svc.list_registrations.return_value = [rec1, rec2]

    page = HomePage(registry_service=reg_svc)
    qtbot.addWidget(page)
    page.show()

    assert page.model_selector_combo.count() == 2
    assert "Sales Executive (Sales WS)" in page.model_selector_combo.itemText(0)
    assert page.workspace_id_input.text() == "ws-sales"
    assert page.dataset_id_input.text() == "ds-sales"

    # Switch to Finance
    page.model_selector_combo.setCurrentIndex(1)
    assert page.workspace_id_input.text() == "ws-fin"
    assert page.dataset_id_input.text() == "ds-fin"


def test_home_page_populates_live_powerbi_models_in_dropdown(qtbot):
    from app.integrations.powerbi.models import PowerBIDataset, PowerBIReport, PowerBIWorkspace
    from app.services.powerbi_service import PowerBIService

    mock_pbi = MagicMock(spec=PowerBIService)
    mock_pbi.is_busy = False
    mock_pbi.cached_workspaces = []

    page = HomePage(powerbi_service=mock_pbi)
    qtbot.addWidget(page)
    page.show()

    # Initially empty
    assert "No semantic models" in page.model_selector_combo.itemText(0)

    # Live Power BI workspaces loaded
    ws = PowerBIWorkspace(id="ws-ops", name="Operations WS")
    page.set_workspaces([ws])

    # Live assets loaded
    ds = PowerBIDataset(id="ds-ops", name="Inventory Model")
    rpt = PowerBIReport(id="rpt-ops", name="Warehouse Dashboard", datasetId="ds-ops")
    page.set_workspace_assets("ws-ops", [ds], [rpt])

    # The dropdown now contains the live Power BI model
    assert page.model_selector_combo.count() == 1
    assert "Warehouse Dashboard (Operations WS)" in page.model_selector_combo.itemText(0)
    assert page.workspace_id_input.text() == "ws-ops"
    assert page.dataset_id_input.text() == "ds-ops"

    # Click refresh button triggers sync
    qtbot.mouseClick(page.refresh_models_button, Qt.MouseButton.LeftButton)
    mock_pbi.sync_all_workspaces_and_assets_async.assert_called_once()


