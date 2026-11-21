"""Microsoft Teams notification service delivering validation alerts via Webhooks or Microsoft Graph."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
import json
import logging
from typing import Any, Callable
import urllib.parse

from PySide6.QtCore import QObject, QThread, Signal
import requests

from app.auth.msal_auth import AuthAccount
from app.database.db import DatabaseManager
from app.database.repositories.settings_repository import AppSettingsRepository
from app.services.orchestrator_service import ValidationResultDTO, ValidationRunSummaryDTO, ValidationStatus

logger = logging.getLogger(__name__)

SETTING_KEY_TEAMS_CONFIG = "teams_alert_config"


@dataclass
class TeamsAlertConfig:
    """Configuration for Microsoft Teams validation alerts."""

    enabled: bool = False
    delivery_mode: str = "webhook"  # "webhook" or "graph"
    webhook_url: str = ""
    notify_on: str = "failure_only"  # "failure_only", "failure_strict", "all"
    include_rule_details: bool = True
    graph_target: str = "me"  # "me" or "channel"
    graph_chat_id: str = ""
    graph_team_id: str = ""
    graph_channel_id: str = ""

    def to_json(self) -> str:
        data: dict[str, Any] = {
            "enabled": self.enabled,
            "delivery_mode": self.delivery_mode,
            "webhook_url": self.webhook_url.strip(),
            "notify_on": self.notify_on,
            "include_rule_details": self.include_rule_details,
            "graph_target": self.graph_target,
            "graph_chat_id": self.graph_chat_id.strip(),
            "graph_team_id": self.graph_team_id.strip(),
            "graph_channel_id": self.graph_channel_id.strip(),
        }
        return json.dumps(data)

    @classmethod
    def from_json(cls, raw: str | None) -> TeamsAlertConfig:
        if not raw:
            return cls()
        try:
            data = json.loads(raw)
            return cls(
                enabled=bool(data.get("enabled", False)),
                delivery_mode=str(data.get("delivery_mode", "webhook")),
                webhook_url=str(data.get("webhook_url", "")).strip(),
                notify_on=str(data.get("notify_on", "failure_only")),
                include_rule_details=bool(data.get("include_rule_details", True)),
                graph_target=str(data.get("graph_target", "me")),
                graph_chat_id=str(data.get("graph_chat_id", "")).strip(),
                graph_team_id=str(data.get("graph_team_id", "")).strip(),
                graph_channel_id=str(data.get("graph_channel_id", "")).strip(),
            )
        except Exception as exc:
            logger.warning("Failed parsing Teams alert config JSON: %s", exc)
            return cls()


def _format_rule_failure_text(result: ValidationResultDTO) -> str:
    """Format a single failed check into a concise readable text string."""
    parts = [f"**{result.rule_name}** ({result.target_display})"]
    if result.expected_value and result.actual_value:
        parts.append(f"Expected: {result.expected_value} | Observed: {result.actual_value}")
    if result.deviation:
        parts.append(f"Deviation: {result.deviation}")
    elif result.result_summary:
        parts.append(f"Issue: {result.result_summary}")
    return " - " + " - ".join(parts)


def build_teams_adaptive_card(
    summary: ValidationRunSummaryDTO,
    account: AuthAccount | None = None,
    include_details: bool = True,
    is_test: bool = False,
) -> dict[str, Any]:
    """Construct a modern Microsoft Teams Adaptive Card 1.4 payload."""
    status = summary.overall_status
    if status == ValidationStatus.PASS:
        status_icon = "🟢"
        status_label = "VALIDATION PASSED"
        status_color = "Good"
        container_style = "good"
    elif status == ValidationStatus.WARNING:
        status_icon = "🟡"
        status_label = "VALIDATION WARNINGS DETECTED"
        status_color = "Warning"
        container_style = "warning"
    else:
        status_icon = "🔴"
        status_label = "VALIDATION VIOLATIONS DETECTED"
        status_color = "Attention"
        container_style = "attention"

    test_prefix = "[TEST ALERT] " if is_test else ""
    title_text = f"{status_icon} {test_prefix}Power BI {status_label}"

    user_str = account.display_name if account else "Microsoft User"
    if account and account.username:
        user_str += f" ({account.username})"

    facts = [
        {"title": "User Account:", "value": user_str},
        {"title": "Overall Status:", "value": status.value},
        {
            "title": "Evaluated Checks:",
            "value": f"{summary.total_rules} total ({summary.passed_count} passed, {summary.failed_count} failed, {summary.warning_count} warnings)",
        },
        {"title": "Duration:", "value": summary.duration_display},
        {"title": "Timestamp:", "value": summary.started_at.strftime("%Y-%m-%d %H:%M:%S UTC")},
    ]

    body_items: list[dict[str, Any]] = [
        {
            "type": "Container",
            "style": container_style,
            "items": [
                {
                    "type": "TextBlock",
                    "text": title_text,
                    "weight": "Bolder",
                    "size": "Medium",
                    "color": status_color,
                },
                {
                    "type": "TextBlock",
                    "text": (
                        "Test message verifying Microsoft Teams alert integration."
                        if is_test
                        else f"Automated validation run evaluated {summary.total_rules} checks across your Validation Sheet."
                    ),
                    "isSubtle": True,
                    "spacing": "None",
                    "wrap": True,
                },
            ],
        },
        {
            "type": "FactSet",
            "facts": facts,
            "spacing": "Medium",
        },
    ]

    # Include failed rules breakdown
    if include_details and (summary.failed_count > 0 or summary.warning_count > 0):
        failed_results = [
            r for r in summary.results if r.status in (ValidationStatus.FAIL, ValidationStatus.ERROR)
        ]
        if failed_results:
            body_items.append(
                {
                    "type": "TextBlock",
                    "text": f"Failed Checks ({len(failed_results)}):",
                    "weight": "Bolder",
                    "separator": True,
                    "spacing": "Medium",
                }
            )
            for res in failed_results[:8]:  # Limit top 8 failures to avoid excessive payload
                body_items.append(
                    {
                        "type": "TextBlock",
                        "text": _format_rule_failure_text(res),
                        "wrap": True,
                        "spacing": "Small",
                    }
                )
            if len(failed_results) > 8:
                body_items.append(
                    {
                        "type": "TextBlock",
                        "text": f"... and {len(failed_results) - 8} additional violation(s). Open application to view complete diagnostics.",
                        "isSubtle": True,
                        "spacing": "Small",
                    }
                )

    body_items.append(
        {
            "type": "TextBlock",
            "text": "Power BI Validation Tool - Automated Diagnostics",
            "isSubtle": True,
            "size": "Small",
            "spacing": "Large",
            "separator": True,
        }
    )

    return {
        "type": "message",
        "attachments": [
            {
                "contentType": "application/vnd.microsoft.card.adaptive",
                "content": {
                    "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
                    "type": "AdaptiveCard",
                    "version": "1.4",
                    "msteams": {"width": "Full"},
                    "body": body_items,
                },
            }
        ],
    }


def build_teams_legacy_messagecard(
    summary: ValidationRunSummaryDTO,
    account: AuthAccount | None = None,
    include_details: bool = True,
    is_test: bool = False,
) -> dict[str, Any]:
    """Construct a legacy Office 365 Connector MessageCard payload as fallback."""
    status = summary.overall_status
    if status == ValidationStatus.PASS:
        theme_color = "16A34A"
        status_label = "VALIDATION PASSED"
    elif status == ValidationStatus.WARNING:
        theme_color = "D97706"
        status_label = "VALIDATION WARNINGS"
    else:
        theme_color = "DC2626"
        status_label = "VALIDATION VIOLATIONS DETECTED"

    test_prefix = "[TEST ALERT] " if is_test else ""
    title_text = f"{test_prefix}Power BI {status_label}"

    user_str = account.display_name if account else "Microsoft User"
    if account and account.username:
        user_str += f" ({account.username})"

    facts = [
        {"name": "User Account:", "value": user_str},
        {"name": "Overall Status:", "value": status.value},
        {
            "name": "Evaluated Checks:",
            "value": f"{summary.total_rules} total ({summary.passed_count} passed, {summary.failed_count} failed, {summary.warning_count} warnings)",
        },
        {"name": "Duration:", "value": summary.duration_display},
        {"name": "Timestamp:", "value": summary.started_at.strftime("%Y-%m-%d %H:%M:%S UTC")},
    ]

    text_lines = [
        "Test message verifying Microsoft Teams alert integration."
        if is_test
        else f"Automated validation evaluated {summary.total_rules} checks across your Validation Sheet."
    ]

    if include_details and (summary.failed_count > 0 or summary.warning_count > 0):
        failed_results = [
            r for r in summary.results if r.status in (ValidationStatus.FAIL, ValidationStatus.ERROR)
        ]
        if failed_results:
            text_lines.append("")
            text_lines.append("**Failed Checks:**")
            for res in failed_results[:8]:
                text_lines.append(_format_rule_failure_text(res))

    return {
        "@type": "MessageCard",
        "@context": "https://schema.org/extensions",
        "themeColor": theme_color,
        "summary": title_text,
        "title": title_text,
        "sections": [
            {
                "activityTitle": "Power BI Validation Diagnostics",
                "activitySubtitle": f"Evaluated by {user_str}",
                "facts": facts,
                "text": "\n\n".join(text_lines),
            }
        ],
    }


class TeamsAlertWorker(QThread):
    """Background worker dispatching Teams notifications without blocking the UI thread."""

    finished_signal = Signal(bool, str)

    def __init__(
        self,
        service: TeamsAlertService,
        summary: ValidationRunSummaryDTO | None = None,
        account: AuthAccount | None = None,
        is_test: bool = False,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._service = service
        self._summary = summary
        self._account = account
        self._is_test = is_test

    def run(self) -> None:
        success, message = self._service.send_alert_sync(
            summary=self._summary,
            account=self._account,
            is_test=self._is_test,
        )
        self.finished_signal.emit(success, message)


class TeamsAlertService(QObject):
    """Service managing Microsoft Teams alerts for validation runs."""

    config_changed = Signal(object)  # emits TeamsAlertConfig
    alert_dispatched = Signal(bool, str)  # success, message

    def __init__(
        self,
        db: DatabaseManager | None = None,
        token_provider: Callable[..., str] | None = None,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._db = db
        self._token_provider = token_provider
        self._config = TeamsAlertConfig()
        self._active_worker: TeamsAlertWorker | None = None

        self._load_config()

    @property
    def config(self) -> TeamsAlertConfig:
        return self._config

    def set_db(self, db: DatabaseManager) -> None:
        self._db = db
        self._load_config()

    def set_token_provider(self, token_provider: Callable[..., str]) -> None:
        self._token_provider = token_provider

    def _load_config(self) -> None:
        if self._db is None:
            return
        try:
            with self._db.session_scope() as session:
                repo = AppSettingsRepository(session)
                raw = repo.get_value(SETTING_KEY_TEAMS_CONFIG)
                self._config = TeamsAlertConfig.from_json(raw)
        except Exception as exc:
            logger.warning("Could not load Teams alert config: %s", exc)
            self._config = TeamsAlertConfig()
        self.config_changed.emit(self._config)

    def save_config(self, config: TeamsAlertConfig) -> None:
        """Persist updated configuration to SQLite database."""
        self._config = config
        if self._db is not None:
            try:
                with self._db.session_scope() as session:
                    repo = AppSettingsRepository(session)
                    repo.set(SETTING_KEY_TEAMS_CONFIG, config.to_json())
            except Exception as exc:
                logger.error("Failed persisting Teams alert config to database: %s", exc)
        self.config_changed.emit(self._config)

    def should_notify(self, summary: ValidationRunSummaryDTO) -> bool:
        """Evaluate whether the given run summary triggers an alert under current rules."""
        if not self._config.enabled:
            return False

        mode = self._config.notify_on
        if mode == "all":
            return True
        if mode == "failure_strict":
            return summary.failed_count > 0 or summary.error_count > 0
        # Default: failure_only (fails, errors, or warnings)
        return summary.failed_count > 0 or summary.error_count > 0 or summary.warning_count > 0

    def send_alert_async(
        self,
        summary: ValidationRunSummaryDTO | None = None,
        account: AuthAccount | None = None,
        is_test: bool = False,
        on_completed: Callable[[bool, str], None] | None = None,
    ) -> TeamsAlertWorker:
        """Dispatch a Teams alert on a background worker thread."""
        worker = TeamsAlertWorker(
            service=self,
            summary=summary,
            account=account,
            is_test=is_test,
            parent=self,
        )

        def _on_finish(success: bool, msg: str) -> None:
            self.alert_dispatched.emit(success, msg)
            if on_completed:
                on_completed(success, msg)
            worker.deleteLater()

        worker.finished_signal.connect(_on_finish)
        self._active_worker = worker
        worker.start()
        return worker

    def send_alert_sync(
        self,
        summary: ValidationRunSummaryDTO | None = None,
        account: AuthAccount | None = None,
        is_test: bool = False,
    ) -> tuple[bool, str]:
        """Synchronously dispatch a Teams alert to the configured endpoint."""
        if is_test and summary is None:
            return self.send_test_alert(account)
        if summary is None:
            return False, "No validation summary provided."
        if self._config.delivery_mode == "graph":
            return self._send_graph_message(summary, account, is_test)
        return self._send_webhook_message(summary, account, is_test)

    def _send_webhook_message(
        self,
        summary: ValidationRunSummaryDTO,
        account: AuthAccount | None = None,
        is_test: bool = False,
    ) -> tuple[bool, str]:
        url = self._config.webhook_url.strip()
        if not url:
            return False, "Teams Webhook URL is not configured."

        if not (url.startswith("https://") or url.startswith("http://")):
            return False, "Teams Webhook URL must begin with https://"

        # First attempt: modern Adaptive Card 1.4 payload
        adaptive_payload = build_teams_adaptive_card(
            summary=summary,
            account=account,
            include_details=self._config.include_rule_details,
            is_test=is_test,
        )

        try:
            resp = requests.post(
                url,
                json=adaptive_payload,
                headers={"Content-Type": "application/json; charset=utf-8"},
                timeout=15.0,
            )
            if resp.status_code in (200, 201, 202):
                logger.info("Successfully posted Adaptive Card to Teams webhook.")
                return True, "Alert posted successfully to Teams channel."

            # If webhook rejected Adaptive Card format, try legacy MessageCard format
            logger.warning(
                "Teams webhook returned status %d for Adaptive Card. Retrying with MessageCard.",
                resp.status_code,
            )
        except requests.RequestException as exc:
            logger.warning("Error posting Adaptive Card to Teams webhook: %s", exc)

        # Fallback attempt: Office 365 Connector MessageCard
        legacy_payload = build_teams_legacy_messagecard(
            summary=summary,
            account=account,
            include_details=self._config.include_rule_details,
            is_test=is_test,
        )

        try:
            resp_fallback = requests.post(
                url,
                json=legacy_payload,
                headers={"Content-Type": "application/json; charset=utf-8"},
                timeout=15.0,
            )
            if resp_fallback.status_code in (200, 201, 202):
                logger.info("Successfully posted MessageCard to Teams webhook.")
                return True, "Alert posted successfully to Teams channel."

            err_msg = f"Teams webhook error (HTTP {resp_fallback.status_code}): {resp_fallback.text[:200]}"
            logger.error(err_msg)
            return False, err_msg
        except requests.RequestException as exc:
            err_msg = f"Network failure connecting to Teams webhook: {type(exc).__name__}"
            logger.error(err_msg)
            return False, err_msg

    def _send_graph_message(
        self,
        summary: ValidationRunSummaryDTO,
        account: AuthAccount | None = None,
        is_test: bool = False,
    ) -> tuple[bool, str]:
        """Send message via Microsoft Graph API using the logged-in Microsoft account token."""
        if not self._token_provider:
            return False, "No active Microsoft token provider available for Microsoft Graph."

        try:
            token = self._token_provider(scopes=["https://graph.microsoft.com/.default"])
        except Exception as exc:
            return False, f"Could not acquire Microsoft Graph token: {exc}"

        if not token:
            return False, "Failed acquiring Microsoft Graph token for logged-in user."

        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json; charset=utf-8",
        }

        # Build clean HTML content for Graph chat/channel message
        status_color = "#16A34A" if summary.overall_status == ValidationStatus.PASS else "#DC2626"
        user_name = account.display_name if account else "Microsoft User"
        user_email = f"({account.username})" if account and account.username else ""

        html_body = f"""
        <div style="font-family: Segoe UI, sans-serif; border-left: 4px solid {status_color}; padding-left: 10px;">
            <h3 style="color: {status_color}; margin: 0 0 6px 0;">{'[TEST ALERT] ' if is_test else ''}Power BI Validation: {summary.overall_status.value}</h3>
            <p style="margin: 0 0 4px 0;"><b>Triggered by:</b> {user_name} {user_email}</p>
            <p style="margin: 0 0 4px 0;"><b>Checks Summary:</b> {summary.total_rules} total ({summary.passed_count} passed, {summary.failed_count} failed)</p>
            <p style="margin: 0 0 4px 0;"><b>Duration:</b> {summary.duration_display} | <b>Time:</b> {summary.started_at.strftime('%Y-%m-%d %H:%M:%S UTC')}</p>
        </div>
        """

        payload = {
            "body": {
                "contentType": "html",
                "content": html_body,
            }
        }

        # Graph endpoint target
        if self._config.graph_target == "channel" and self._config.graph_team_id and self._config.graph_channel_id:
            endpoint = f"https://graph.microsoft.com/v1.0/teams/{self._config.graph_team_id}/channels/{self._config.graph_channel_id}/messages"
        elif self._config.graph_chat_id:
            endpoint = f"https://graph.microsoft.com/v1.0/chats/{self._config.graph_chat_id}/messages"
        else:
            return False, "No valid Microsoft Graph chat or channel specified. Please provide a chat ID or use Webhook mode."

        try:
            resp = requests.post(endpoint, json=payload, headers=headers, timeout=15.0)
            if resp.status_code in (200, 201):
                return True, "Alert posted successfully via Microsoft Graph API."
            if resp.status_code == 403:
                return False, (
                    "Microsoft Graph returned 403 Forbidden: Your Microsoft Entra tenant requires "
                    "ChannelMessage.Send or Chat.ReadWrite permission approval. "
                    "Tip: Switch to 'Teams Channel Webhook' mode to post without needing IT tenant admin approval."
                )
            return False, f"Microsoft Graph error (HTTP {resp.status_code}): {resp.text[:200]}"
        except requests.RequestException as exc:
            return False, f"Network failure calling Microsoft Graph: {type(exc).__name__}"

    def send_test_alert(self, account: AuthAccount | None = None) -> tuple[bool, str]:
        """Construct and send an immediate sample validation alert to test connectivity."""
        now = datetime.now(timezone.utc)
        sample_result_pass = ValidationResultDTO(
            id=1,
            validation_run_id=9999,
            rule_id=1,
            rule_name="Sales_Amount > 0 Check",
            validation_type="custom_dax",
            target_type="MEASURE",
            target_display="Sales[Total Sales]",
            status=ValidationStatus.PASS,
            actual_value="45,210.00",
            expected_value="> 0",
            deviation="0.00",
            result_summary="Condition satisfied",
            detailed_message="Validation passed successfully.",
            duration_ms=45,
            started_at=now,
            completed_at=now,
        )
        sample_result_fail = ValidationResultDTO(
            id=2,
            validation_run_id=9999,
            rule_id=2,
            rule_name="Order_Date Freshness",
            validation_type="latest_date_check",
            target_type="COLUMN",
            target_display="Orders[Order_Date]",
            status=ValidationStatus.FAIL,
            actual_value="2025-01-16 (16,184.0h old)",
            expected_value="<= 24.0h limit",
            deviation="+16,160.0h over threshold",
            result_summary="Data is stale: latest date exceeds 24.0h limit.",
            detailed_message="Table order dates have not refreshed recently.",
            duration_ms=62,
            started_at=now,
            completed_at=now,
        )

        test_summary = ValidationRunSummaryDTO(
            id=9999,
            workspace_registration_id=1,
            overall_status=ValidationStatus.FAIL,
            passed_count=9,
            failed_count=1,
            warning_count=0,
            error_count=0,
            total_rules=10,
            duration_ms=1840,
            app_version="1.0.0",
            started_at=now,
            completed_at=now,
            results=[sample_result_pass, sample_result_fail],
        )

        return self.send_alert_sync(
            summary=test_summary,
            account=account,
            is_test=True,
        )

    def get_status_text(self) -> str:
        """User-friendly status text for badges and labels."""
        if not self._config.enabled:
            return "Teams: Off"
        if self._config.notify_on == "all":
            return "Teams: All Runs"
        if self._config.notify_on == "failure_strict":
            return "Teams: Critical Only"
        return "Teams: Violations"
