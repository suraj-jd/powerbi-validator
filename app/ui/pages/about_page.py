"""Descriptive product documentation, check reference, and local support utilities."""

from __future__ import annotations

from pathlib import Path
import platform

from PySide6.QtCore import Qt, QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from app import APP_NAME, APP_VERSION
from app.core.config import AppConfig
from app.core.status import NotificationLevel, ValidationStatus
from app.services.sheet_service import (
    FRIENDLY_TEST_NAMES,
    TEST_TYPE_TOOLTIPS,
    VALIDATION_TYPE_ANOMALY,
    VALIDATION_TYPE_DAX_MEASURE,
    VALIDATION_TYPE_DUPLICATE,
    VALIDATION_TYPE_LATEST_DATE,
    VALIDATION_TYPE_NULL,
    VALIDATION_TYPE_REFRESH,
    VALIDATION_TYPE_ROW_COUNT,
)
from app.ui.widgets.enterprise import PageHeader, action_button, status_presentation
from app.ui.widgets.notification_banner import NotificationBanner

_CHECK_REFERENCE_DETAILS: dict[str, tuple[str, str]] = {
    VALIDATION_TYPE_NULL: (
        "Key settings: Max allowed blank count or percentage, plus optional empty-string and whitespace handling.",
        "Example: Ensure Orders[Order_ID] has 0 NULL or blank values after ETL load.",
    ),
    VALIDATION_TYPE_DUPLICATE: (
        "Key settings: Max allowed duplicate count and optional case-sensitive text comparison.",
        "Example: Verify Customers[Customer_Key] remains unique with 0 duplicate keys.",
    ),
    VALIDATION_TYPE_ROW_COUNT: (
        "Key settings: Expected exact row count or minimum/maximum acceptable row bounds.",
        "Example: Confirm FactSales contains at least 10,000 rows after overnight refresh.",
    ),
    VALIDATION_TYPE_LATEST_DATE: (
        "Key settings: Max data age limit (hours) and whether future dates should fail validation.",
        "Example: Alert if Orders[Order_Date] is more than 24h behind the current UTC time.",
    ),
    VALIDATION_TYPE_DAX_MEASURE: (
        "Key settings: Target measure, comparison operator (=, >, <, between), expected value, and tolerance %.",
        "Example: Verify [Gross Margin %] stays between 20% and 65% across active regions.",
    ),
    VALIDATION_TYPE_ANOMALY: (
        "Key settings: Historical lookback window, deviation % threshold, optional weekend exclusion, and min/max floors.",
        "Example: Detect if daily [Net Revenue] deviates by more than +/-25% from its 30-day baseline.",
    ),
    VALIDATION_TYPE_REFRESH: (
        "Key settings: Expected refresh status (Completed) and maximum allowed hours since last successful refresh.",
        "Example: Fail if the Sales Semantic Model has not refreshed cleanly within the last 24h.",
    ),
}


