"""UI tests for Stage 9 DAX Measure Query Inspector dialog."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from app.database.db import DatabaseManager
from app.integrations.powerbi.dax_client import DaxQueryClient, DaxQueryResult
from app.integrations.powerbi.models import DatasetMetadata, SemanticMeasureMetadata
from app.services.dax_service import DaxQueryService
from app.services.registry_service import RegistrationInput, RegistryService
from app.ui.dialogs.dax_inspector_dialog import DaxInspectorDialog
from app.ui.pages.settings_page import SettingsPage

WS_ID = "11111111-2222-3333-4444-555555555555"
DS_ID = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
RPT_ID = "12345678-1234-1234-1234-1234567890ab"


@pytest.fixture
def db(tmp_path) -> DatabaseManager:
    db_file = tmp_path / "test_dax_ui.db"
    manager = DatabaseManager(db_file)
    manager.run_migrations()
    yield manager
    manager.dispose()


def test_dax_inspector_dialog_probe_and_execute_measure(qtbot) -> None:
    mock_client = MagicMock()
    service = DaxQueryService(mock_client)

    metadata = DatasetMetadata(
        dataset_id=DS_ID,
        workspace_id=WS_ID,
        measures=[
            SemanticMeasureMetadata(name="Total Sales", table_name="Sales"),
            SemanticMeasureMetadata(name="Gross Margin %", table_name="Sales"),
        ],
    )

    dialog = DaxInspectorDialog(
        workspace_id=WS_ID,
        dataset_id=DS_ID,
        display_name="Sales Analytics",
        dax_service=service,
        metadata=metadata,
        preselected_measure="Total Sales",
    )
    qtbot.addWidget(dialog)
    dialog.show()

    # Verify initial query preview
    assert 'EVALUATE ROW("Value", [Total Sales])' in dialog.text_query.toPlainText()

    # 1. Test probe button
    mock_client.execute_raw_dax.return_value = DaxQueryResult(
        is_success=True,
        scalar_value=1,
        is_blank=False,
        value_type="numeric",
        raw_rows=[{"[TestValue]": 1}],
        error_message=None,
        error_code=None,
        duration_ms=45,
        query='EVALUATE ROW("TestValue", 1)',
    )
    dialog.btn_test_probe.click()
    qtbot.waitUntil(lambda: dialog.lbl_value_result.text() == "1", timeout=3000)
    assert "Active" in dialog.lbl_type_pill.text()

    # 2. Test Measure execution returning numeric value
    mock_client.execute_raw_dax.return_value = DaxQueryResult(
        is_success=True,
        scalar_value=5400000,
        is_blank=False,
        value_type="numeric",
        raw_rows=[{"[Value]": 5400000}],
        error_message=None,
        error_code=None,
        duration_ms=120,
        query='EVALUATE ROW("Value", [Total Sales])',
    )
    dialog.btn_run.click()
    qtbot.waitUntil(lambda: dialog.lbl_value_result.text() == "5,400,000", timeout=3000)
    assert "Numeric" in dialog.lbl_type_pill.text()

    # 3. Test Measure execution returning BLANK()
    mock_client.execute_raw_dax.return_value = DaxQueryResult(
        is_success=True,
        scalar_value=None,
        is_blank=True,
        value_type="blank",
        raw_rows=[{"[Value]": None}],
        error_message=None,
        error_code=None,
        duration_ms=90,
        query='EVALUATE ROW("Value", [Total Sales])',
    )
    dialog.btn_run.click()
    qtbot.waitUntil(lambda: dialog.lbl_value_result.text() == "BLANK()", timeout=3000)
    assert "BLANK()" in dialog.lbl_type_pill.text()

    dialog.close()


def test_dax_inspector_dialog_handles_query_error(qtbot) -> None:
    mock_client = MagicMock()
    service = DaxQueryService(mock_client)

    dialog = DaxInspectorDialog(
        workspace_id=WS_ID,
        dataset_id=DS_ID,
        display_name="Sales Analytics",
        dax_service=service,
        preselected_measure="BrokenMeasure",
    )
    qtbot.addWidget(dialog)
    dialog.show()

    mock_client.execute_raw_dax.return_value = DaxQueryResult(
        is_success=False,
        scalar_value=None,
        is_blank=False,
        value_type="error",
        raw_rows=[],
        error_message="The measure 'BrokenMeasure' could not be found.",
        error_code="SemanticError",
        duration_ms=50,
        query="EVALUATE ...",
    )
    dialog.btn_run.click()
    qtbot.waitUntil(lambda: dialog.lbl_value_result.text() == "Error", timeout=3000)
    assert "Failed" in dialog.lbl_type_pill.text()
    assert "BrokenMeasure" in dialog.banner._message_label.text()

    dialog.close()


def test_settings_page_has_inspect_dax_button(qtbot, db: DatabaseManager) -> None:
    registry = RegistryService(db=db)
    mock_client = MagicMock()
    dax_svc = DaxQueryService(mock_client)

    settings = SettingsPage(
        registry_service=registry,
        dax_service=dax_svc,
    )
    qtbot.addWidget(settings)
    settings.show()

    assert hasattr(settings, "inspect_dax_button")
    assert "Inspect Measure DAX" in settings.inspect_dax_button.text()
