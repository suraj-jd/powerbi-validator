"""UI tests for ScheduleValidationDialog and HomePage scheduler controls."""

from __future__ import annotations

from unittest.mock import MagicMock, patch
from datetime import datetime

import pytest
from PySide6.QtCore import QPoint, Qt, QTime
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from app.services.orchestrator_service import OrchestratorService
from app.services.registry_service import RegistryService
from app.services.rule_service import RuleService
from app.services.scheduler_service import ScheduleConfig, ValidationSchedulerService
from app.ui.dialogs.schedule_validation_dialog import ScheduleValidationDialog
from app.ui.pages.home_page import HomePage


def test_schedule_dialog_blocks_when_zero_rules(qtbot):
    svc = ValidationSchedulerService(db=None)
    dlg = ScheduleValidationDialog(scheduler_service=svc, rule_count=0)
    qtbot.addWidget(dlg)

    assert dlg.chk_enabled.isEnabled() is False
    assert dlg.btn_save.isEnabled() is False
    assert "0 rules configured" in dlg.lbl_sheet_msg.text()


def test_schedule_dialog_allows_configuration_when_rules_exist(qtbot):
    svc = ValidationSchedulerService(db=None)
    dlg = ScheduleValidationDialog(scheduler_service=svc, rule_count=5)
    qtbot.addWidget(dlg)

    assert dlg.chk_enabled.isEnabled() is True
    assert dlg.btn_save.isEnabled() is True
    assert "5 rule(s) configured" in dlg.lbl_sheet_msg.text()

    # Enable scheduler
    dlg.chk_enabled.setChecked(True)
    assert dlg.settings_card.isEnabled() is True

    # Test adding a time
    initial_count = len(dlg._times)
    dlg.time_input.setTime(QTime(23, 30))
    dlg._add_selected_time()
    assert "23:30" in dlg._times
    assert len(dlg._times) == initial_count + 1

    # Test removing a time
    dlg._remove_time("23:30")
    assert "23:30" not in dlg._times

    # Test saving
    dlg._save_schedule()
    assert svc.config.enabled is True


def test_schedule_dialog_saves_exact_minutes_and_custom_interval(qtbot, tmp_path):
    from app.database.db import DatabaseManager

    db = DatabaseManager(tmp_path / "schedule.db")
    db.run_migrations()
    svc = ValidationSchedulerService(db=db)
    dlg = ScheduleValidationDialog(scheduler_service=svc, rule_count=1)
    qtbot.addWidget(dlg)
    dlg.chk_enabled.setChecked(True)
    for hour, minute in [(0, 1), (9, 17), (23, 59), (9, 17)]:
        dlg.time_input.setTime(QTime(hour, minute))
        dlg.btn_add_time.click()
    dlg._save_schedule()
    reloaded = ValidationSchedulerService(db=db)
    assert reloaded.config.times == ["00:01", "09:00", "09:17", "13:00", "18:00", "23:59"]

    interval_dialog = ScheduleValidationDialog(scheduler_service=reloaded, rule_count=1)
    qtbot.addWidget(interval_dialog)
    interval_dialog.combo_frequency.setCurrentIndex(1)
    interval_dialog.spin_interval.setValue(7)
    assert "every 7m" in interval_dialog.lbl_preview_summary.text()
    interval_dialog._save_schedule()
    interval_service = ValidationSchedulerService(db=db)
    assert interval_service.config.mode == "interval"
    assert interval_service.config.interval_minutes == 7
    for service in (svc, reloaded, interval_service):
        service._timer.stop()
    db.dispose()


def test_schedule_dialog_requires_a_time_when_daily_enabled(qtbot):
    svc = ValidationSchedulerService(db=None)
    dlg = ScheduleValidationDialog(scheduler_service=svc, rule_count=1)
    qtbot.addWidget(dlg)
    dlg.chk_enabled.setChecked(True)
    for time_string in list(dlg._times):
        dlg._remove_time(time_string)
    assert not dlg.btn_save.isEnabled()
    dlg._save_schedule()
    assert not svc.config.enabled
    dlg.chk_enabled.setChecked(False)
    assert dlg.btn_save.isEnabled()


def test_daily_preview_explains_why_the_next_run_is_tomorrow(qtbot):
    svc = ValidationSchedulerService(db=None)
    svc.save_config(ScheduleConfig(enabled=True, times=["15:00", "15:30"]))
    dlg = ScheduleValidationDialog(svc, rule_count=1)
    qtbot.addWidget(dlg)
    dlg._update_preview(datetime(2026, 11, 28, 16, 0))
    assert "Tomorrow, 29 Nov 2026 at 15:00" in dlg.lbl_preview_next.text()
    assert "already passed" in dlg.lbl_preview_reason.text()
    dlg.time_input.setTime(QTime(16, 17))
    dlg._add_selected_time()
    dlg._update_preview(datetime(2026, 11, 28, 16, 0))
    assert "Today, 28 Nov 2026 at 16:17" in dlg.lbl_preview_next.text()
    assert "still ahead today" in dlg.lbl_preview_reason.text()
    svc._timer.stop()


def test_home_page_scheduler_controls_and_empty_sheet_guard(qtbot):
    reg_svc = MagicMock(spec=RegistryService)
    reg_svc.list_registrations.return_value = []
    rule_svc = MagicMock(spec=RuleService)
    rule_svc.list_rules.return_value = []
    orch_svc = MagicMock(spec=OrchestratorService)
    orch_svc._db = None

    home = HomePage(
        registry_service=reg_svc,
        rule_service=rule_svc,
        orchestrator_service=orch_svc,
    )
    qtbot.addWidget(home)
    home.show()

    assert hasattr(home, "schedule_validation_button")
    assert hasattr(home, "schedule_badge")
    assert "Schedule Off" in home.schedule_badge.text()

    # Since rule_count is 0, clicking schedule button should trigger warning banner
    home._open_schedule_dialog()
    assert home.validation_banner.isHidden() is False
    assert "Validation Sheet is currently empty" in home.validation_banner._message_label.text()


def test_schedule_dialog_toggle_switch_and_card_clicks(qtbot):
    """Verify clicking directly anywhere on the toggle switch or its surrounding card toggles state."""
    svc = ValidationSchedulerService(db=None)
    dlg = ScheduleValidationDialog(scheduler_service=svc, rule_count=3)
    qtbot.addWidget(dlg)
    dlg.show()

    assert dlg.chk_enabled.isChecked() is False

    # 1. Click switch near center (x=30, y=14)
    QTest.mouseClick(dlg.chk_enabled, Qt.MouseButton.LeftButton, pos=QPoint(30, 14))
    assert dlg.chk_enabled.isChecked() is True
    assert dlg.settings_card.isEnabled() is True

    # 2. Click switch near right knob (x=48, y=14)
    QTest.mouseClick(dlg.chk_enabled, Qt.MouseButton.LeftButton, pos=QPoint(48, 14))
    assert dlg.chk_enabled.isChecked() is False
    assert dlg.settings_card.isEnabled() is False

    # 3. Click switch near left edge (x=8, y=14)
    QTest.mouseClick(dlg.chk_enabled, Qt.MouseButton.LeftButton, pos=QPoint(8, 14))
    assert dlg.chk_enabled.isChecked() is True

    # 4. Click surrounding toggle card rectangle
    QTest.mouseClick(dlg.toggle_card, Qt.MouseButton.LeftButton, pos=QPoint(250, 15))
    assert dlg.chk_enabled.isChecked() is False
    assert dlg.settings_card.isEnabled() is False
