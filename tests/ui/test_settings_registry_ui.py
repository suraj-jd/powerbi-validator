"""UI tests for Stage 5 Settings registry table, RegistrationDialog, and ImportRegistrationsDialog."""

from __future__ import annotations

import csv
from pathlib import Path
from unittest.mock import MagicMock

from PySide6.QtCore import Qt

from app.database.db import DatabaseManager
from app.integrations.file_import import TEMPLATE_COLUMNS, RegistrationInput
from app.integrations.powerbi.models import PowerBIDataset, PowerBIReport, PowerBIWorkspace
from app.services.registry_service import RegistryService
from app.ui.dialogs.import_registrations_dialog import ImportRegistrationsDialog
from app.ui.dialogs.quick_add_workspaces_dialog import QuickAddWorkspacesDialog
from app.ui.dialogs.registration_dialog import RegistrationDialog
from app.ui.pages.settings_page import SettingsPage

WS_1 = "11111111-2222-3333-4444-555555555555"
DS_1 = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
RPT_1 = "12345678-1234-1234-1234-1234567890ab"


def test_registration_dialog_validates_fields_and_accepts_valid_input(qtbot) -> None:
    dialog = RegistrationDialog()
    qtbot.addWidget(dialog)

    # Empty / invalid GUID rejected
    dialog.workspace_name_input.setText("Analytics")
    dialog.workspace_id_input.setText("bad-guid")
    dialog.report_name_input.setText("Dashboard")
    dialog.dataset_id_input.setText("bad-dataset-guid")
    qtbot.mouseClick(dialog.save_button, Qt.MouseButton.LeftButton)
    assert dialog.result() != RegistrationDialog.DialogCode.Accepted
    assert not dialog.error_label.isHidden()

    # Valid input accepted
    dialog.workspace_id_input.setText(WS_1)
    dialog.report_id_input.setText(RPT_1)
    dialog.dataset_name_input.setText("HR Semantic Model")
    dialog.dataset_id_input.setText(DS_1)
    qtbot.mouseClick(dialog.save_button, Qt.MouseButton.LeftButton)

    assert dialog.result() == RegistrationDialog.DialogCode.Accepted
    assert dialog.registration_input is not None
    assert dialog.registration_input.workspace_id == WS_1
    assert dialog.registration_input.dataset_id == DS_1


def test_import_dialog_requires_explicit_acknowledgement_for_invalid_rows(
    qtbot,
    tmp_path: Path,
) -> None:
    db = DatabaseManager(tmp_path / "import_ui.db")
    db.run_migrations()
    try:
        registry = RegistryService(db)
        csv_path = tmp_path / "mixed.csv"
        with csv_path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.writer(handle)
            writer.writerow(TEMPLATE_COLUMNS)
            writer.writerow(["Bosch Analytics", WS_1, "Employee Dashboard", RPT_1, "HR", DS_1, "True"])
            writer.writerow(["Broken Row", "not-a-guid", "", "", "", "bad-ds", "True"])

        dialog = ImportRegistrationsDialog(registry)
        qtbot.addWidget(dialog)
        dialog.show()

        dialog.load_file_preview(csv_path)
        assert dialog.preview_table.visible_row_count() == 2
        assert dialog.skip_invalid_checkbox.isVisible()
        # Confirm stays disabled until user explicitly opts to skip invalid rows
        assert not dialog.confirm_button.isEnabled()

        dialog.skip_invalid_checkbox.setChecked(True)
        assert dialog.confirm_button.isEnabled()

        qtbot.mouseClick(dialog.confirm_button, Qt.MouseButton.LeftButton)
        assert dialog.result() == ImportRegistrationsDialog.DialogCode.Accepted
        assert len(dialog.confirmed_rows) == 1
        assert dialog.confirmed_rows[0].workspace_name == "Bosch Analytics"
    finally:
        db.dispose()


