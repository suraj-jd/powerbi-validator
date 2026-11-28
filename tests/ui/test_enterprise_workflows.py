"""Behavior and persistence checks for the enterprise presentation."""

from unittest.mock import MagicMock

from PySide6.QtCore import Qt

from app.database.db import DatabaseManager
from app.services.sheet_service import SheetRowDTO, SheetService
from app.ui.dialogs.import_sheet_dialog import ImportSheetDialog
from app.ui.pages.home_page import HomePage
from app.ui.pages.sheet_settings_page import SheetSettingsPage
from tests.ui.test_dashboard_ui import _make_dummy_run_summary


def test_sorted_results_open_and_filter_the_correct_check(qtbot):
    page = HomePage()
    qtbot.addWidget(page)
    results = _make_dummy_run_summary().results
    page._populate_results_table(results)
    page.results_table.sortItems(1, Qt.SortOrder.AscendingOrder)
    assert page.results_table.result_at(0).id == results[1].id
    page._open_result_details = MagicMock()
    page._handle_table_clicked(0, 9)
    page._open_result_details.assert_called_once_with(results[1])
    page.results_search_input.setText("Sales Amount")
    assert page.results_table.isRowHidden(0)
    assert not page.results_table.isRowHidden(1)
    page.results_search_input.setText("no matching check")
    assert "Showing 0 of 2" in page.results_count_label.text()


def _saved_sheet(tmp_path):
    db = DatabaseManager(tmp_path / "enterprise.db")
    db.run_migrations()
    SheetService(db).save_all_rows([SheetRowDTO(
        sr_no=1, workspace_name="QA workspace", workspace_id="me", report_name="QA report",
        dataset_name="QA model", dataset_id="aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
        table_name="Orders", column_name="OrderID", validation_type="null_check",
        rule_name="Order ID complete", config={"allowed_blank_count": 0},
    )])
    return db


def test_sheet_keeps_unsaved_changes_when_returning_to_page(qtbot, tmp_path):
    db = _saved_sheet(tmp_path)
    page = SheetSettingsPage(db=db)
    qtbot.addWidget(page)
    page.show()
    page._rows[0].rule_name = "Unsaved label"
    page._mark_dirty()
    page.hide()
    page.show()
    assert page._rows[0].rule_name == "Unsaved label"
    assert SheetService(db).load_sheet_rows()[0].rule_name == "Order ID complete"
    page.close()
    db.dispose()


def test_side_editor_cancel_and_apply_then_save(qtbot, tmp_path):
    db = _saved_sheet(tmp_path)
    page = SheetSettingsPage(db=db)
    page.resize(1500, 900)
    qtbot.addWidget(page)
    page.show()
    row = page._rows[0]
    button = page.sheet_table.cellWidget(0, 11)
    page._open_gear_dialog(button, row)
    editor = page._inline_check_editor
    assert not page.check_editor_panel.isHidden()
    assert page.check_editor_panel.rect().contains(editor.cancel_button.mapTo(page.check_editor_panel, editor.cancel_button.rect().center()))
    editor.null_max_count.setValue(7)
    editor.reject()
    assert row.config["allowed_blank_count"] == 0
    assert page.sheet_table.isEnabled()
    page._open_gear_dialog(button, row)
    editor = page._inline_check_editor
    editor.null_max_count.setValue(3)
    editor.apply_button.click()
    assert row.config["allowed_blank_count"] == 3
    assert page._is_dirty
    assert SheetService(db).load_sheet_rows()[0].config["allowed_blank_count"] == 0
    page._handle_save_sheet()
    assert SheetService(db).load_sheet_rows()[0].config["allowed_blank_count"] == 3
    page.close()
    db.dispose()


def test_failed_sheet_save_retains_edits_for_retry(qtbot, tmp_path, monkeypatch):
    db = _saved_sheet(tmp_path)
    page = SheetSettingsPage(db=db)
    qtbot.addWidget(page)
    page._rows[0].rule_name = "Retry this edit"
    page._mark_dirty()
    real_save = page._sheet_service.save_all_rows
    def fail_save(_rows):
        raise RuntimeError("Temporary storage failure")
    monkeypatch.setattr(page._sheet_service, "save_all_rows", fail_save)
    page._handle_save_sheet()
    assert page._is_dirty
    assert "Save failed" in page.lbl_auto_save.text()
    assert page._rows[0].rule_name == "Retry this edit"
    monkeypatch.setattr(page._sheet_service, "save_all_rows", real_save)
    page._handle_save_sheet()
    assert SheetService(db).load_sheet_rows()[0].rule_name == "Retry this edit"
    assert not page._is_dirty
    page.close()
    db.dispose()


def test_import_preview_states_exact_effect_and_cancel_does_not_import(qtbot, tmp_path):
    source = tmp_path / "checks.csv"
    source.write_text("Workspace ID,Dataset ID,Table Name,Column Name\nme,model-1,Orders,OrderID\nme,,Orders,OrderID\n", encoding="utf-8")
    dialog = ImportSheetDialog()
    qtbot.addWidget(dialog)
    dialog._selected_file = source
    assert dialog._load_import_preview()
    assert dialog.demo_table.rowCount() == 1
    assert "1 valid checks" in dialog.preview_title.text()
    assert "1 skipped rows" in dialog.preview_title.text()
    dialog.reject()
    assert dialog.imported_rows == []


def test_import_rechecks_a_file_changed_after_preview(qtbot, tmp_path):
    source = tmp_path / "checks.csv"
    source.write_text("Workspace ID,Dataset ID\nme,model-1\n", encoding="utf-8")
    dialog = ImportSheetDialog()
    qtbot.addWidget(dialog)
    dialog._selected_file = source
    assert dialog._load_import_preview()
    source.write_text("Workspace ID,Dataset ID\nme,model-1\nme,model-2\n", encoding="utf-8")
    dialog._handle_execute_import()
    assert dialog.imported_rows == []
    assert "2 valid checks" in dialog.preview_title.text()
    dialog._handle_execute_import()
    assert len(dialog.imported_rows) == 2


def test_history_gives_most_of_the_page_to_tables(qtbot):
    from app.ui.pages.history_page import HistoryPage
    page = HistoryPage()
    qtbot.addWidget(page)
    page.resize(1600, 900)
    page.show()
    qtbot.waitUntil(lambda: page.tables_splitter.height() > 100)
    assert page.tables_splitter.height() >= page.height() * 0.65
    assert page.advanced_filters.isHidden()


def test_overview_keeps_settings_near_run_and_refresh_inspection_optional(qtbot):
    page = HomePage()
    qtbot.addWidget(page)
    page.show()
    assert page.schedule_validation_button.parentWidget() is page.overview_header
    assert page.teams_alerts_button.parentWidget() is page.overview_header
    assert not page.refresh_card.isVisible()
    assert not hasattr(page, "refresh_monitor_toggle")
