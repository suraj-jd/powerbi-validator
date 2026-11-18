"""UI tests for Stage 6 SearchableComboBox, MetadataSelectorWidget, and SettingsPage discovery."""

from __future__ import annotations

from unittest.mock import MagicMock

from PySide6.QtCore import Qt

from app.integrations.powerbi.models import (
    DatasetMetadata,
    SemanticColumnMetadata,
    SemanticMeasureMetadata,
    SemanticTableMetadata,
)
from app.services.metadata_service import MetadataService
from app.services.registry_service import RegistrationRecord
from app.ui.pages.settings_page import SettingsPage
from app.ui.widgets.metadata_selector_widget import MetadataSelectorWidget
from app.ui.widgets.searchable_combo import SearchableComboBox


def test_searchable_combo_box_selection_and_manual_entry(qtbot) -> None:
    combo = SearchableComboBox()
    qtbot.addWidget(combo)
    combo.show()

    # Populate items
    combo.set_items(["Orders", "Customers", "Products"], placeholder="-- Select Table --")
    assert combo.count() == 4
    assert combo.current_text() == ""

    # Select an item from the list
    combo.setCurrentIndex(1)
    assert combo.current_text() == "Orders"

    # Type a free-form custom name (manual entry fallback)
    combo.set_manual_text("Custom_Fact_Table")
    assert combo.current_text() == "Custom_Fact_Table"


def test_metadata_selector_widget_target_type_toggles_and_dynamic_filtering(qtbot) -> None:
    widget = MetadataSelectorWidget()
    qtbot.addWidget(widget)
    widget.show()

    # Default is Column check: Table and Column visible, Measure hidden
    assert widget.target_type == "column"
    assert widget._table_combo.isVisible()
    assert widget._column_combo.isVisible()
    assert not widget._measure_combo.isVisible()
    assert not widget._model_notice.isVisible()

    # Switch to DAX Measure check: Measure visible, Column hidden
    widget._radio_measure.setChecked(True)
    assert widget.target_type == "measure"
    assert widget._measure_combo.isVisible()
    assert not widget._column_combo.isVisible()

    # Switch to Model / Refresh check: Table/Column/Measure hidden, notice visible
    widget._radio_model.setChecked(True)
    assert widget.target_type == "model"
    assert not widget._table_combo.isVisible()
    assert not widget._column_combo.isVisible()
    assert not widget._measure_combo.isVisible()
    assert widget._model_notice.isVisible()


def test_metadata_selector_widget_applies_metadata_and_validates(qtbot) -> None:
    widget = MetadataSelectorWidget()
    qtbot.addWidget(widget)
    widget.show()

    tbl_orders = SemanticTableMetadata(
        name="Orders",
        columns=[SemanticColumnMetadata(name="OrderID"), SemanticColumnMetadata(name="Sales")],
    )
    tbl_cust = SemanticTableMetadata(
        name="Customers",
        columns=[SemanticColumnMetadata(name="CustID"), SemanticColumnMetadata(name="City")],
    )
    meas = SemanticMeasureMetadata(name="Total Sales", table_name="Measures")

    metadata = DatasetMetadata(
        dataset_id="ds-guid",
        workspace_id="me",
        tables=[tbl_cust, tbl_orders],
        measures=[meas],
        is_supported=True,
    )

    widget.set_active_dataset("me", "ds-guid")
    widget.apply_metadata(metadata)

    # Status pill displays discovered counts
    assert "✓ Discovered (2 tables, 4 cols, 1 measures)" in widget._status_pill.text()

    # Table combo has discovered tables
    assert widget._table_combo.count() == 3  # placeholder + 2 tables

    # Select Orders table -> Column combo dynamically populates OrderID and Sales
    widget._radio_column.setChecked(True)
    widget._table_combo.setCurrentIndex(2)  # Orders
    assert "Orders" in widget.selected_table
    assert widget._column_combo.count() == 3  # placeholder + 2 columns

    # Validate valid target
    widget._column_combo.setCurrentIndex(1)  # OrderID
    is_valid, msg = widget.validate_current_target()
    assert is_valid
    assert "verified" in msg.lower()
    assert "✓" in widget._val_badge.text()

    # Validate invalid target column (typed manually)
    widget._column_combo.set_manual_text("InvalidColumn")
    is_valid, msg = widget.validate_current_target()
    assert not is_valid
    assert "not found" in msg.lower()
    assert "✗" in widget._val_badge.text()


def test_settings_page_integrates_metadata_discovery(qtbot) -> None:
    # Mock registry service with 1 registration
    mock_reg = MagicMock()
    rec = RegistrationRecord(
        id=1,
        workspace_name="Finance Workspace",
        workspace_id="ws-1234",
        report_name="Revenue Report",
        report_id="rep-1234",
        dataset_name="Sales Model",
        dataset_id="ds-5678",
        is_active=True,
    )
    mock_reg.list_registrations.return_value = [rec]

    # Mock metadata client returning discovered model
    tbl = SemanticTableMetadata(name="Sales", columns=[SemanticColumnMetadata(name="Revenue")])
    discovered_meta = DatasetMetadata(
        dataset_id="ds-5678",
        workspace_id="ws-1234",
        tables=[tbl],
        measures=[],
        is_supported=True,
    )
    mock_client = MagicMock()
    mock_client.discover_metadata.return_value = discovered_meta

    meta_service = MetadataService(mock_client)

    page = SettingsPage(registry_service=mock_reg, metadata_service=meta_service)
    qtbot.addWidget(page)
    page.show()

    # Dataset selector combo has registered dataset selected
    assert page.dataset_selector_combo.count() >= 2
    assert "Sales Model" in page.dataset_selector_combo.currentText()

    # Click Discover button on MetadataSelectorWidget
    with qtbot.waitSignal(meta_service.metadata_loaded, timeout=2000):
        qtbot.mouseClick(page.metadata_selector._discover_button, Qt.MouseButton.LeftButton)

    # Metadata applied cleanly to selector widget
    assert "✓ Discovered" in page.metadata_selector._status_pill.text()
    assert page.metadata_selector._table_combo.count() == 2
    assert "Sales" in [page.metadata_selector._table_combo.itemText(i) for i in range(2)]
