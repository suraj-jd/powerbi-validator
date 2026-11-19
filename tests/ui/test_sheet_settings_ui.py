"""UI tests for Stage D & E Excel-style SheetSettingsPage and SheetRuleConfigDialog."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QComboBox, QLineEdit, QPushButton

from app.database.db import DatabaseManager
from app.integrations.file_import import RegistrationInput
from app.services.powerbi_service import PowerBIService
from app.services.registry_service import RegistryService
from app.services.rule_service import (
    RuleService,
    VALIDATION_TYPE_DAX_MEASURE,
    VALIDATION_TYPE_DUPLICATE,
    VALIDATION_TYPE_NULL,
    VALIDATION_TYPE_REFRESH,
)
from app.services.sheet_service import SheetRowDTO, SheetService
from app.ui.dialogs.sheet_rule_config_dialog import SheetRuleConfigDialog
from app.ui.pages.sheet_settings_page import SheetSettingsPage

WS_ID = "11111111-2222-3333-4444-555555555555"
DS_ID = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"


@pytest.fixture
def db(tmp_path: Path) -> DatabaseManager:
    db_file = tmp_path / "test_sheet_ui.db"
    manager = DatabaseManager(db_file)
    manager.run_migrations()
    yield manager
    manager.dispose()


@pytest.fixture
def sample_registration(db: DatabaseManager) -> int:
    registry = RegistryService(db=db)
    rec = registry.create_registration(
        RegistrationInput(
            workspace_name="Finance Workspace",
            workspace_id=WS_ID,
            report_name="Revenue Report",
            report_id=None,
            dataset_name="Revenue Model",
            dataset_id=DS_ID,
            is_active=True,
        )
    )
    return rec.id


def test_sheet_rule_config_dialog_null_check(qtbot) -> None:
    dialog = SheetRuleConfigDialog(
        validation_type=VALIDATION_TYPE_NULL,
        target_display="Sales[Amount]",
        current_config={"allowed_blank_count": 0},
        rule_name="Initial Name",
    )
    qtbot.addWidget(dialog)
    dialog.show()

    assert "Null / Blank Check" in dialog.windowTitle()
    assert dialog.null_max_count.value() == 0

    # Modify values
    dialog.null_max_count.setValue(5)
    dialog.null_max_pct.setValue(2.5)
    dialog.rule_name_input.setText("Custom Null Check")

    # Click apply
    qtbot.mouseClick(dialog.apply_button, Qt.MouseButton.LeftButton)

    assert dialog.config["allowed_blank_count"] == 5
    assert dialog.config["allowed_blank_percentage"] == 2.5
    assert dialog.rule_name == "Custom Null Check"


def test_sheet_rule_config_dialog_refresh_sla(qtbot) -> None:
    dialog = SheetRuleConfigDialog(
        validation_type=VALIDATION_TYPE_REFRESH,
        target_display="Revenue Model",
        current_config={"expected_status": "Completed", "max_age_hours": 24},
    )
    qtbot.addWidget(dialog)
    dialog.show()

    assert "Power BI Refresh SLA" in dialog.windowTitle()
    assert dialog.ref_max_age.value() == 24

    dialog.ref_max_age.setValue(12)
    qtbot.mouseClick(dialog.apply_button, Qt.MouseButton.LeftButton)

    assert dialog.config["max_age_hours"] == 12
    assert dialog.config["expected_status"] == "Completed"


def test_sheet_settings_page_initial_ui(qtbot, db: DatabaseManager, sample_registration: int) -> None:
    page = SheetSettingsPage(db=db)
    qtbot.addWidget(page)
    page.show()

    # Ribbon buttons
    assert "Add Row" in page.btn_add_row.text()
    assert "Delete" in page.btn_delete_row.text()
    assert "Save Sheet" in page.btn_save_sheet.text()
    assert "Sync PBI" in page.btn_sync_pbi.text()
    assert "Import..." in page.btn_import.text()
    assert "Export..." in page.btn_export.text()

    # Table columns
    assert page.sheet_table.columnCount() == 9
    assert page.sheet_table.horizontalHeaderItem(0).text() == "Sr."
    assert page.sheet_table.horizontalHeaderItem(2).text() == "Workspace"
    assert page.sheet_table.horizontalHeaderItem(4).text() == "Test to Do"
    assert page.sheet_table.horizontalHeaderItem(7).text() == "Test Rule & Settings ⚙️"


def test_sheet_settings_page_add_and_save_flow(qtbot, db: DatabaseManager, sample_registration: int) -> None:
    page = SheetSettingsPage(db=db)
    qtbot.addWidget(page)
    page.show()

    # 1. Click Add Row
    qtbot.mouseClick(page.btn_add_row, Qt.MouseButton.LeftButton)
    assert page.sheet_table.rowCount() == 1

    # 2. Configure row widgets
    tbl_input = page.sheet_table.cellWidget(0, 5)
    col_input = page.sheet_table.cellWidget(0, 6)
    assert isinstance(tbl_input, (QLineEdit, QComboBox))
    assert isinstance(col_input, (QLineEdit, QComboBox))

    tbl_input.setText("Orders")
    col_input.setText("OrderID")

    # 3. Save Sheet
    qtbot.mouseClick(page.btn_save_sheet, Qt.MouseButton.LeftButton)

    assert "Successfully saved 1 validation test row(s)" in page.banner.text()

    # 4. Reload and verify persistence
    sheet_service = SheetService(db=db)
    rows = sheet_service.load_sheet_rows()
    assert len(rows) == 1
    assert rows[0].table_name == "Orders"
    assert rows[0].column_name == "OrderID"
    assert rows[0].validation_type == VALIDATION_TYPE_NULL


def test_sheet_settings_page_row_deletion(qtbot, db: DatabaseManager, sample_registration: int) -> None:
    sheet_service = SheetService(db=db)
    sheet_service.save_sheet_row(
        SheetRowDTO(
            workspace_id=WS_ID,
            workspace_name="Finance Workspace",
            dataset_id=DS_ID,
            report_name="Revenue Report",
            validation_type=VALIDATION_TYPE_NULL,
            table_name="Customers",
            column_name="CustomerID",
        )
    )

    page = SheetSettingsPage(db=db)
    qtbot.addWidget(page)
    page.show()

    assert page.sheet_table.rowCount() == 1

    # Click row delete button in column 8
    btn_del = page.sheet_table.cellWidget(0, 8)
    assert isinstance(btn_del, QPushButton)
    qtbot.mouseClick(btn_del, Qt.MouseButton.LeftButton)

    assert page.sheet_table.rowCount() == 0
    assert len(sheet_service.load_sheet_rows()) == 0


def test_sheet_settings_page_quick_filter(qtbot, db: DatabaseManager, sample_registration: int) -> None:
    sheet_service = SheetService(db=db)
    sheet_service.save_sheet_row(
        SheetRowDTO(
            workspace_id=WS_ID,
            workspace_name="Finance Workspace",
            dataset_id=DS_ID,
            report_name="Revenue Report",
            validation_type=VALIDATION_TYPE_NULL,
            table_name="Customers",
            column_name="CustomerID",
        )
    )
    sheet_service.save_sheet_row(
        SheetRowDTO(
            workspace_id=WS_ID,
            workspace_name="Finance Workspace",
            dataset_id=DS_ID,
            report_name="Revenue Report",
            validation_type=VALIDATION_TYPE_DUPLICATE,
            table_name="Orders",
            column_name="OrderID",
        )
    )

    page = SheetSettingsPage(db=db)
    qtbot.addWidget(page)
    page.show()

    assert page.sheet_table.rowCount() == 2

    # Filter by "Orders"
    page.search_filter.setText("Orders")
    assert page.sheet_table.isRowHidden(0)
    assert not page.sheet_table.isRowHidden(1)

    # Clear filter
    page.search_filter.setText("")
    assert not page.sheet_table.isRowHidden(0)
    assert not page.sheet_table.isRowHidden(1)


def test_main_window_registers_sheet_settings_tab(qtbot, db: DatabaseManager) -> None:
    from app.core.config import AppConfig
    from app.ui.main_window import MainWindow

    cfg = AppConfig()
    win = MainWindow(config=cfg, db_manager=db)
    qtbot.addWidget(win)

    # Verify sheet settings tab exists in pages
    assert "sheet_settings" in win._pages
    assert hasattr(win, "sheet_settings_page")
    assert win.sheet_settings_page is not None

    # Verify nav button exists
    btn = win._nav_buttons.get("sheet_settings")
    assert btn is not None
    assert "Validation Sheet" in btn.text()

    # Verify legacy settings page is cleanly removed
    assert "settings" not in win._pages
    assert "settings" not in win._nav_buttons


def test_import_sheet_dialog_structure_and_template(qtbot, tmp_path: Path) -> None:
    from app.ui.dialogs.import_sheet_dialog import ImportSheetDialog

    dialog = ImportSheetDialog()
    qtbot.addWidget(dialog)
    dialog.show()

    assert "Import Validation Sheet" in dialog.windowTitle()
    assert dialog.test_selector_combo.count() >= 7

    # Test downloading sample CSV template
    csv_file = tmp_path / "sample.csv"
    saved_path = dialog._download_sample_template(is_xlsx=False, destination=csv_file)
    assert saved_path is not None
    assert csv_file.exists()

    # Directly verify _parse_dict maps correctly
    sample_item = {
        "Workspace Name": "HR Operations",
        "Workspace ID": WS_ID,
        "Report Name": "Staffing",
        "Dataset ID": DS_ID,
        "Table Name": "Employees",
        "Column Name": "EmployeeID",
        "Test to Do": "Duplicate Check",
    }
    dto = dialog._parse_dict(sample_item, forced_test="auto")
    assert dto is not None
    assert dto.workspace_id == WS_ID
    assert dto.dataset_id == DS_ID
    assert dto.table_name == "Employees"
    assert dto.column_name == "EmployeeID"
    assert dto.validation_type == VALIDATION_TYPE_DUPLICATE

    # Test forced test
    dto_forced = dialog._parse_dict(sample_item, forced_test=VALIDATION_TYPE_NULL)
    assert dto_forced is not None
    assert dto_forced.validation_type == VALIDATION_TYPE_NULL


def test_sheet_settings_page_populates_live_workspaces_and_cascades_datasets(qtbot, db: DatabaseManager) -> None:
    from app.integrations.powerbi.models import PowerBIDataset, PowerBIReport, PowerBIWorkspace

    mock_pbi = MagicMock(spec=PowerBIService)
    mock_pbi.is_busy = False
    mock_pbi.cached_workspaces = []

    page = SheetSettingsPage(db=db, powerbi_service=mock_pbi)
    qtbot.addWidget(page)
    page.show()

    ws1 = PowerBIWorkspace(id="ws-1111", name="Finance WS")
    ws2 = PowerBIWorkspace(id="ws-2222", name="Marketing WS")
    page._on_workspaces_loaded([ws1, ws2])

    ds1 = PowerBIDataset(id="ds-1111", name="P&L Model")
    rpt1 = PowerBIReport(id="rpt-1111", name="Income Statement", datasetId="ds-1111")
    page._on_workspace_assets_loaded(ws1.id, [ds1], [rpt1])

    ds2 = PowerBIDataset(id="ds-2222", name="Campaign Model")
    rpt2 = PowerBIReport(id="rpt-2222", name="Ad Performance", datasetId="ds-2222")
    page._on_workspace_assets_loaded(ws2.id, [ds2], [rpt2])

    # Click Add Row
    qtbot.mouseClick(page.btn_add_row, Qt.MouseButton.LeftButton)
    assert page.sheet_table.rowCount() == 1

    ws_combo = page.sheet_table.cellWidget(0, 2)
    ds_combo = page.sheet_table.cellWidget(0, 3)
    assert isinstance(ws_combo, QComboBox)
    assert isinstance(ds_combo, QComboBox)

    # Check that both workspaces are available in the dropdown
    assert ws_combo.count() == 2
    assert "Finance WS" in ws_combo.itemText(0)
    assert "Marketing WS" in ws_combo.itemText(1)

    # By default, first workspace is selected, so dataset combo has Finance report
    assert "Income Statement" in ds_combo.itemText(0)

    # Switch workspace combo to Marketing WS (index 1)
    ws_combo.setCurrentIndex(1)
    # Cascades to Marketing report
    assert "Ad Performance" in ds_combo.itemText(0)

    # Test Sync PBI button triggers sync
    qtbot.mouseClick(page.btn_sync_pbi, Qt.MouseButton.LeftButton)
    mock_pbi.sync_all_workspaces_and_assets_async.assert_called_once()


def test_import_sheet_dialog_demo_table_and_file_selection(qtbot, tmp_path: Path) -> None:
    from app.ui.dialogs.import_sheet_dialog import ImportSheetDialog

    dialog = ImportSheetDialog()
    qtbot.addWidget(dialog)
    dialog.show()

    # Check demo table structure
    assert dialog.demo_table.columnCount() == 8
    assert dialog.demo_table.rowCount() == 3
    assert dialog.demo_table.horizontalHeaderItem(0).text() == "SR"
    assert dialog.demo_table.horizontalHeaderItem(5).text() == "Test to Do"

    # Initially import button is disabled
    assert not dialog.import_button.isEnabled()
    assert dialog.btn_browse.text() == "📁  Choose File (.xlsx, .csv)..."

    # Simulate selecting a valid CSV file
    csv_file = tmp_path / "valid_rules.csv"
    dialog._download_sample_template(is_xlsx=False, destination=csv_file)

    dialog._selected_file = csv_file
    dialog.file_path_input.setText(str(csv_file))
    dialog.import_button.setEnabled(True)

    assert dialog.import_button.isEnabled()
    assert str(csv_file) in dialog.file_path_input.text()


def test_sheet_settings_page_auto_save(qtbot, db: DatabaseManager, sample_registration: int) -> None:
    page = SheetSettingsPage(db=db)
    qtbot.addWidget(page)
    page.show()

    # Verify auto-save timer and status label
    assert hasattr(page, "lbl_auto_save")
    assert "Auto-save active (1 min)" in page.lbl_auto_save.text()
    assert hasattr(page, "_auto_save_timer")
    assert page._auto_save_timer.isActive()
    assert page._auto_save_timer.interval() == 60_000

    # Click Add Row
    qtbot.mouseClick(page.btn_add_row, Qt.MouseButton.LeftButton)
    assert page.sheet_table.rowCount() == 1
    assert page._is_dirty is True
    assert "Unsaved changes" in page.lbl_auto_save.text()

    # Fill in required fields
    tbl_input = page.sheet_table.cellWidget(0, 5)
    col_input = page.sheet_table.cellWidget(0, 6)
    tbl_input.setText("Orders")
    col_input.setText("OrderID")

    # Trigger auto-save handler directly
    page._handle_auto_save()

    assert page._is_dirty is False
    assert "Auto-saved at" in page.lbl_auto_save.text()

    # Verify saved to database
    sheet_service = SheetService(db=db)
    rows = sheet_service.load_sheet_rows()
    assert len(rows) == 1
    assert rows[0].table_name == "Orders"
    assert rows[0].column_name == "OrderID"


def test_sheet_settings_cascading_metadata_dropdowns(qtbot, db: DatabaseManager) -> None:
    from unittest.mock import MagicMock
    from app.integrations.powerbi.models import (
        DatasetMetadata,
        PowerBIDataset,
        PowerBIWorkspace,
        SemanticColumnMetadata,
        SemanticMeasureMetadata,
        SemanticTableMetadata,
    )
    from app.services.metadata_service import MetadataService

    meta = DatasetMetadata(
        dataset_id=DS_ID,
        workspace_id=WS_ID,
        tables=[
            SemanticTableMetadata(
                name="Customers",
                columns=[SemanticColumnMetadata(name="CustomerID"), SemanticColumnMetadata(name="CustomerName")],
            ),
            SemanticTableMetadata(
                name="Orders",
                columns=[SemanticColumnMetadata(name="OrderID"), SemanticColumnMetadata(name="OrderAmount")],
            ),
        ],
        measures=[
            SemanticMeasureMetadata(name="Total Revenue"),
        ],
    )

    mock_meta_svc = MagicMock(spec=MetadataService)
    mock_meta_svc.is_busy = False
    mock_meta_svc.get_cached_metadata.return_value = meta

    mock_pbi = MagicMock(spec=PowerBIService)
    mock_pbi.is_busy = False
    mock_pbi.cached_workspaces = [PowerBIWorkspace(id=WS_ID, name="Finance WS")]
    mock_pbi.get_cached_datasets.return_value = [PowerBIDataset(id=DS_ID, name="Finance Dataset")]
    mock_pbi.get_cached_reports.return_value = []

    page = SheetSettingsPage(db=db, powerbi_service=mock_pbi, metadata_service=mock_meta_svc)
    qtbot.addWidget(page)
    page.show()

    # Add row
    qtbot.mouseClick(page.btn_add_row, Qt.MouseButton.LeftButton)
    assert page.sheet_table.rowCount() == 1

    tbl_combo = page.sheet_table.cellWidget(0, 5)
    col_combo = page.sheet_table.cellWidget(0, 6)
    test_combo = page.sheet_table.cellWidget(0, 4)

    # Tables should be populated from metadata
    assert tbl_combo.count() == 2
    assert tbl_combo.itemText(0) == "Customers"
    assert tbl_combo.itemText(1) == "Orders"

    # Select "Orders" table
    tbl_combo.setCurrentIndex(1)
    assert tbl_combo.currentText() == "Orders"

    # Cascading: Columns should now be populated with Orders columns
    assert col_combo.count() == 2
    assert col_combo.itemText(0) == "OrderID"
    assert col_combo.itemText(1) == "OrderAmount"

    # Switch test to DAX Measure Check
    idx_dax = next(i for i in range(test_combo.count()) if test_combo.itemData(i) == VALIDATION_TYPE_DAX_MEASURE)
    test_combo.setCurrentIndex(idx_dax)

    # Table combo disabled for DAX measure
    assert not tbl_combo.isEnabled()
    # Column/Measure combo should now be populated with discovered measures
    assert col_combo.count() == 1
    assert col_combo.itemText(0) == "[Total Revenue]"





