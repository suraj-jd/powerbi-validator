"""UI tests for ScheduleValidationDialog and HomePage scheduler controls."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
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
    dlg.combo_add_time.setCurrentText("23:30")
    dlg._add_selected_time()
    assert "23:30" in dlg._times
    assert len(dlg._times) == initial_count + 1

    # Test removing a time
    dlg._remove_time("23:30")
    assert "23:30" not in dlg._times

    # Test saving
    dlg._save_schedule()
    assert svc.config.enabled is True


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
