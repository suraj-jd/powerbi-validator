"""UI unit tests for Stage 7 Validation Rule Editor, Advanced Settings, and Rules Table."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog

from app.database.db import DatabaseManager
from app.integrations.file_import import RegistrationInput
from app.integrations.powerbi.models import (
    DatasetMetadata,
    SemanticColumnMetadata,
    SemanticMeasureMetadata,
    SemanticTableMetadata,
)
from app.services.registry_service import RegistryService
from app.services.rule_service import (
    TARGET_TYPE_COLUMN,
    TARGET_TYPE_MEASURE,
    TARGET_TYPE_MODEL,
    VALIDATION_TYPE_ANOMALY,
    VALIDATION_TYPE_DAX_MEASURE,
    VALIDATION_TYPE_DUPLICATE,
    VALIDATION_TYPE_NULL,
    VALIDATION_TYPE_REFRESH,
    VALIDATION_TYPE_ROW_COUNT,
    RuleInput,
    RuleRecord,
    RuleService,
)
from app.ui.dialogs.advanced_settings_dialog import AdvancedSettingsDialog
from app.ui.dialogs.rule_editor_dialog import RuleEditorDialog
from app.ui.pages.settings_page import SettingsPage
from app.ui.widgets.rules_table_widget import ValidationRulesTableWidget

WS_ID = "22222222-3333-4444-5555-666666666666"
DS_ID = "bbbbbbbb-cccc-dddd-eeee-ffffffffffff"


@pytest.fixture
def db(tmp_path: Path):
    manager = DatabaseManager(tmp_path / "test_rules_ui.db")
    manager.run_migrations()
    try:
        yield manager
    finally:
        manager.dispose()


@pytest.fixture
def sample_registration_id(db: DatabaseManager) -> int:
    registry = RegistryService(db)
    rec = registry.create_registration(
        RegistrationInput(
            workspace_name="Analytics Workspace",
            workspace_id=WS_ID,
            report_name="Sales Executive",
            report_id=None,
            dataset_name="Retail Sales",
            dataset_id=DS_ID,
            is_active=True,
        )
    )
    return rec.id


def test_rule_editor_dialog_target_toggles_and_validations(qtbot) -> None:
    meta = DatasetMetadata(
        dataset_id=DS_ID,
        workspace_id=WS_ID,
        tables=[
            SemanticTableMetadata(name="Orders", columns=[SemanticColumnMetadata(name="OrderID")]),
            SemanticTableMetadata(name="Customers", columns=[SemanticColumnMetadata(name="CustomerID")]),
        ],
        measures=[
            SemanticMeasureMetadata(name="Total Sales"),
            SemanticMeasureMetadata(name="Gross Margin"),
        ],
        is_supported=True,
    )

    dlg = RuleEditorDialog(
        workspace_registration_id=1,
        registration_display_name="Retail Sales",
        metadata=meta,
    )
    qtbot.addWidget(dlg)
    dlg.show()

    # Initial state: Column check
    assert dlg.radio_column.isChecked()
    assert dlg.table_combo.isVisible()
    assert dlg.column_combo.isVisible()
    assert not dlg.measure_combo.isVisible()
    assert not dlg.model_notice.isVisible()

    # Switch to DAX Measure
    dlg.radio_measure.setChecked(True)
    assert not dlg.column_combo.isVisible()
    assert dlg.measure_combo.isVisible()
    assert dlg.measure_combo.count() >= 3  # placeholder + 2 measures

    # Switch to Model / Refresh Check
    dlg.radio_model.setChecked(True)
    assert not dlg.table_combo.isVisible()
    assert not dlg.column_combo.isVisible()
    assert not dlg.measure_combo.isVisible()
    assert dlg.model_notice.isVisible()

    # Attempt save with empty rule name -> error shown
    qtbot.mouseClick(dlg.save_button, Qt.MouseButton.LeftButton)
    assert not dlg.error_label.isHidden()
    assert "Rule name cannot be empty" in dlg.error_label.text()

    # Enter rule name for refresh check -> succeeds
    dlg.rule_name_input.setText("Semantic Model Refresh Check")
    qtbot.mouseClick(dlg.save_button, Qt.MouseButton.LeftButton)
    assert dlg.result() == QDialog.DialogCode.Accepted
    assert dlg.rule_input is not None
    assert dlg.rule_input.rule_name == "Semantic Model Refresh Check"
    assert dlg.rule_input.target_type == TARGET_TYPE_MODEL
    assert dlg.rule_input.validation_type == VALIDATION_TYPE_REFRESH


def test_advanced_settings_dialog_isolation_and_save(qtbot) -> None:
    initial_config = {"allowed_blank_count": 0, "filter_condition": ""}

    dlg = AdvancedSettingsDialog(
        rule_name="Customer Email Not Null",
        validation_type=VALIDATION_TYPE_NULL,
        current_config=initial_config,
    )
    qtbot.addWidget(dlg)
    dlg.show()

    # Change allowed blanks and filter
    dlg.spin_blank_count.setValue(5)
    dlg.edit_filter.setText('[IsGuest] = FALSE')
    qtbot.mouseClick(dlg.save_button, Qt.MouseButton.LeftButton)

    assert dlg.result() == QDialog.DialogCode.Accepted
    result_cfg = dlg.config
    assert result_cfg["allowed_blank_count"] == 5
    assert result_cfg["filter_condition"] == '[IsGuest] = FALSE'
    # Verify initial config was NOT mutated (isolation)
    assert initial_config["allowed_blank_count"] == 0


def test_rules_table_widget_crud_duplicate_reorder(qtbot, db: DatabaseManager, sample_registration_id: int) -> None:
    rule_service = RuleService(db)
    table_widget = ValidationRulesTableWidget(rule_service=rule_service)
    qtbot.addWidget(table_widget)
    table_widget.show()

    table_widget.set_registration(sample_registration_id, "Retail Sales")
    assert table_widget.table.rowCount() == 0

    # 1. Add rule programmatically through service & refresh
    r1 = rule_service.create_rule(
        RuleInput(
            workspace_registration_id=sample_registration_id,
            rule_name="OrderID Unique",
            target_type=TARGET_TYPE_COLUMN,
            validation_type=VALIDATION_TYPE_DUPLICATE,
            table_name="Orders",
            column_name="OrderID",
            config={"allowed_duplicate_count": 0},
        )
    )
    r2 = rule_service.create_rule(
        RuleInput(
            workspace_registration_id=sample_registration_id,
            rule_name="Total Revenue Range",
            target_type=TARGET_TYPE_MEASURE,
            validation_type=VALIDATION_TYPE_DAX_MEASURE,
            measure_name="Total Revenue",
            config={"expected_method": "min_max", "min_value": 100, "max_value": 500},
        )
    )
    table_widget.refresh_rules()
    assert table_widget.table.rowCount() == 2
    assert "2 rule(s) (2 enabled)" in table_widget.count_badge.text()

    # 2. Duplicate rule 0
    table_widget.table.selectRow(0)
    qtbot.mouseClick(table_widget.duplicate_button, Qt.MouseButton.LeftButton)
    assert table_widget.table.rowCount() == 3
    assert "OrderID Unique (Copy)" in table_widget.table.item(1, 2).text()

    # 3. Toggle enabled on rule 0
    table_widget.table.selectRow(0)
    qtbot.mouseClick(table_widget.toggle_button, Qt.MouseButton.LeftButton)
    assert "✗ No" in table_widget.table.item(0, 1).text()
    assert "2 enabled" in table_widget.count_badge.text()

    # 4. Move Down rule 0
    table_widget.table.selectRow(0)
    qtbot.mouseClick(table_widget.move_down_button, Qt.MouseButton.LeftButton)
    # The swapped rule should now be in row 1
    assert "OrderID Unique" in table_widget.table.item(1, 2).text()

    # 5. Delete rule 0
    table_widget.table.selectRow(0)
    import app.ui.widgets.rules_table_widget as rtw_mod
    orig_ask = rtw_mod.ConfirmDialog.ask
    rtw_mod.ConfirmDialog.ask = lambda *args, **kwargs: True
    try:
        qtbot.mouseClick(table_widget.delete_button, Qt.MouseButton.LeftButton)
    finally:
        rtw_mod.ConfirmDialog.ask = orig_ask

    assert table_widget.table.rowCount() == 2


def test_settings_page_integrates_rules_configuration(qtbot, db: DatabaseManager, sample_registration_id: int) -> None:
    registry_svc = RegistryService(db)
    rule_svc = RuleService(db)

    # Pre-populate 1 rule
    rule_svc.create_rule(
        RuleInput(
            workspace_registration_id=sample_registration_id,
            rule_name="Daily Refresh Monitor",
            target_type=TARGET_TYPE_MODEL,
            validation_type=VALIDATION_TYPE_REFRESH,
            config={"expected_status": "Completed", "max_age_hours": 24},
        )
    )

    page = SettingsPage(registry_service=registry_svc, rule_service=rule_svc)
    qtbot.addWidget(page)
    page.show()

    # Check Stage Badge
    stage_badges = [lbl for lbl in page.findChildren(object, "StageBadge")]
    assert any("Stage" in b.text() for b in stage_badges)

    # Section 3 rules table is loaded with the registered model's rule
    assert page.rules_table.table.rowCount() == 1
    assert page.rules_table.table.item(0, 2).text() == "Daily Refresh Monitor"
    assert page.rules_table.table.item(0, 3).text() == "Model / Refresh"
    assert "status = Completed" in page.rules_table.table.item(0, 7).text()
