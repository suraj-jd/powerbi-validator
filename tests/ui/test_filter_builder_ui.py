"""Tests for FilterBuilderDialog and FilterCellWidget in sheet settings."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog, QLineEdit

from app.database.db import DatabaseManager
from app.integrations.powerbi.models import (
    DatasetMetadata,
    SemanticColumnMetadata,
    SemanticTableMetadata,
)
from app.services.registry_service import RegistrationInput, RegistryService
from app.ui.dialogs.filter_builder_dialog import (
    OPERATOR_EQUALS,
    OPERATOR_GREATER_EQUAL,
    OPERATOR_IN,
    OPERATOR_IS_BLANK,
    OPERATOR_IS_NOT_BLANK,
    OPERATOR_NOT_EQUALS,
    OPERATOR_NOT_IN,
    FilterBuilderDialog,
    build_dax_filter_expression,
    escape_dax_column,
    escape_dax_table,
    format_filter_in_list,
    format_filter_scalar_value,
    parse_dax_filter_expression,
)
from app.ui.pages.sheet_settings_page import SheetSettingsPage
from app.ui.widgets.filter_cell_widget import FilterCellWidget


WS_ID = "11111111-2222-3333-4444-555555555555"
DS_ID = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"


@pytest.fixture
def db(tmp_path: Path) -> DatabaseManager:
    db_file = tmp_path / "test_filter_builder.db"
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
        )
    )
    return rec.id


# ---------------------------------------------------------------------------
# 1. Helper function unit tests
# ---------------------------------------------------------------------------


def test_escape_dax_table() -> None:
    assert escape_dax_table("") == ""
    assert escape_dax_table("Sales") == "'Sales'"
    assert escape_dax_table("'Sales'") == "'Sales'"
    assert escape_dax_table("Sales's Data") == "'Sales''s Data'"


def test_escape_dax_column() -> None:
    assert escape_dax_column("") == ""
    assert escape_dax_column("Year") == "[Year]"
    assert escape_dax_column("[Year]") == "[Year]"


def test_format_filter_scalar_value() -> None:
    assert format_filter_scalar_value("2024") == "2024"
    assert format_filter_scalar_value("-50.5") == "-50.5"
    assert format_filter_scalar_value("Active") == '"Active"'
    assert format_filter_scalar_value('"Already Quoted"') == '"Already Quoted"'
    assert format_filter_scalar_value("TRUE") == "TRUE()"
    assert format_filter_scalar_value("FALSE()") == "FALSE()"
    assert format_filter_scalar_value("") == '""'


def test_format_filter_in_list() -> None:
    assert format_filter_in_list("US, UK, CA") == '{ "US", "UK", "CA" }'
    assert format_filter_in_list('1, 2, 3') == "{ 1, 2, 3 }"
    assert format_filter_in_list('{ "Active", "Pending" }') == '{ "Active", "Pending" }'


def test_build_dax_filter_expression_operators() -> None:
    # Equals with number
    assert build_dax_filter_expression("Sales", "Year", "=", "2024") == "'Sales'[Year] = 2024"
    # Equals with string
    assert build_dax_filter_expression("Customer", "Region", "=", "North America") == "'Customer'[Region] = \"North America\""
    # Greater equal
    assert build_dax_filter_expression("Orders", "Amount", ">=", "100") == "'Orders'[Amount] >= 100"
    # IN list
    assert build_dax_filter_expression("Orders", "Status", "IN", "Pending, Shipped") == "'Orders'[Status] IN { \"Pending\", \"Shipped\" }"
    # NOT IN list
    assert build_dax_filter_expression("Orders", "Status", "NOT IN", "Cancelled") == "NOT('Orders'[Status] IN { \"Cancelled\" })"
    # IS BLANK
    assert build_dax_filter_expression("Orders", "Notes", "IS BLANK", "") == "ISBLANK('Orders'[Notes])"
    # IS NOT BLANK
    assert build_dax_filter_expression("Orders", "Notes", "IS NOT BLANK", "") == "NOT(ISBLANK('Orders'[Notes]))"
    # Without table name
    assert build_dax_filter_expression("", "Year", "=", "2025") == "[Year] = 2025"


def test_parse_dax_filter_expression() -> None:
    # Standard equals
    res1 = parse_dax_filter_expression("'Sales'[Year] = 2024")
    assert res1 is not None
    assert res1["table"] == "Sales"
    assert res1["column"] == "Year"
    assert res1["operator"] == "="
    assert res1["value"] == "2024"

    # String comparison
    res2 = parse_dax_filter_expression("'Dim_Customer'[Country] = \"United States\"")
    assert res2 is not None
    assert res2["table"] == "Dim_Customer"
    assert res2["column"] == "Country"
    assert res2["value"] == "United States"

    # IN expression
    res3 = parse_dax_filter_expression("'Orders'[Status] IN { \"Active\", \"Pending\" }")
    assert res3 is not None
    assert res3["table"] == "Orders"
    assert res3["column"] == "Status"
    assert res3["operator"] == OPERATOR_IN

    # NOT IN expression
    res4 = parse_dax_filter_expression("NOT('Orders'[Status] IN { \"Cancelled\" })")
    assert res4 is not None
    assert res4["operator"] == OPERATOR_NOT_IN

    # ISBLANK
    res5 = parse_dax_filter_expression("ISBLANK('Orders'[Notes])")
    assert res5 is not None
    assert res5["operator"] == OPERATOR_IS_BLANK

    # NOT ISBLANK
    res6 = parse_dax_filter_expression("NOT(ISBLANK('Orders'[Notes]))")
    assert res6 is not None
    assert res6["operator"] == OPERATOR_IS_NOT_BLANK

    # Complex expression falls back to None (for custom DAX mode)
    assert parse_dax_filter_expression("YEAR('Dates'[Date]) = 2024 && [Sales] > 100") is None


# ---------------------------------------------------------------------------
# 2. FilterBuilderDialog UI tests
# ---------------------------------------------------------------------------


def test_filter_builder_dialog_visual_flow(qtbot) -> None:
    dialog = FilterBuilderDialog(
        filter_index=1,
        table_name="Sales",
        parent=None,
    )
    qtbot.addWidget(dialog)
    dialog.show()

    dialog.combo_table.setEditText("Orders")
    dialog.combo_column.setEditText("Status")
    dialog.input_value.setText("Completed")

    assert dialog.lbl_preview_code.text() == "'Orders'[Status] = \"Completed\""

    # Switch operator to IS BLANK
    idx = dialog.combo_operator.findData(OPERATOR_IS_BLANK)
    dialog.combo_operator.setCurrentIndex(idx)
    assert not dialog.input_value.isEnabled()
    assert dialog.lbl_preview_code.text() == "ISBLANK('Orders'[Status])"

    # Switch operator to IN
    idx_in = dialog.combo_operator.findData(OPERATOR_IN)
    dialog.combo_operator.setCurrentIndex(idx_in)
    assert dialog.input_value.isEnabled()
    dialog.input_value.setText("Pending, Shipped")
    assert dialog.lbl_preview_code.text() == "'Orders'[Status] IN { \"Pending\", \"Shipped\" }"

    # Apply
    qtbot.mouseClick(dialog.btn_apply, Qt.MouseButton.LeftButton)
    assert dialog.result() == QDialog.DialogCode.Accepted
    assert dialog.generated_expression == "'Orders'[Status] IN { \"Pending\", \"Shipped\" }"


def test_filter_builder_dialog_clear_flow(qtbot) -> None:
    dialog = FilterBuilderDialog(
        filter_index=2,
        current_expression="'Sales'[Year] = 2024",
        parent=None,
    )
    qtbot.addWidget(dialog)
    dialog.show()

    assert dialog.combo_table.currentText() == "Sales"
    assert dialog.combo_column.currentText() == "Year"
    assert dialog.input_value.text() == "2024"

    # Click Clear Filter
    qtbot.mouseClick(dialog.btn_clear, Qt.MouseButton.LeftButton)
    assert dialog.result() == QDialog.DialogCode.Accepted
    assert dialog.generated_expression == ""


def test_filter_builder_dialog_custom_dax_flow(qtbot) -> None:
    dialog = FilterBuilderDialog(
        filter_index=3,
        parent=None,
    )
    qtbot.addWidget(dialog)
    dialog.show()

    # Check custom DAX checkbox
    dialog.chk_custom_dax.setChecked(True)
    assert dialog.input_custom_dax.isVisible()
    assert not dialog.combo_table.isEnabled()

    dialog.input_custom_dax.setText("YEAR('Dates'[Date]) = 2024")
    assert dialog.lbl_preview_code.text() == "YEAR('Dates'[Date]) = 2024"

    qtbot.mouseClick(dialog.btn_apply, Qt.MouseButton.LeftButton)
    assert dialog.result() == QDialog.DialogCode.Accepted
    assert dialog.generated_expression == "YEAR('Dates'[Date]) = 2024"


def test_filter_builder_dialog_metadata_cascading(qtbot) -> None:
    # Mock metadata service
    meta_service = MagicMock()
    mock_meta = DatasetMetadata(
        workspace_id="ws-1",
        dataset_id="ds-1",
        tables=[
            SemanticTableMetadata(
                name="Customers",
                columns=[
                    SemanticColumnMetadata(name="CustomerID"),
                    SemanticColumnMetadata(name="CustomerName"),
                    SemanticColumnMetadata(name="Country"),
                ],
            ),
            SemanticTableMetadata(
                name="Orders",
                columns=[
                    SemanticColumnMetadata(name="OrderID"),
                    SemanticColumnMetadata(name="OrderDate"),
                    SemanticColumnMetadata(name="Amount"),
                ],
            ),
        ],
    )
    meta_service.get_cached_metadata.return_value = mock_meta

    dialog = FilterBuilderDialog(
        filter_index=1,
        workspace_id="ws-1",
        dataset_id="ds-1",
        metadata_service=meta_service,
        parent=None,
    )
    qtbot.addWidget(dialog)
    dialog.show()

    assert dialog.combo_table.count() >= 2
    # Select Customers
    dialog.combo_table.setCurrentIndex(dialog.combo_table.findText("Customers"))
    assert dialog.combo_column.count() == 3
    assert dialog.combo_column.findText("Country") >= 0

    # Select Orders
    dialog.combo_table.setCurrentIndex(dialog.combo_table.findText("Orders"))
    assert dialog.combo_column.count() == 3
    assert dialog.combo_column.findText("Amount") >= 0


# ---------------------------------------------------------------------------
# 3. FilterCellWidget UI tests
# ---------------------------------------------------------------------------


def test_filter_cell_widget_button_state_and_interaction(qtbot) -> None:
    cell = FilterCellWidget(filter_index=1)
    qtbot.addWidget(cell)
    cell.show()

    # Empty cell -> Bold "Add"
    assert cell.btn_add.text() == "Add"
    assert cell.btn_add.isVisible()

    # Populate cell -> Bold "Edit"
    cell.setText("'Sales'[Year] = 2024")
    assert cell.btn_add.text() == "Edit"

    # Clear cell -> Switches back to "Add"
    cell.setText("")
    assert cell.btn_add.text() == "Add"

    # Disabled cell -> Hides button
    cell.setEnabled(False)
    assert not cell.btn_add.isVisible()

    cell.setEnabled(True)
    assert cell.btn_add.isVisible()


def test_sheet_settings_filter_cell_add_button_opens_dialog(
    qtbot, db: DatabaseManager, sample_registration: int, monkeypatch
) -> None:
    page = SheetSettingsPage(db=db)
    qtbot.addWidget(page)
    page.show()

    # Add row
    qtbot.mouseClick(page.btn_add_row, Qt.MouseButton.LeftButton)
    assert page.sheet_table.rowCount() == 1

    f1_cell = page.sheet_table.cellWidget(0, 8)
    assert isinstance(f1_cell, FilterCellWidget)
    assert f1_cell.btn_add.text() == "Add"

    # Mock FilterBuilderDialog.exec to simulate user applying filter in popup
    def mock_exec(self):
        self._result_expression = "'Orders'[Status] = \"Completed\""
        return 1

    monkeypatch.setattr(FilterBuilderDialog, "exec", mock_exec)

    # Click bold "Add" button
    qtbot.mouseClick(f1_cell.btn_add, Qt.MouseButton.LeftButton)

    # Verify cell text was updated and button changed to "Edit"
    assert f1_cell.text() == "'Orders'[Status] = \"Completed\""
    assert f1_cell.btn_add.text() == "Edit"

    # Verify page was marked dirty (Save button enabled)
    assert page.btn_save_sheet.isEnabled()
