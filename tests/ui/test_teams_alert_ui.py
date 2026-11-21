"""UI tests for TeamsAlertConfigDialog and HomePage Teams alert integration."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from PySide6.QtCore import QPoint, Qt
from PySide6.QtTest import QTest

from app.auth.msal_auth import AuthAccount
from app.services.orchestrator_service import OrchestratorService
from app.services.registry_service import RegistryService
from app.services.rule_service import RuleService
from app.services.teams_alert_service import TeamsAlertConfig, TeamsAlertService
from app.ui.dialogs.teams_alert_dialog import TeamsAlertConfigDialog
from app.ui.pages.home_page import HomePage


def test_teams_dialog_initial_state_and_toggle_clicks(qtbot):
    svc = TeamsAlertService(db=None)
    account = AuthAccount(
        home_account_id="id1",
        display_name="Suraj jd",
        username="cisam55573@exespay.com",
        tenant_id="tenant-1",
        is_personal_account=False,
    )

    dlg = TeamsAlertConfigDialog(teams_service=svc, account=account)
    qtbot.addWidget(dlg)
    dlg.show()

    assert "Connected: cisam55573@exespay.com" in dlg.lbl_account_text.text()
    assert dlg.chk_enabled.isChecked() is False
    assert dlg.settings_card.isEnabled() is False

    # 1. Click switch near center (x=30, y=14)
    QTest.mouseClick(dlg.chk_enabled, Qt.MouseButton.LeftButton, pos=QPoint(30, 14))
    assert dlg.chk_enabled.isChecked() is True
    assert dlg.settings_card.isEnabled() is True

    # 2. Click switch near knob (x=48, y=14)
    QTest.mouseClick(dlg.chk_enabled, Qt.MouseButton.LeftButton, pos=QPoint(48, 14))
    assert dlg.chk_enabled.isChecked() is False
    assert dlg.settings_card.isEnabled() is False

    # 3. Click switch near left edge (x=8, y=14)
    QTest.mouseClick(dlg.chk_enabled, Qt.MouseButton.LeftButton, pos=QPoint(8, 14))
    assert dlg.chk_enabled.isChecked() is True

    # 4. Click surrounding toggle card rectangle
    QTest.mouseClick(dlg.toggle_card, Qt.MouseButton.LeftButton, pos=QPoint(250, 15))
    assert dlg.chk_enabled.isChecked() is False


def test_teams_dialog_save_configuration(qtbot):
    svc = TeamsAlertService(db=None)
    dlg = TeamsAlertConfigDialog(teams_service=svc)
    qtbot.addWidget(dlg)
    dlg.show()

    # Enable and enter webhook URL
    dlg.chk_enabled.setChecked(True)
    dlg.edit_webhook_url.setText("https://teams.microsoft.com/l/webhook/test123")
    dlg.combo_notify_on.setCurrentIndex(2)  # "all"

    dlg._save_settings()

    assert svc.config.enabled is True
    assert svc.config.webhook_url == "https://teams.microsoft.com/l/webhook/test123"
    assert svc.config.notify_on == "all"


def test_home_page_teams_badge_and_dialog(qtbot):
    reg_svc = MagicMock(spec=RegistryService)
    reg_svc.list_registrations.return_value = []
    rule_svc = MagicMock(spec=RuleService)
    rule_svc.list_rules.return_value = []
    orch_svc = MagicMock(spec=OrchestratorService)
    orch_svc._db = None

    svc = TeamsAlertService(db=None)

    home = HomePage(
        registry_service=reg_svc,
        rule_service=rule_svc,
        orchestrator_service=orch_svc,
        teams_alert_service=svc,
    )
    qtbot.addWidget(home)
    home.show()

    assert hasattr(home, "teams_badge")
    assert hasattr(home, "teams_alerts_button")
    assert "Teams: Off" in home.teams_badge.text()

    # Enable Teams alert
    svc.save_config(
        TeamsAlertConfig(
            enabled=True,
            webhook_url="https://contoso.webhook.office.com/test",
            notify_on="failure_only",
        )
    )
    assert "Teams: Violations" in home.teams_badge.text()
