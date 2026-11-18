"""UI tests for Stage 1 shared widgets, confirmation dialog, About page, and bootstrap."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt

from app.bootstrap import bootstrap_application
from app.core.status import NotificationLevel, ValidationStatus
from app.ui.dialogs.confirm_dialog import ConfirmDialog
from app.ui.models.dict_table_model import ColumnSpec
from app.ui.pages.about_page import AboutPage
from app.ui.widgets.data_table import DataTableWidget
from app.ui.widgets.notification_banner import NotificationBanner


def test_notification_banner_shows_and_dismisses(qtbot) -> None:
    banner = NotificationBanner()
    qtbot.addWidget(banner)

    assert not banner.isVisible()

    banner.show_message("Saved successfully", level=NotificationLevel.SUCCESS, title="Done")
    assert banner.isVisible()
    assert banner.current_level == NotificationLevel.SUCCESS
    assert banner.current_message == "Saved successfully"

    qtbot.mouseClick(banner._dismiss_button, Qt.MouseButton.LeftButton)
    assert not banner.isVisible()
    assert banner.current_message == ""


def test_notification_banner_post_message_signal(qtbot) -> None:
    banner = NotificationBanner()
    qtbot.addWidget(banner)

    banner.post_message("Worker error occurred", level=NotificationLevel.ERROR)
    assert banner.isVisible()
    assert banner.current_level == NotificationLevel.ERROR
    assert banner.current_message == "Worker error occurred"


def test_data_table_widget_filters_and_emits_row_activated(qtbot) -> None:
    columns = [
        ColumnSpec(key="sr", header="SR"),
        ColumnSpec(key="check", header="Check"),
        ColumnSpec(key="status", header="Status", is_status=True),
    ]
    rows = [
        {"sr": 1, "check": "Null Check", "status": ValidationStatus.PASS.value},
        {"sr": 2, "check": "Duplicate Check", "status": ValidationStatus.FAIL.value},
    ]
    table = DataTableWidget(
        columns=columns,
        rows=rows,
        show_search=True,
        filter_column_key="status",
        filter_options=[ValidationStatus.PASS.value, ValidationStatus.FAIL.value],
    )
    qtbot.addWidget(table)
    table.show()

    assert table.visible_row_count() == 2

    assert table.search_input is not None
    table.search_input.setText("duplicate")
    assert table.visible_row_count() == 1

    table.search_input.clear()
    assert table.filter_combo is not None
    table.filter_combo.setCurrentText(ValidationStatus.PASS.value)
    assert table.visible_row_count() == 1

    activated: list[dict] = []
    table.row_activated.connect(activated.append)
    first_index = table.proxy_model.index(0, 0)
    table._on_double_clicked(first_index)
    assert len(activated) == 1
    assert activated[0]["check"] == "Null Check"


def test_confirm_dialog_accept_and_reject(qtbot) -> None:
    dialog = ConfirmDialog(
        title="Delete Rule",
        message="Are you sure you want to delete this rule?",
        detail="This action cannot be undone.",
        confirm_text="Delete",
        destructive=True,
    )
    qtbot.addWidget(dialog)
    assert dialog.confirm_button.objectName() == "DangerButton"

    qtbot.mouseClick(dialog.cancel_button, Qt.MouseButton.LeftButton)
    assert dialog.result() == ConfirmDialog.DialogCode.Rejected

    dialog2 = ConfirmDialog(title="Save", message="Save changes?")
    qtbot.addWidget(dialog2)
    assert dialog2.confirm_button.objectName() == "PrimaryButton"
    qtbot.mouseClick(dialog2.confirm_button, Qt.MouseButton.LeftButton)
    assert dialog2.result() == ConfirmDialog.DialogCode.Accepted


def test_about_page_shared_component_demo(qtbot, tmp_path: Path) -> None:
    page = AboutPage(logs_dir=tmp_path / "logs")
    qtbot.addWidget(page)
    page.show()

    assert page.demo_table.visible_row_count() == 5
    assert not page.demo_banner.isVisible()

    qtbot.mouseClick(page.demo_notify_btn, Qt.MouseButton.LeftButton)
    assert page.demo_banner.isVisible()
    assert page.demo_banner.current_level == NotificationLevel.INFO


def test_bootstrap_application_initializes_config_logs_and_window(qtbot, tmp_path: Path) -> None:
    ctx = bootstrap_application(argv=[], data_dir=tmp_path, install_hooks=False)
    try:
        qtbot.addWidget(ctx.window)
        ctx.window.show()

        assert (tmp_path / "config.json").exists()
        assert ctx.log_file.exists()
        assert ctx.db_path.exists()
        assert ctx.db.get_current_revision() == "20261118_0001"
        assert ctx.window.current_page_key == "home"

        ctx.window.show_notification("Bootstrap check", level=NotificationLevel.SUCCESS)
        assert ctx.window.notification_banner.isVisible()
    finally:
        ctx.db.dispose()