def test_settings_page_loads_toggles_and_persists_registrations(
    qtbot,
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "settings_ui.db"
    db1 = DatabaseManager(db_path)
    db1.run_migrations()
    try:
        registry1 = RegistryService(db1)
        registry1.create_registration(
            RegistrationInput(
                workspace_name="Bosch Analytics",
                workspace_id=WS_1,
                report_name="Employee Dashboard",
                report_id=RPT_1,
                dataset_name="HR Model",
                dataset_id=DS_1,
                is_active=True,
            )
        )

        page = SettingsPage(registry_service=registry1)
        qtbot.addWidget(page)
        page.show()

        assert page.registry_table.visible_row_count() == 1
        assert "1 registration(s) (1 active)" in page.count_label.text()

        # Select row 0 and toggle Active -> Inactive
        page.registry_table.table_view.selectRow(0)
        qtbot.mouseClick(page.toggle_active_button, Qt.MouseButton.LeftButton)
        assert "1 registration(s) (0 active)" in page.count_label.text()
    finally:
        db1.dispose()

    # Reopen fresh DB + SettingsPage simulating app restart
    db2 = DatabaseManager(db_path)
    try:
        page2 = SettingsPage(registry_service=RegistryService(db2))
        qtbot.addWidget(page2)
        assert page2.registry_table.visible_row_count() == 1
        assert "1 registration(s) (0 active)" in page2.count_label.text()
    finally:
        db2.dispose()


def test_registration_dialog_autofills_from_powerbi_dropdowns_and_save_another(qtbot) -> None:
    mock_pbi = MagicMock()
    ws_personal = PowerBIWorkspace(id="me", name="My Workspace (Personal)")
    ds_zomato = PowerBIDataset(id=DS_1, name="Zomato")
    rpt_zomato = PowerBIReport(id=RPT_1, name="Zomato Report", dataset_id=DS_1)

    mock_pbi.list_workspaces_sync.return_value = [ws_personal]
    mock_pbi.cached_workspaces = [ws_personal]
    mock_pbi.list_workspace_assets_sync.return_value = ([ds_zomato], [rpt_zomato])

    saved_items: list[RegistrationInput] = []

    dialog = RegistrationDialog(
        powerbi_service=mock_pbi,
        on_save_another=lambda item: saved_items.append(item) or True,
    )
    qtbot.addWidget(dialog)
    dialog.show()

    # Workspace combo has My Workspace
    assert dialog.autofill_ws_combo.count() >= 2
    # Select My Workspace
    dialog.autofill_ws_combo.setCurrentIndex(1)
    assert dialog.workspace_name_input.text() == "My Workspace (Personal)"
    assert dialog.workspace_id_input.text() == "me"

    # Dataset combo has Zomato
    assert dialog.autofill_ds_combo.count() >= 2
    # Select Zomato
    dialog.autofill_ds_combo.setCurrentIndex(1)
    assert dialog.dataset_name_input.text() == "Zomato"
    assert dialog.dataset_id_input.text() == DS_1
    assert dialog.report_name_input.text() == "Zomato Report"
    assert dialog.report_id_input.text() == RPT_1

    # Click "Save & Add Another"
    qtbot.mouseClick(dialog.save_and_add_another_button, Qt.MouseButton.LeftButton)
    assert len(saved_items) == 1
    assert saved_items[0].dataset_name == "Zomato"
    assert saved_items[0].workspace_id == "me"

    # Workspace remains filled, dataset and report fields cleared for next addition
    assert dialog.workspace_name_input.text() == "My Workspace (Personal)"
    assert dialog.dataset_name_input.text() == ""
    assert not dialog.feedback_label.isHidden()
    assert "Saved 'Zomato'" in dialog.feedback_label.text()


def test_quick_add_workspaces_dialog_registers_multiple_datasets(qtbot) -> None:
    mock_pbi = MagicMock()
    ws = PowerBIWorkspace(id="me", name="My Workspace (Personal)")
    ds1 = PowerBIDataset(id=DS_1, name="Zomato")
    ds2 = PowerBIDataset(id="bbbbbbbb-cccc-dddd-eeee-ffffffffffff", name="Superstore")
    rpt1 = PowerBIReport(id=RPT_1, name="Zomato Report", dataset_id=DS_1)

    mock_pbi.list_workspaces_sync.return_value = [ws]
    mock_pbi.cached_workspaces = [ws]
    mock_pbi.list_workspace_assets_sync.return_value = ([ds1, ds2], [rpt1])

    dialog = QuickAddWorkspacesDialog(powerbi_service=mock_pbi)
    qtbot.addWidget(dialog)
    dialog.show()

    assert dialog.table.rowCount() == 2
    assert "Register Selected (2)" in dialog.register_button.text()

    qtbot.mouseClick(dialog.register_button, Qt.MouseButton.LeftButton)
    assert dialog.result() == QuickAddWorkspacesDialog.DialogCode.Accepted
    assert len(dialog.selected_registrations) == 2
    assert dialog.selected_registrations[0].dataset_name == "Zomato"
    assert dialog.selected_registrations[0].report_name == "Zomato Report"
    assert dialog.selected_registrations[1].dataset_name == "Superstore"


def test_settings_page_quick_add_batch_registers_models(qtbot, tmp_path: Path, monkeypatch) -> None:
    from PySide6.QtWidgets import QDialog

    db = DatabaseManager(tmp_path / "batch.db")
    db.run_migrations()
    try:
        registry = RegistryService(db)
        mock_pbi = MagicMock()
        ws = PowerBIWorkspace(id="me", name="My Workspace (Personal)")
        ds1 = PowerBIDataset(id=DS_1, name="Zomato")
        ds2 = PowerBIDataset(id="bbbbbbbb-cccc-dddd-eeee-ffffffffffff", name="Superstore")
        mock_pbi.list_workspaces_sync.return_value = [ws]
        mock_pbi.cached_workspaces = [ws]
        mock_pbi.list_workspace_assets_sync.return_value = ([ds1, ds2], [])

        page = SettingsPage(registry_service=registry, powerbi_service=mock_pbi)
        qtbot.addWidget(page)
        page.show()

        batch_inputs = [
            RegistrationInput(
                workspace_name="My Workspace (Personal)",
                workspace_id="me",
                report_name="Zomato",
                dataset_id=DS_1,
                dataset_name="Zomato",
                is_active=True,
            ),
            RegistrationInput(
                workspace_name="My Workspace (Personal)",
                workspace_id="me",
                report_name="Superstore",
                dataset_id="bbbbbbbb-cccc-dddd-eeee-ffffffffffff",
                dataset_name="Superstore",
                is_active=True,
            ),
        ]

        class FakeDialog:
            def __init__(self, **kwargs):
                self.selected_registrations = batch_inputs

            def exec(self):
                return QDialog.DialogCode.Accepted

        monkeypatch.setattr("app.ui.pages.settings_page.QuickAddWorkspacesDialog", FakeDialog)

        qtbot.mouseClick(page.quick_add_button, Qt.MouseButton.LeftButton)

        assert page.registry_table.visible_row_count() == 2
        assert "2 registration(s) (2 active)" in page.count_label.text()
        assert "Successfully registered 2 semantic model(s)" in page.registry_banner._message_label.text()
    finally:
        db.dispose()