class AboutPage(QWidget):
    """Structured product guide, validation catalog, and local diagnostics/support page."""

    page_requested = Signal(str)
    diagnostics_requested = Signal()
    backup_requested = Signal()

    def __init__(
        self,
        *,
        config: AppConfig | None = None,
        logs_dir: Path | None = None,
        db_path: Path | None = None,
        token_cache_path: Path | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._config = config or AppConfig()
        self._logs_dir = logs_dir
        self._db_path = db_path
        self._token_cache_path = token_cache_path

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 16, 24, 16)
        layout.setSpacing(12)
        layout.addWidget(
            PageHeader(
                "About & Support",
                f"{APP_NAME} · Version {APP_VERSION} · Local-First Power BI Governance",
            )
        )
        self.banner = NotificationBanner(self)
        layout.addWidget(self.banner)

        self.tabs = QTabWidget()
        self.tabs.addTab(self._quick_start(), "Quick start")
        self.tabs.addTab(self._reference(), "Check reference")
        self.tabs.addTab(self._support(), "Support")
        layout.addWidget(self.tabs, 1)

    def _scroll(self, content: QWidget) -> QScrollArea:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setWidget(content)
        return scroll

    def _card(
        self,
        title: str,
        body: str,
        *,
        badge_text: str | None = None,
        badge_style: str | None = None,
        bullets: list[str] | None = None,
    ) -> QFrame:
        card = QFrame()
        card.setObjectName("Card")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(18, 14, 18, 14)
        layout.setSpacing(6)

        header = QHBoxLayout()
        header.setSpacing(8)
        if badge_text:
            badge = QLabel(badge_text)
            badge.setStyleSheet(
                badge_style
                or "background-color: #EFF6FF; color: #1D4ED8; border: 1px solid #BFDBFE; "
                   "border-radius: 4px; padding: 2px 8px; font-size: 11px; font-weight: 700;"
            )
            header.addWidget(badge)

        heading = QLabel(title)
        heading.setObjectName("SectionTitle")
        heading.setWordWrap(True)
        header.addWidget(heading, 1)
        layout.addLayout(header)

        if body:
            text = QLabel(body)
            text.setWordWrap(True)
            text.setObjectName("MutedText")
            text.setTextFormat(Qt.TextFormat.PlainText)
            layout.addWidget(text)

        for item in bullets or []:
            bullet_lbl = QLabel(f"•  {item}")
            bullet_lbl.setWordWrap(True)
            bullet_lbl.setStyleSheet("color: #334155; font-size: 12px; padding-left: 4px;")
            bullet_lbl.setTextFormat(Qt.TextFormat.PlainText)
            layout.addWidget(bullet_lbl)

        return card

    def _hero_card(self) -> QFrame:
        hero = QFrame()
        hero.setObjectName("Card")
        layout = QVBoxLayout(hero)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(10)

        top = QHBoxLayout()
        top.setSpacing(10)
        title = QLabel(APP_NAME)
        title.setStyleSheet("font-size: 16px; font-weight: 700; color: #16243A;")
        top.addWidget(title)

        ver_pill = QLabel(f"v{APP_VERSION}")
        ver_pill.setStyleSheet(
            "background-color: #EFF6FF; color: #1D4ED8; border: 1px solid #BFDBFE; "
            "border-radius: 4px; padding: 2px 8px; font-size: 11px; font-weight: 700;"
        )
        top.addWidget(ver_pill)

        local_pill = QLabel("Local Desktop · Zero-Trust")
        local_pill.setStyleSheet(
            "background-color: #DCFCE7; color: #15803D; border: 1px solid #BBF7D0; "
            "border-radius: 4px; padding: 2px 8px; font-size: 11px; font-weight: 700;"
        )
        top.addWidget(local_pill)
        top.addStretch(1)
        layout.addLayout(top)

        summary = QLabel(
            "Automates semantic model quality assurance across your Power BI workspaces. "
            "Run data integrity checks, DAX measure assertions, freshness SLAs, and historical "
            "comparisons directly from your desktop without sending credentials or dataset rows to external servers."
        )
        summary.setWordWrap(True)
        summary.setStyleSheet("color: #334155; font-size: 13px;")
        summary.setTextFormat(Qt.TextFormat.PlainText)
        layout.addWidget(summary)

        pills_row = QHBoxLayout()
        pills_row.setSpacing(10)
        for cap_title, cap_desc in [
            ("Spreadsheet Rule Design", "Configure checks with live workspace, table, and measure dropdowns."),
            ("Audit History & Diffs", "Compare up to 4 historical runs side by side and export to CSV or Excel."),
            ("Schedules & Teams Alerts", "Run checks automatically on local schedules and post summaries to Teams."),
        ]:
            box = QFrame()
            box.setStyleSheet(
                "QFrame { background-color: #F8FAFC; border: 1px solid #DDE4ED; border-radius: 6px; }"
            )
            box_lay = QVBoxLayout(box)
            box_lay.setContentsMargins(12, 10, 12, 10)
            box_lay.setSpacing(3)
            c_title = QLabel(cap_title)
            c_title.setStyleSheet("font-size: 12px; font-weight: 700; color: #16243A; border: none;")
            c_desc = QLabel(cap_desc)
            c_desc.setWordWrap(True)
            c_desc.setStyleSheet("font-size: 11px; color: #526278; border: none;")
            box_lay.addWidget(c_title)
            box_lay.addWidget(c_desc)
            pills_row.addWidget(box, 1)
        layout.addLayout(pills_row)
        return hero

    def _quick_start(self) -> QScrollArea:
        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        layout.addWidget(self._hero_card())

        steps = [
            (
                "STEP 1",
                "Sign in & sync Power BI metadata",
                "Connect using your corporate Microsoft account via Azure CLI or Microsoft Entra ID.",
                [
                    "Use the account banner or menu on Overview to sign in with delegated Power BI read scopes.",
                    "Open Validation Sheet and click Sync from Power BI to cache your workspaces, datasets, tables, columns, and measures.",
                ],
            ),
            (
                "STEP 2",
                "Configure & name checks in Validation Sheet",
                "Define rules in the spreadsheet-style editor so every team member can recognize results immediately.",
                [
                    "Click Add check, enter a clear Check Name (or leave blank to use the auto-generated label), and pick your target model.",
                    "Choose a Check type, add up to 4 optional DAX filters, and click Condition & settings to set thresholds.",
                    "Autosave runs every minute, or click Save sheet to persist immediately.",
                ],
            ),
            (
                "STEP 3",
                "Run checks, inspect details, and export evidence",
                "Evaluate all enabled checks in one click from Overview and share clean reports.",
                [
                    "Click Run all enabled checks in Overview to evaluate rules across every configured model.",
                    "Inspect row-level expected vs. observed values and deviations via Details.",
                    "Export results to CSV or Excel and use Open File or Open File Location directly from the confirmation banner.",
                ],
            ),
            (
                "STEP 4",
                "Automate schedules & Microsoft Teams alerts",
                "Keep datasets monitored continuously while the application is open.",
                [
                    "Click Schedule beside the run button to set daily local-time slots or repeat intervals (requires at least 1 check).",
                    "Configure Teams Alerts to deliver rich Adaptive Card summaries on violations, critical failures, or every run.",
                ],
            ),
        ]
        for badge, title, body, bullets in steps:
            layout.addWidget(self._card(title, body, badge_text=badge, bullets=bullets))

        actions = QHBoxLayout()
        for text, key, icon in [
            ("Validation Sheet", "sheet_settings", "sheet_settings"),
            ("Overview", "home", "home"),
            ("Run History", "history", "history"),
        ]:
            button = action_button(text, icon)
            button.clicked.connect(lambda _=False, target=key: self.page_requested.emit(target))
            actions.addWidget(button)
        actions.addStretch(1)
        layout.addLayout(actions)
        layout.addStretch(1)
        return self._scroll(content)

    def _reference(self) -> QScrollArea:
        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        # Status legend card
        legend_card = QFrame()
        legend_card.setObjectName("Card")
        legend_lay = QVBoxLayout(legend_card)
        legend_lay.setContentsMargins(18, 14, 18, 14)
        legend_lay.setSpacing(8)
        legend_title = QLabel("Result Status Legend")
        legend_title.setObjectName("SectionTitle")
        legend_lay.addWidget(legend_title)

        legend_grid = QGridLayout()
        legend_grid.setHorizontalSpacing(14)
        legend_grid.setVerticalSpacing(8)
        for row_idx, (status, desc) in enumerate(
            [
                (ValidationStatus.PASS, "Condition met within all configured thresholds and tolerances."),
                (ValidationStatus.FAIL, "Validation threshold violated. Review expected vs. observed deviation."),
                (ValidationStatus.WARNING, "Needs review (for example, insufficient historical baseline or minor drift)."),
                (ValidationStatus.ERROR, "Check could not be evaluated due to missing object, DAX syntax, or connection issue."),
            ]
        ):
            label_text, _, fg, bg, _ = status_presentation(status)
            pill = QLabel(label_text)
            pill.setAlignment(Qt.AlignmentFlag.AlignCenter)
            pill.setFixedWidth(108)
            pill.setStyleSheet(
                f"background-color: {bg}; color: {fg}; border: 1px solid {fg}; "
                "border-radius: 4px; padding: 3px 8px; font-size: 11px; font-weight: 700;"
            )
            desc_lbl = QLabel(desc)
            desc_lbl.setWordWrap(True)
            desc_lbl.setStyleSheet("color: #334155; font-size: 12px;")
            legend_grid.addWidget(pill, row_idx, 0, alignment=Qt.AlignmentFlag.AlignLeft)
            legend_grid.addWidget(desc_lbl, row_idx, 1)
        legend_grid.setColumnStretch(1, 1)
        legend_lay.addLayout(legend_grid)
        layout.addWidget(legend_card)

        layout.addWidget(
            self._card(
                "Understanding Dates, Time Zones & Durations",
                "Different screens show distinct timestamps depending on what event is measured:",
                bullets=[
                    "Validated At (UTC): Exact time a validation check finished executing.",
                    "Latest Data Date: Maximum transaction or calendar date found inside your Power BI table.",
                    "Power BI Refresh Time: Timestamp when the Power BI service finished refreshing the semantic model.",
                    "Duration Formatting: Ages and durations of 48 hours or more are automatically displayed in days and hours (for example, 2d 4h).",
                ],
            )
        )

        for key, title in FRIENDLY_TEST_NAMES.items():
            summary = TEST_TYPE_TOOLTIPS.get(key, "Review this check's settings for its expected condition.")
            settings_note, example_note = _CHECK_REFERENCE_DETAILS.get(key, ("", ""))
            bullets = [b for b in (settings_note, example_note) if b]
            layout.addWidget(
                self._card(
                    title,
                    summary,
                    badge_text=key.upper(),
                    badge_style=(
                        "background-color: #F1F5F9; color: #334155; border: 1px solid #CBD5E1; "
                        "border-radius: 4px; padding: 2px 7px; font-size: 10px; font-weight: 700;"
                    ),
                    bullets=bullets,
                )
            )

        layout.addStretch(1)
        return self._scroll(content)

    def _support(self) -> QScrollArea:
        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        card = self._card(
            "Local Storage & Data Paths",
            "Reports, checks, schedules, Teams alert preferences, and validation history are stored locally on this PC. Signing out preserves your saved data.",
        )
        for title, value in [
            ("Database", str(self._db_path) if self._db_path else "Not configured"),
            ("Logs", str(self._logs_dir) if self._logs_dir else "Not configured"),
            ("Token Cache", str(self._token_cache_path) if self._token_cache_path else "Windows DPAPI protected"),
        ]:
            label = QLabel(f"{title}: {value}")
            label.setWordWrap(True)
            label.setTextFormat(Qt.TextFormat.PlainText)
            label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            label.setStyleSheet("color: #334155; font-size: 12px;")
            card.layout().addWidget(label)
        layout.addWidget(card)

        actions = QHBoxLayout()
        self.open_logs_button = action_button("Open logs folder", "export")
        self.open_logs_button.clicked.connect(self._open_log_folder)
        actions.addWidget(self.open_logs_button)
        self.open_db_button = action_button("Open data folder", "database")
        self.open_db_button.clicked.connect(self._open_db_folder)
        actions.addWidget(self.open_db_button)
        export = action_button("Export diagnostics", "export")
        export.clicked.connect(self.diagnostics_requested.emit)
        actions.addWidget(export)
        backup = action_button("Backup & maintenance", "database")
        backup.clicked.connect(self.backup_requested.emit)
        actions.addWidget(backup)
        actions.addStretch(1)
        layout.addLayout(actions)

        layout.addWidget(
            self._card(
                "Account, Security & Privacy",
                "Designed for enterprise environments with strict credential hygiene:",
                bullets=[
                    "OAuth 2.0 delegated access tokens are encrypted on disk using Windows DPAPI and never written to logs.",
                    "Diagnostic log exports automatically redact bearer tokens, secrets, and authorization headers.",
                    "Hide account email is enabled by default in the sidebar; toggle visibility anytime from the Account menu.",
                    "Teams notifications only transmit validation summaries when you explicitly enable and configure an alert target.",
                ],
            )
        )

        layout.addWidget(
            self._card(
                "Runtime & Environment",
                "Application and platform diagnostics:",
                bullets=[
                    f"Application: {APP_NAME} v{APP_VERSION}",
                    f"Operating System: {platform.system()} {platform.release()} ({platform.machine()})",
                    f"Python Runtime: {platform.python_version()}",
                    "Storage Engine: SQLite with Alembic schema migrations",
                ],
            )
        )

        layout.addStretch(1)
        return self._scroll(content)

    def _open_log_folder(self) -> None:
        self._open_folder(self._logs_dir)

    def _open_db_folder(self) -> None:
        self._open_folder(self._db_path.parent if self._db_path else None)

    def _open_folder(self, path: Path | None) -> None:
        if path and path.exists():
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))
        else:
            self.banner.show_message("This folder is not available yet.", level=NotificationLevel.INFO)
