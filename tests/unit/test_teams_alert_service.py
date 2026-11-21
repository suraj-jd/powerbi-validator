"""Unit tests for TeamsAlertService, TeamsAlertConfig, and Teams card formatting."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest
import requests

from app.auth.msal_auth import AuthAccount
from app.services.orchestrator_service import ValidationResultDTO, ValidationRunSummaryDTO, ValidationStatus
from app.services.teams_alert_service import (
    TeamsAlertConfig,
    TeamsAlertService,
    build_teams_adaptive_card,
    build_teams_legacy_messagecard,
)


def _make_dummy_summary(
    status: ValidationStatus = ValidationStatus.FAIL,
    passed: int = 8,
    failed: int = 2,
    warnings: int = 0,
) -> ValidationRunSummaryDTO:
    now = datetime.now(timezone.utc)
    res_pass = ValidationResultDTO(
        id=1,
        validation_run_id=10,
        rule_id=1,
        rule_name="Sales Check",
        validation_type="custom_dax",
        target_type="MEASURE",
        target_display="Sales[Total Sales]",
        status=ValidationStatus.PASS,
        actual_value="100.00",
        expected_value="> 0",
        deviation=None,
        result_summary="Passed",
        detailed_message=None,
        duration_ms=20,
        started_at=now,
        completed_at=now,
    )
    res_fail = ValidationResultDTO(
        id=2,
        validation_run_id=10,
        rule_id=2,
        rule_name="Date Freshness",
        validation_type="latest_date_check",
        target_type="COLUMN",
        target_display="Orders[Date]",
        status=ValidationStatus.FAIL,
        actual_value="2025-01-01",
        expected_value="<= 24h",
        deviation="+1000h over threshold",
        result_summary="Data is stale",
        detailed_message="Table has not refreshed.",
        duration_ms=30,
        started_at=now,
        completed_at=now,
    )
    return ValidationRunSummaryDTO(
        id=10,
        workspace_registration_id=1,
        overall_status=status,
        passed_count=passed,
        failed_count=failed,
        warning_count=warnings,
        error_count=0,
        total_rules=passed + failed + warnings,
        duration_ms=1250,
        app_version="1.0.0",
        started_at=now,
        completed_at=now,
        results=[res_pass, res_fail],
    )


def test_teams_alert_config_serialization():
    cfg = TeamsAlertConfig(
        enabled=True,
        delivery_mode="webhook",
        webhook_url="https://example.webhook.office.com/test",
        notify_on="all",
        include_rule_details=True,
    )
    raw = cfg.to_json()
    loaded = TeamsAlertConfig.from_json(raw)

    assert loaded.enabled is True
    assert loaded.delivery_mode == "webhook"
    assert loaded.webhook_url == "https://example.webhook.office.com/test"
    assert loaded.notify_on == "all"
    assert loaded.include_rule_details is True


def test_teams_alert_config_empty_or_corrupt():
    assert TeamsAlertConfig.from_json(None).enabled is False
    assert TeamsAlertConfig.from_json("").enabled is False
    assert TeamsAlertConfig.from_json("{corrupt: json").enabled is False


def test_should_notify_rules():
    svc = TeamsAlertService(db=None)

    # Disabled
    svc._config.enabled = False
    assert svc.should_notify(_make_dummy_summary(ValidationStatus.FAIL)) is False

    # Enabled - failure_only
    svc._config.enabled = True
    svc._config.notify_on = "failure_only"
    assert svc.should_notify(_make_dummy_summary(ValidationStatus.PASS, 10, 0, 0)) is False
    assert svc.should_notify(_make_dummy_summary(ValidationStatus.WARNING, 9, 0, 1)) is True
    assert svc.should_notify(_make_dummy_summary(ValidationStatus.FAIL, 8, 2, 0)) is True

    # Enabled - failure_strict
    svc._config.notify_on = "failure_strict"
    assert svc.should_notify(_make_dummy_summary(ValidationStatus.WARNING, 9, 0, 1)) is False
    assert svc.should_notify(_make_dummy_summary(ValidationStatus.FAIL, 8, 2, 0)) is True

    # Enabled - all
    svc._config.notify_on = "all"
    assert svc.should_notify(_make_dummy_summary(ValidationStatus.PASS, 10, 0, 0)) is True


def test_build_teams_adaptive_card_structure():
    summary = _make_dummy_summary(ValidationStatus.FAIL, 8, 2, 0)
    account = AuthAccount(
        home_account_id="user123",
        display_name="Jane Doe",
        username="jane@contoso.com",
        tenant_id="tenant-123",
        is_personal_account=False,
    )

    card = build_teams_adaptive_card(summary, account=account, include_details=True)
    assert card["type"] == "message"
    attachments = card["attachments"]
    assert len(attachments) == 1
    content = attachments[0]["content"]
    assert content["type"] == "AdaptiveCard"
    body = content["body"]
    assert len(body) >= 3

    # Verify user account appears in facts
    fact_set = next(item for item in body if item.get("type") == "FactSet")
    facts = fact_set["facts"]
    user_fact = next(f for f in facts if f["title"] == "User Account:")
    assert "Jane Doe (jane@contoso.com)" in user_fact["value"]


def test_build_teams_legacy_messagecard():
    summary = _make_dummy_summary(ValidationStatus.PASS, 10, 0, 0)
    card = build_teams_legacy_messagecard(summary, account=None)
    assert card["@type"] == "MessageCard"
    assert card["themeColor"] == "16A34A"
    assert "VALIDATION PASSED" in card["title"]


@patch("requests.post")
def test_send_webhook_adaptive_success(mock_post):
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_post.return_value = mock_resp

    svc = TeamsAlertService(db=None)
    svc._config.enabled = True
    svc._config.webhook_url = "https://contoso.webhook.office.com/incoming"

    summary = _make_dummy_summary()
    success, msg = svc.send_alert_sync(summary)

    assert success is True
    assert "Alert posted successfully" in msg
    assert mock_post.call_count == 1


@patch("requests.post")
def test_send_webhook_fallback_to_messagecard(mock_post):
    mock_bad = MagicMock()
    mock_bad.status_code = 400
    mock_bad.text = "AdaptiveCard not supported"

    mock_ok = MagicMock()
    mock_ok.status_code = 200

    mock_post.side_effect = [mock_bad, mock_ok]

    svc = TeamsAlertService(db=None)
    svc._config.enabled = True
    svc._config.webhook_url = "https://contoso.webhook.office.com/incoming"

    summary = _make_dummy_summary()
    success, msg = svc.send_alert_sync(summary)

    assert success is True
    assert "Alert posted successfully" in msg
    assert mock_post.call_count == 2


@patch("requests.post")
def test_send_webhook_network_failure(mock_post):
    mock_post.side_effect = requests.ConnectionError("Failed connecting")

    svc = TeamsAlertService(db=None)
    svc._config.enabled = True
    svc._config.webhook_url = "https://contoso.webhook.office.com/incoming"

    summary = _make_dummy_summary()
    success, msg = svc.send_alert_sync(summary)

    assert success is False
    assert "Network failure" in msg


def test_send_webhook_empty_url():
    svc = TeamsAlertService(db=None)
    svc._config.enabled = True
    svc._config.webhook_url = ""

    summary = _make_dummy_summary()
    success, msg = svc.send_alert_sync(summary)

    assert success is False
    assert "URL is not configured" in msg


@patch("requests.post")
def test_send_graph_message_403_guidance(mock_post):
    mock_resp = MagicMock()
    mock_resp.status_code = 403
    mock_post.return_value = mock_resp

    svc = TeamsAlertService(db=None, token_provider=lambda **_: "mock-token")
    svc._config.enabled = True
    svc._config.delivery_mode = "graph"
    svc._config.graph_chat_id = "19:mock_chat_id"

    summary = _make_dummy_summary()
    success, msg = svc.send_alert_sync(summary)

    assert success is False
    assert "403 Forbidden" in msg
    assert "Switch to 'Teams Channel Webhook'" in msg
