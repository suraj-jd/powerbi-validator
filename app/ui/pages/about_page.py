"""About page displaying application metadata, comprehensive user guide, section definitions, and system diagnostics."""

from __future__ import annotations

import platform
import sys
from pathlib import Path

from PySide6 import __version__ as pyside_version
from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from app import APP_NAME, APP_STAGE, APP_VERSION
from app.core.config import AppConfig
from app.core.status import NotificationLevel, ValidationStatus
from app.ui.dialogs.confirm_dialog import ConfirmDialog
from app.ui.models.dict_table_model import ColumnSpec
from app.ui.widgets.data_table import DataTableWidget
from app.ui.widgets.notification_banner import NotificationBanner
from app.ui.widgets.smooth_scroller import apply_smooth_scrolling

_DEMO_COLUMNS: list[ColumnSpec] = [
    ColumnSpec(key="sr", header="SR", alignment=Qt.AlignmentFlag.AlignCenter),
    ColumnSpec(key="component", header="Shared Component"),
    ColumnSpec(key="purpose", header="Role in Application"),
    ColumnSpec(
        key="status",
        header="Sample Status",
        alignment=Qt.AlignmentFlag.AlignCenter,
        is_status=True,
    ),
]

_DEMO_ROWS = [
    {
        "sr": 1,
        "component": "Central Config (Pydantic)",
        "purpose": "Validates non-secret local preferences",
        "status": ValidationStatus.PASS.value,
    },
    {
        "sr": 2,
        "component": "Rotating Redacted Logger",
        "purpose": "Writes rotating logs while scrubbing tokens/secrets",
        "status": ValidationStatus.PASS.value,
    },
    {
        "sr": 3,
        "component": "Sample Warning State",
        "purpose": "Illustrates amber WARNING badge rendering",
        "status": ValidationStatus.WARNING.value,
    },
    {
        "sr": 4,
        "component": "Sample Failure State",
        "purpose": "Illustrates red FAIL badge rendering",
        "status": ValidationStatus.FAIL.value,
    },
    {
        "sr": 5,
        "component": "Sample Error State",
        "purpose": "Keeps execution ERROR distinct from data FAIL",
        "status": ValidationStatus.ERROR.value,
    },
]


class AboutPage(QWidget):
    """Professional software overview, interactive user guide, section manual, and system diagnostics."""

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
        self._build_ui()

    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(24, 20, 24, 20)
        outer.setSpacing(16)

        # 1. Header Banner
        header = self._build_header()
        outer.addWidget(header)

        # 2. Notification banner
        self.demo_banner = NotificationBanner(self)
        outer.addWidget(self.demo_banner)

        # 3. Main Tabbed Container
        self.tabs = QTabWidget(self)
        self.tabs.setObjectName("AboutTabs")
        self.tabs.setCursor(Qt.CursorShape.PointingHandCursor)

        self.tabs.addTab(self._build_guide_tab(), "📖  User Guide & Walkthrough")
        self.tabs.addTab(self._build_sections_tab(), "🏛️  Sections & Architecture")
        self.tabs.addTab(self._build_catalog_tab(), "🛡️  Validation Tests Catalog")
        self.tabs.addTab(self._build_diagnostics_tab(), "⚙️  System & Diagnostics")

        outer.addWidget(self.tabs, stretch=1)

    # =========================================================================
    # Header Banner
    # =========================================================================

    def _build_header(self) -> QWidget:
        header_card = QFrame(self)
        header_card.setObjectName("Card")
        header_card.setStyleSheet(
            "QFrame#Card { background-color: #FFFFFF; border: 1px solid #CBD5E1; "
            "border-radius: 8px; padding: 16px 20px; }"
        )
        layout = QHBoxLayout(header_card)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(16)

        # Icon / Logo
        logo_lbl = QLabel("📊")
        logo_lbl.setStyleSheet(
            "font-size: 36px; background-color: #EFF6FF; border: 1px solid #DBEAFE; "
            "border-radius: 10px; padding: 6px 12px;"
        )
        layout.addWidget(logo_lbl, alignment=Qt.AlignmentFlag.AlignVCenter)

        # Title & Subtitle
        title_col = QVBoxLayout()
        title_col.setSpacing(3)

        title_row = QHBoxLayout()
        title_row.setSpacing(10)

        title = QLabel(APP_NAME)
        title.setObjectName("PageTitle")
        title.setStyleSheet("font-size: 20px; font-weight: 700; color: #0F172A;")
        title_row.addWidget(title)

        version_badge = QLabel(f"v{APP_VERSION}")
        version_badge.setStyleSheet(
            "background-color: #EBF3FF; color: #1668DC; font-weight: 700; "
            "padding: 3px 8px; border-radius: 10px; font-size: 11px;"
        )
        title_row.addWidget(version_badge)

        stage_badge = QLabel("Local-First Enterprise")
        stage_badge.setStyleSheet(
            "background-color: #ECFDF5; color: #059669; font-weight: 700; "
            "padding: 3px 8px; border-radius: 10px; font-size: 11px;"
        )
        title_row.addWidget(stage_badge)
        title_row.addStretch(1)

        title_col.addLayout(title_row)

        subtitle = QLabel(
            "Enterprise desktop platform for automated Microsoft Power BI semantic model validation, "
            "quality assurance, and data anomaly detection — 100% local, private, and credential-safe."
        )
        subtitle.setObjectName("PageSubtitle")
        subtitle.setStyleSheet("font-size: 12px; color: #475569;")
        subtitle.setWordWrap(True)
        title_col.addWidget(subtitle)

        layout.addLayout(title_col, stretch=1)
        return header_card

    # =========================================================================
    # Tab 1: Step-by-Step User Guide
    # =========================================================================

    def _build_guide_tab(self) -> QWidget:
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(20, 16, 20, 20)
        layout.setSpacing(14)

        intro_lbl = QLabel(
            "Follow this step-by-step walkthrough to connect to your Power BI tenant, configure automated validation checks, and run quality audits."
        )
        intro_lbl.setStyleSheet("font-size: 13px; font-weight: 600; color: #1E293B;")
        layout.addWidget(intro_lbl)

        # Step 1
        layout.addWidget(
            self._create_step_card(
                step_num=1,
                title="Sign in with Microsoft Entra ID",
                subtitle="Authenticate securely with corporate Microsoft credentials",
                description=(
                    "Connect your corporate Microsoft account via delegated OAuth 2.0 with official Power BI read permissions. "
                    "The tool supports instant 1-click authentication via Azure CLI or secure browser popup."
                ),
                bullet_points=[
                    "Click 'Sign in with Microsoft' in the top notification banner on any page.",
                    "If Azure CLI is signed in on your PC, authentication connects instantly with zero prompts.",
                    "Zero client secrets or passwords are ever saved to disk; security tokens are protected by Windows DPAPI.",
                ],
                tip="You can verify your active signed-in identity and tenant name in the left navigation sidebar.",
            )
        )

        # Step 2
        layout.addWidget(
            self._create_step_card(
                step_num=2,
                title="Sync Accessible Workspaces & Semantic Models",
                subtitle="Discover Power BI workspaces and datasets with one click",
                description=(
                    "Retrieve all Power BI workspaces, reports, and semantic models accessible to your corporate identity. "
                    "All metadata is cached locally for instant offline editing and responsive dropdowns."
                ),
                bullet_points=[
                    "Navigate to the 'Validation Sheet' page from the left sidebar.",
                    "Click the '🔄 Sync PBI' button in the menu ribbon.",
                    "The application automatically fetches accessible workspaces and caches semantic model metadata.",
                ],
                tip="Click '🔄 Sync PBI' anytime new reports or workspaces are published to your Power BI tenant.",
            )
        )

        # Step 3
        layout.addWidget(
            self._create_step_card(
                step_num=3,
                title="Build Rules in the Excel-Style Validation Sheet",
                subtitle="Spreadsheet view designed for business analysts — no code required",
                description=(
                    "Configure validation checks in a spreadsheet-like interface. Select workspaces, reports, tables, and columns "
                    "using smart cascading dropdowns that automatically discover schema objects from your live Power BI models."
                ),
                bullet_points=[
                    "Click '➕ Add Row' in the top menu ribbon.",
                    "Select your target Workspace and Report / Dataset from the dropdowns.",
                    "Choose the Test to Do (Null, Duplicate, Freshness, Row Count, Refresh SLA, DAX Measure, or Anomaly).",
                    "Pick the target Table Name and Column or Measure directly from the cascading dropdown list.",
                    "Filter 1, 2, 3, 4: Specify up to four DAX filter expressions (e.g. 'Dates'[Year] = 2024, 'Customer'[Country] = \"US\") applied directly inside CALCULATE / CALCULATETABLE.",
                    "Non-technical: All technical GUIDs and dataset IDs are linked automatically in the background.",
                ],
                tip="Dropdowns are editable! You can pick from discovered Power BI tables/columns or type custom names freely.",
            )
        )

        # Step 4
        layout.addWidget(
            self._create_step_card(
                step_num=4,
                title="Fine-Tune Test Criteria with the ⚙️ Settings Popup",
                subtitle="Customize thresholds, allowed blanks, freshness SLA, and baselines",
                description=(
                    "Click the ⚙️ Settings button on any rule row to open an interactive configuration popup. "
                    "Customize rule thresholds to reflect your business SLAs and compliance standards."
                ),
                bullet_points=[
                    "Null / Blank Check: Define allowed blank counts (default 0) and toggle empty string detection.",
                    "Duplicate Check: Set acceptable duplicate limits for unique key columns.",
                    "Freshness SLA: Define maximum acceptable hours since the latest recorded timestamp.",
                    "Row Count Baseline: Specify minimum expected rows or baseline percentage deviation tolerances.",
                    "Refresh SLA: Set expected model refresh status ('Completed') and maximum allowable refresh age.",
                    "DAX Measure: Choose operators (=, >, <, between) and target numeric or percentage values.",
                    "Anomaly Detection: Choose rolling lookback days (e.g. 30 days) and standard deviation thresholds.",
                ],
                tip="The ⚙️ button text automatically reflects your active settings (e.g. 'allowed blanks: 0' or 'max age: 24h').",
            )
        )

        # Step 5
        layout.addWidget(
            self._create_step_card(
                step_num=5,
                title="Automatic 1-Minute Auto-Save & Spreadsheet Sharing",
                subtitle="Zero data loss with built-in auto-save and Excel / CSV exchange",
                description=(
                    "Your validation sheet automatically saves changes every 60 seconds. You can also save manually on demand, "
                    "or import/export rules with teammates using Microsoft Excel (.xlsx) or CSV files."
                ),
                bullet_points=[
                    "1-Minute Auto-Save: Automatically detects unsaved edits and commits them silently in the background.",
                    "Live Status Feedback: Look at the bottom status bar for '✓ Auto-saved at HH:MM:SS' or '● Unsaved changes'.",
                    "Manual Save: Click '💾 Save Sheet' anytime to commit all rows immediately to local SQLite storage.",
                    "Excel / CSV Import & Export: Click '📥 Import' to load existing rules from spreadsheets, or '📤 Export' to share.",
                ],
                tip="The Import dialog includes a 1-click 'Download Sample Template' button to generate formatted starter files.",
            )
        )

        # Step 6
        layout.addWidget(
            self._create_step_card(
                step_num=6,
                title="Execute Validations from the Home Dashboard",
                subtitle="Run validations across your models and review live audit reports",
                description=(
                    "Head to the Home page and click '▶ Run Validation'. The orchestrator executes all enabled sheet checks "
                    "directly against live Power BI semantic models in high-performance background workers."
                ),
                bullet_points=[
                    "Real-time Scorecards: View instant KPI summaries (Total Checks, Passed, Warnings, Failures, Errors).",
                    "Detailed Audit Table: Inspect each check's status badge, target object, actual measured value, and expected value.",
                    "Zero UI Freezes: All DAX and REST calls run asynchronously without freezing the interface.",
                ],
                tip="Failed checks display the exact measured value vs expected value, along with recommended remediation actions.",
            )
        )

        # Step 7
        layout.addWidget(
            self._create_step_card(
                step_num=7,
                title="Audit History & Data Health Tracking",
                subtitle="Track historical validation runs and ensure regulatory compliance",
                description=(
                    "Every validation execution is permanently logged in your local audit database. Switch to the History page "
                    "to review past run outcomes, track schema quality over time, and export compliance audit logs."
                ),
                bullet_points=[
                    "Review chronological runs with timestamps, durations, rule counts, and overall status.",
                    "Drill down into any historical execution to inspect specific test results.",
                    "Ensure ongoing compliance and track data quality trends across sprint deployments.",
                ],
                tip="Use the History tab to verify that overnight automated ETL pipelines did not introduce subtle data regressions.",
            )
        )

        return self._wrap_in_scroll_area(container)

    def _create_step_card(
        self,
        *,
        step_num: int,
        title: str,
        subtitle: str,
        description: str,
        bullet_points: list[str],
        tip: str | None = None,
    ) -> QFrame:
        card = QFrame()
        card.setObjectName("Card")
        card.setStyleSheet(
            "QFrame#Card { background-color: #FFFFFF; border: 1px solid #E2E8F0; "
            "border-radius: 8px; padding: 14px 18px; } "
            "QFrame#Card:hover { border-color: #CBD5E1; }"
        )
        layout = QVBoxLayout(card)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(8)

        # Header Row
        header_row = QHBoxLayout()
        header_row.setSpacing(10)

        num_badge = QLabel(f"STEP {step_num}")
        num_badge.setStyleSheet(
            "background-color: #1668DC; color: #FFFFFF; font-weight: 700; "
            "padding: 3px 8px; border-radius: 4px; font-size: 10px;"
        )
        header_row.addWidget(num_badge)

        title_lbl = QLabel(title)
        title_lbl.setStyleSheet("font-size: 14px; font-weight: 700; color: #0F172A;")
        header_row.addWidget(title_lbl)

        sub_lbl = QLabel(f" —  {subtitle}")
        sub_lbl.setStyleSheet("font-size: 12px; color: #64748B;")
        header_row.addWidget(sub_lbl)
        header_row.addStretch(1)

        layout.addLayout(header_row)

        # Description
        desc_lbl = QLabel(description)
        desc_lbl.setStyleSheet("font-size: 12px; color: #334155; line-height: 1.4;")
        desc_lbl.setWordWrap(True)
        layout.addWidget(desc_lbl)

        # Bullets
        bullets_layout = QVBoxLayout()
        bullets_layout.setSpacing(4)
        bullets_layout.setContentsMargins(8, 2, 8, 2)
        for bullet in bullet_points:
            b_row = QHBoxLayout()
            b_row.setSpacing(6)
            dot = QLabel("•")
            dot.setStyleSheet("color: #1668DC; font-weight: 700; font-size: 14px;")
            b_lbl = QLabel(bullet)
            b_lbl.setStyleSheet("font-size: 12px; color: #475569;")
            b_lbl.setWordWrap(True)
            b_row.addWidget(dot, alignment=Qt.AlignmentFlag.AlignTop)
            b_row.addWidget(b_lbl, stretch=1)
            bullets_layout.addLayout(b_row)
        layout.addLayout(bullets_layout)

        # Tip callout
        if tip:
            tip_frame = QFrame()
            tip_frame.setStyleSheet(
                "background-color: #F0FDF4; border-left: 3px solid #10B981; "
                "border-radius: 4px; padding: 6px 10px;"
            )
            tip_layout = QHBoxLayout(tip_frame)
            tip_layout.setContentsMargins(4, 2, 4, 2)
            tip_layout.setSpacing(6)
            t_icon = QLabel("💡")
            t_icon.setStyleSheet("font-size: 12px;")
            t_lbl = QLabel(f"<b>Tip:</b> {tip}")
            t_lbl.setStyleSheet("font-size: 11px; color: #065F46;")
            t_lbl.setWordWrap(True)
            tip_layout.addWidget(t_icon, alignment=Qt.AlignmentFlag.AlignTop)
            tip_layout.addWidget(t_lbl, stretch=1)
            layout.addWidget(tip_frame)

        return card

    # =========================================================================
    # Tab 2: Sections & Tool Reference
    # =========================================================================

    def _build_sections_tab(self) -> QWidget:
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(20, 16, 20, 20)
        layout.setSpacing(14)

        intro_lbl = QLabel(
            "Detailed architectural overview of every page in the application, explaining its core role and operational capabilities."
        )
        intro_lbl.setStyleSheet("font-size: 13px; font-weight: 600; color: #1E293B;")
        layout.addWidget(intro_lbl)

        # Section 1: Home Dashboard
        layout.addWidget(
            self._create_section_card(
                icon="📊",
                title="Home (Validation Dashboard)",
                badge="Execution & Reporting Hub",
                badge_color="#EBF3FF",
                badge_text_color="#1668DC",
                description=(
                    "The primary mission control center for initiating validation runs and evaluating semantic model health in real-time. "
                    "When you trigger validation, it evaluates all active checks configured in your Validation Sheet against live Power BI data."
                ),
                key_features=[
                    ("▶ Run Validation Action", "Executes all enabled sheet checks in asynchronous background workers with real-time progress updates."),
                    ("Executive KPI Scorecards", "Live summary cards counting Total Checks, Passed (green), Warnings (amber), Failures (red), and Errors."),
                    ("Detailed Results Table", "Per-rule audit showing Rule Name, Target Object (Table.Column), Status Badge, Measured Value vs Expected Criteria, and Execution Duration."),
                    ("Active Semantic Model", "Convenient model selector badge showing the currently targeted workspace and dataset."),
                ],
            )
        )

        # Section 2: Validation Sheet
        layout.addWidget(
            self._create_section_card(
                icon="📑",
                title="Validation Sheet (Excel-Style Rule Manager)",
                badge="Interactive Spreadsheet Engine",
                badge_color="#ECFDF5",
                badge_text_color="#059669",
                description=(
                    "A spreadsheet-style validation rules manager designed specifically for non-technical users and business analysts. "
                    "It replaces complex database configurations with an intuitive grid featuring ribbon menus, cascading dropdowns, and popup rule dialogs."
                ),
                key_features=[
                    ("Top Menu Ribbon", "Quick-action toolbar providing Add Row, Delete Row, Save Sheet, Sync PBI, Import, Export, and Quick Search."),
                    ("Cascading Dropdowns", "Intelligently resolves Workspace -> Dataset -> Table -> Column or Measure from discovered Power BI model metadata."),
                    ("1-Minute Auto-Save", "Background timer continuously monitors unsaved changes and commits them safely without user intervention."),
                    ("⚙️ Rule Config Popups", "Tailored configuration dialogs for defining allowed blanks, duplicate limits, freshness SLA hours, or baseline deviations."),
                    ("Excel / CSV Interoperability", "Import existing rules or export complete sheets to Excel (.xlsx) and CSV with template support."),
                ],
            )
        )

        # Section 3: History
        layout.addWidget(
            self._create_section_card(
                icon="🕒",
                title="History (Audit Trail & Trend Compliance)",
                badge="Immutable Audit Archive",
                badge_color="#F3E8FF",
                badge_text_color="#7E22CE",
                description=(
                    "A compliance-grade historical archive logging every validation run executed by your team. "
                    "Allows data engineers and governance leads to audit semantic model quality over time and catch schema regressions."
                ),
                key_features=[
                    ("Chronological Audit Log", "Complete history of past validation executions with timestamps, execution durations, and pass rates."),
                    ("Run Drill-Down", "Inspect the granular per-rule test results of any historical run to identify what changed and why."),
                    ("Trend Analysis", "Track whether model reliability is improving or if recurrent pipeline issues are causing recurring failures."),
                    ("Compliance Export", "Export historical execution runs for stakeholder reporting, governance audits, and SLA verification."),
                ],
            )
        )

        # Section 4: About Page
        layout.addWidget(
            self._create_section_card(
                icon="ℹ️",
                title="About & System Guide (This Page)",
                badge="Documentation & System Diagnostics",
                badge_color="#F1F5F9",
                badge_text_color="#475569",
                description=(
                    "Comprehensive user manual, architectural reference, validation test type catalog, and runtime system diagnostic panel."
                ),
                key_features=[
                    ("Step-by-Step Walkthrough", "Clear numbered guide walking new users through authentication, syncing, sheet editing, and validation runs."),
                    ("Validation Catalog", "In-depth guide explaining all 7 supported validation checks with practical business scenarios."),
                    ("System Diagnostics", "Runtime details (Python, PySide6, Platform), local storage paths, and 1-click folder navigation."),
                    ("Component Health Preview", "Interactive test sandbox verifying shared UI components for automated regression checks."),
                ],
            )
        )

        return self._wrap_in_scroll_area(container)

    def _create_section_card(
        self,
        *,
        icon: str,
        title: str,
        badge: str,
        badge_color: str,
        badge_text_color: str,
        description: str,
        key_features: list[tuple[str, str]],
    ) -> QFrame:
        card = QFrame()
        card.setObjectName("Card")
        card.setStyleSheet(
            "QFrame#Card { background-color: #FFFFFF; border: 1px solid #E2E8F0; "
            "border-radius: 8px; padding: 14px 18px; } "
            "QFrame#Card:hover { border-color: #CBD5E1; }"
        )
        layout = QVBoxLayout(card)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(8)

        # Header Row
        header_row = QHBoxLayout()
        header_row.setSpacing(10)

        i_lbl = QLabel(icon)
        i_lbl.setStyleSheet("font-size: 18px;")
        header_row.addWidget(i_lbl)

        t_lbl = QLabel(title)
        t_lbl.setStyleSheet("font-size: 14px; font-weight: 700; color: #0F172A;")
        header_row.addWidget(t_lbl)

        b_lbl = QLabel(badge)
        b_lbl.setStyleSheet(
            f"background-color: {badge_color}; color: {badge_text_color}; font-weight: 700; "
            "padding: 2px 8px; border-radius: 10px; font-size: 10px;"
        )
        header_row.addWidget(b_lbl)
        header_row.addStretch(1)
        layout.addLayout(header_row)

        # Description
        desc_lbl = QLabel(description)
        desc_lbl.setStyleSheet("font-size: 12px; color: #334155; line-height: 1.4;")
        desc_lbl.setWordWrap(True)
        layout.addWidget(desc_lbl)

        # Key Features
        grid = QGridLayout()
        grid.setHorizontalSpacing(16)
        grid.setVerticalSpacing(4)
        grid.setContentsMargins(4, 4, 4, 4)

        for row_idx, (feature_name, feature_desc) in enumerate(key_features):
            f_name_lbl = QLabel(f"• {feature_name}:")
            f_name_lbl.setStyleSheet("font-size: 12px; font-weight: 600; color: #1E293B;")
            f_desc_lbl = QLabel(feature_desc)
            f_desc_lbl.setStyleSheet("font-size: 12px; color: #475569;")
            f_desc_lbl.setWordWrap(True)
            grid.addWidget(f_name_lbl, row_idx, 0, alignment=Qt.AlignmentFlag.AlignTop)
            grid.addWidget(f_desc_lbl, row_idx, 1)

        grid.setColumnStretch(1, 1)
        layout.addLayout(grid)

        return card

    # =========================================================================
    # Tab 3: Validation Tests Catalog
    # =========================================================================

    def _build_catalog_tab(self) -> QWidget:
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(20, 16, 20, 20)
        layout.setSpacing(16)

        intro_lbl = QLabel(
            "Comprehensive catalog and formula manual for all 7 validation tests configured via the 'Test to Do' "
            "column in your Validation Sheet. Below are the exact DAX queries, Power BI REST API calls, "
            "and mathematical evaluation formulas executed by the tool."
        )
        intro_lbl.setStyleSheet("font-size: 13px; font-weight: 600; color: #1E293B; line-height: 1.4;")
        intro_lbl.setWordWrap(True)
        layout.addWidget(intro_lbl)

        # Quick Reference Summary Card
        layout.addWidget(self._build_catalog_cheat_sheet())

        # 1. Null / Blank Check
        layout.addWidget(
            self._create_test_card(
                icon="🚫",
                test_name="Null / Blank Check (null_check)",
                target_scope="Column Level ('Table'[Column])",
                scope_color="#EFF6FF",
                scope_text_color="#1668DC",
                protocol="⚡ DAX Engine (/executeQueries)",
                definition="Verifies that critical columns do not contain NULL values, empty strings (\"\"), or whitespace-only records.",
                scenario="Guarding primary keys, foreign keys, or mandatory dimension attributes (e.g. CustomerID, OrderDate, Amount) against unpopulated records.",
                config_summary="Allowed blank count (default 0), allowed blank percentage (default 0.0%), and options to include empty strings or whitespace.",
                formula_dax=(
                    "EVALUATE ROW(\n"
                    "    \"TotalRows\", COUNTROWS('TableName'),\n"
                    "    \"BlankCount\", COUNTROWS(FILTER('TableName', ISBLANK('TableName'[ColumnName]) || 'TableName'[ColumnName] = \"\"))\n"
                    ")\n"
                    "-- If a custom filter is configured in Settings:\n"
                    "-- Evaluates FILTER('TableName', <FilterCondition>)"
                ),
                formula_logic=(
                    "• Blank Ratio % = (BlankCount / TotalRows) × 100%\n"
                    "• PASS: BlankCount <= allowed_blank_count (0) AND Blank Ratio % <= allowed_blank_percentage (0.0%)\n"
                    "• FAIL: BlankCount > allowed_blank_count OR Blank Ratio % > allowed_blank_percentage\n"
                    "• WARNING: TotalRows = 0 (Empty dataset returned by model)"
                ),
            )
        )

        # 2. Duplicate Check
        layout.addWidget(
            self._create_test_card(
                icon="👥",
                test_name="Duplicate Check (duplicate_check)",
                target_scope="Column Level (or Composite Keys)",
                scope_color="#EFF6FF",
                scope_text_color="#1668DC",
                protocol="⚡ DAX Engine (/executeQueries)",
                definition="Ensures that unique identifier columns contain strictly distinct records and no repeated keys.",
                scenario="Guarding entity dimension tables against duplicate entries (e.g. EmployeeID, TransactionID, InvoiceNumber) caused by faulty joins or ETL fan-outs.",
                config_summary="Allowed duplicate threshold (default 0), allowed percentage, and optional comma-separated composite key columns.",
                formula_dax=(
                    "-- Single Key Column:\n"
                    "EVALUATE ROW(\n"
                    "    \"TotalRows\", COUNTROWS('TableName'),\n"
                    "    \"DistinctKeys\", COUNTROWS(SUMMARIZE('TableName', 'TableName'[KeyColumn]))\n"
                    ")\n\n"
                    "-- Composite Key Columns (configured in ⚙️ Settings):\n"
                    "EVALUATE ROW(\n"
                    "    \"TotalRows\", COUNTROWS('TableName'),\n"
                    "    \"DistinctKeys\", COUNTROWS(SUMMARIZE('TableName', 'TableName'[ColA], 'TableName'[ColB]))\n"
                    ")"
                ),
                formula_logic=(
                    "• Duplicate Count = TotalRows - DistinctKeys\n"
                    "• Duplicate Ratio % = (Duplicate Count / TotalRows) × 100%\n"
                    "• PASS: Duplicate Count <= allowed_duplicate_count (default 0)\n"
                    "• FAIL: Duplicate Count > allowed_duplicate_count (duplicates detected)\n"
                    "• WARNING: TotalRows = 0 (Empty table)"
                ),
            )
        )

        # 3. Latest Date Freshness
        layout.addWidget(
            self._create_test_card(
                icon="⏱️",
                test_name="Latest Date Freshness (latest_date_check)",
                target_scope="Date / Timestamp Column",
                scope_color="#FEF3C7",
                scope_text_color="#B45309",
                protocol="⚡ DAX Engine (/executeQueries)",
                definition="Evaluates MAX(date_column) against current UTC system time to verify data pipeline freshness SLA and detect future date anomalies.",
                scenario="Catching stalled overnight batch pipelines or failed data syncs before morning executive dashboards present stale daily metrics.",
                config_summary="Maximum allowable data age in hours (e.g. 24h, 36h) or days, and toggle to disallow future timestamps.",
                formula_dax=(
                    "EVALUATE ROW(\n"
                    "    \"LatestDate\", MAX('TableName'[DateColumn]),\n"
                    "    \"EarliestDate\", MIN('TableName'[DateColumn]),\n"
                    "    \"TotalRows\", COUNTROWS('TableName')\n"
                    ")"
                ),
                formula_logic=(
                    "• Data Age (Hours) = (Current UTC Timestamp - LatestDate) / 3600 seconds\n"
                    "• PASS: Data Age <= max_age_hours AND (allow_future OR LatestDate <= Current UTC + future_tolerance)\n"
                    "• FAIL (Stale): Data Age > max_age_hours (Pipeline refresh SLA breached)\n"
                    "• FAIL (Future Anomaly): LatestDate > Current UTC + tolerance (Corrupted future transaction timestamps)\n"
                    "• WARNING: TotalRows = 0 or column values are entirely NULL"
                ),
            )
        )

        # 4. Row Count Check
        layout.addWidget(
            self._create_test_card(
                icon="📊",
                test_name="Row Count Check (row_count_check)",
                target_scope="Table Level ('TableName')",
                scope_color="#F3E8FF",
                scope_text_color="#7E22CE",
                protocol="⚡ DAX Engine (/executeQueries)",
                definition="Validates that total table volume satisfies minimum expected row counts or matches historical baseline rows within tolerance.",
                scenario="Preventing silent table drops, missing partitions, truncated extracts, or unintended Cartesian joins causing volume spikes.",
                config_summary="Fixed thresholds (min_rows, max_rows) or Baseline Percentage Deviation (e.g. +/- 5% of historical baseline).",
                formula_dax=(
                    "-- Full Table Record Count:\n"
                    "EVALUATE ROW(\"RowCount\", COUNTROWS('TableName'))\n\n"
                    "-- With Custom Filter Condition (configured in ⚙️ Settings):\n"
                    "EVALUATE ROW(\"RowCount\", COUNTROWS(FILTER('TableName', <FilterCondition>)))"
                ),
                formula_logic=(
                    "• Fixed Range Method:\n"
                    "    PASS if min_row_count <= RowCount <= max_row_count; FAIL otherwise.\n"
                    "• Baseline Deviation Method:\n"
                    "    Deviation % = (|RowCount - Baseline Row Count| / Baseline Row Count) × 100%\n"
                    "    PASS: Deviation % <= allowed_deviation_pct (default 5.0%)\n"
                    "    FAIL: Deviation % > allowed_deviation_pct"
                ),
            )
        )

        # 5. DAX Measure Check
        layout.addWidget(
            self._create_test_card(
                icon="📐",
                test_name="DAX Measure Check (dax_measure_check)",
                target_scope="Measure Level ([Measure Name])",
                scope_color="#FDF2F8",
                scope_text_color="#BE185D",
                protocol="⚡ DAX Engine (/executeQueries)",
                definition="Executes DAX measures directly inside the semantic model calculation engine and validates numeric or boolean outputs against business criteria.",
                scenario="Validating calculated business KPIs (e.g. [Net Profit Margin %] >= 0.15, [Total Revenue USD] > 0, [Daily Churn Rate] < 0.05).",
                config_summary="Expected value, comparison operators (=, >, <, >=, <=, between), and allowable percentage or absolute deviation tolerances.",
                formula_dax=(
                    "-- Standard Measure Evaluation:\n"
                    "EVALUATE ROW(\"Value\", [Measure Name])\n\n"
                    "-- With Filter Context (configured in ⚙️ Settings):\n"
                    "EVALUATE ROW(\"Value\", CALCULATE([Measure Name], 'Dates'[Year] = 2024))"
                ),
                formula_logic=(
                    "• Baseline Deviation % = ((Actual Value - Expected Value) / Expected Value) × 100%\n"
                    "• PASS: |Deviation %| <= allowed_deviation_pct (or operator condition evaluates to True)\n"
                    "• FAIL: |Deviation %| > allowed_deviation_pct (or operator condition is False)\n"
                    "• FAIL: Measure evaluates to BLANK() when non-blank is expected"
                ),
            )
        )

        # 6. Historical Anomaly Check
        layout.addWidget(
            self._create_test_card(
                icon="📈",
                test_name="Historical Anomaly Check (anomaly_check)",
                target_scope="Measure ([Measure]) or Column ('Table'[Col])",
                scope_color="#FFF7ED",
                scope_text_color="#C2410C",
                protocol="⚡ DAX + Local Statistical Engine",
                definition="Computes a rolling Gaussian distribution (mean and standard deviation) over historical audit runs to automatically detect statistical anomalies without manual threshold maintenance.",
                scenario="Detecting irregular transaction volume spikes, fraudulent spikes, revenue anomalies, or sudden drops in daily active users.",
                config_summary="Rolling lookback window (default 30 days) and standard deviation sensitivity threshold (default 2.5 sigma).",
                formula_dax=(
                    "-- If Target is a DAX Measure:\n"
                    "EVALUATE ROW(\"Value\", [Measure Name])\n\n"
                    "-- If Target is a Column (SUM, AVERAGE, MIN, MAX aggregation):\n"
                    "EVALUATE ROW(\"Value\", SUMX('TableName', 'TableName'[ColumnName]))"
                ),
                formula_logic=(
                    "• Rolling Mean: μ = (1 / N) × Σ(x_i)  for past N validation runs in lookback window\n"
                    "• Standard Deviation: σ = sqrt( (1 / (N - 1)) × Σ(x_i - μ)² )\n"
                    "• Z-Score Distance: Z = |x_current - μ| / σ\n"
                    "• PASS: Z <= sensitivity_threshold (default Z <= 2.5σ, within normal variance)\n"
                    "• WARNING: Z > sensitivity_threshold (Statistically significant outlier detected)\n"
                    "• PASS (Info): Insufficient historical runs (N < 3 runs recorded)"
                ),
            )
        )

        # 7. Power BI Refresh Check
        layout.addWidget(
            self._create_test_card(
                icon="🔄",
                test_name="Power BI Refresh Check (refresh_check)",
                target_scope="Semantic Model / Dataset Level",
                scope_color="#ECFDF5",
                scope_text_color="#059669",
                protocol="🌐 Power BI REST API (/refreshes)",
                definition="Queries the official Power BI REST API to verify scheduled cloud dataset refresh status, completion duration, and SLA freshness.",
                scenario="Alerting engineering teams when cloud gateway refreshes fail with timeout errors or exceed maximum SLA runtime.",
                config_summary="Expected refresh status ('Completed') and maximum allowable elapsed hours since last successful refresh (e.g. 24h).",
                formula_dax=(
                    "GET https://api.powerbi.com/v1.0/myorg/groups/{workspaceId}/datasets/{datasetId}/refreshes?$top=1\n"
                    "Headers:\n"
                    "    Authorization: Bearer <OAuth2_Delegated_Token>\n"
                    "    Accept: application/json"
                ),
                formula_logic=(
                    "• Refresh Age (Hours) = (Current UTC Timestamp - Refresh EndTime) / 3600 seconds\n"
                    "• PASS: Latest Refresh Status == 'Completed' AND Refresh Age <= max_age_hours\n"
                    "• FAIL: Latest Refresh Status == 'Failed' (Cloud refresh error or gateway timeout)\n"
                    "• FAIL: Refresh Age > max_age_hours (Refresh SLA breached)\n"
                    "• WARNING: Status == 'Unknown' OR Status == 'InProgress' (Refresh currently executing)"
                ),
            )
        )

        return self._wrap_in_scroll_area(container)

    def _build_catalog_cheat_sheet(self) -> QFrame:
        card = QFrame()
        card.setObjectName("Card")
        card.setStyleSheet(
            "QFrame#Card { background-color: #F8FAFC; border: 1px solid #CBD5E1; "
            "border-radius: 8px; padding: 14px 18px; }"
        )
        layout = QVBoxLayout(card)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(10)

        title_row = QHBoxLayout()
        title_row.setSpacing(8)
        c_icon = QLabel("⚡")
        c_icon.setStyleSheet("font-size: 16px;")
        title_row.addWidget(c_icon)
        c_title = QLabel("Quick Formula Reference — 'Test to Do' in Validation Sheet")
        c_title.setStyleSheet("font-size: 13px; font-weight: 700; color: #0F172A;")
        title_row.addWidget(c_title)
        title_row.addStretch(1)
        layout.addLayout(title_row)

        desc = QLabel(
            "The table below maps each test option selectable in the Validation Sheet dropdown to its underlying formula and execution protocol."
        )
        desc.setStyleSheet("font-size: 11px; color: #64748B;")
        layout.addWidget(desc)

        grid = QGridLayout()
        grid.setHorizontalSpacing(14)
        grid.setVerticalSpacing(6)
        grid.setContentsMargins(2, 4, 2, 4)

        headers = ["Test to Do", "Target Object", "Underlying Execution Formula", "Pass SLA"]
        for c_idx, h in enumerate(headers):
            h_lbl = QLabel(h)
            h_lbl.setStyleSheet("font-size: 11px; font-weight: 700; color: #1E293B; border-bottom: 2px solid #E2E8F0; padding-bottom: 3px;")
            grid.addWidget(h_lbl, 0, c_idx)

        rows = [
            ("Null / Blank Check", "Table + Column", "COUNTROWS(FILTER('Table', ISBLANK([Col]) || [Col] = \"\"))", "Blank Count <= allowed (0)"),
            ("Duplicate Check", "Table + Column(s)", "TotalRows - COUNTROWS(SUMMARIZE('Table', [Col]))", "Duplicate Count <= allowed (0)"),
            ("Latest Date Freshness", "Table + Date Col", "(Current UTC - MAX('Table'[DateCol])) / 3600s", "Age <= max_age_hours (24h)"),
            ("Row Count Check", "Table Name", "COUNTROWS('Table')", "Within range or +/- deviation %"),
            ("DAX Measure Check", "[Measure Name]", "EVALUATE ROW(\"Value\", [Measure Name])", "Matches target or within +/- dev %"),
            ("Historical Anomaly", "Measure or Column", "Z = |Current - Rolling Mean| / Standard Deviation", "Z-Score <= 2.5σ (within bounds)"),
            ("Power BI Refresh", "Semantic Model", "REST API /refreshes?$top=1 (Status & EndTime)", "Status == 'Completed' & age <= SLA"),
        ]

        for r_idx, (t_name, t_tgt, t_dax, t_sla) in enumerate(rows, start=1):
            lbl_name = QLabel(t_name)
            lbl_name.setStyleSheet("font-size: 11px; font-weight: 600; color: #1668DC;")
            lbl_tgt = QLabel(t_tgt)
            lbl_tgt.setStyleSheet("font-size: 11px; color: #475569;")
            lbl_dax = QLabel(t_dax)
            lbl_dax.setStyleSheet("font-family: Consolas, monospace; font-size: 10px; color: #0F172A;")
            lbl_sla = QLabel(t_sla)
            lbl_sla.setStyleSheet("font-size: 11px; color: #059669; font-weight: 500;")

            grid.addWidget(lbl_name, r_idx, 0)
            grid.addWidget(lbl_tgt, r_idx, 1)
            grid.addWidget(lbl_dax, r_idx, 2)
            grid.addWidget(lbl_sla, r_idx, 3)

        grid.setColumnStretch(2, 1)
        layout.addLayout(grid)
        return card

    def _create_test_card(
        self,
        *,
        icon: str,
        test_name: str,
        target_scope: str,
        scope_color: str,
        scope_text_color: str,
        definition: str,
        scenario: str,
        config_summary: str,
        formula_dax: str | None = None,
        formula_logic: str | None = None,
        protocol: str = "⚡ DAX Engine (/executeQueries)",
    ) -> QFrame:
        card = QFrame()
        card.setObjectName("Card")
        card.setStyleSheet(
            "QFrame#Card { background-color: #FFFFFF; border: 1px solid #E2E8F0; "
            "border-radius: 8px; padding: 16px 20px; } "
            "QFrame#Card:hover { border-color: #CBD5E1; }"
        )
        layout = QVBoxLayout(card)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(10)

        header = QHBoxLayout()
        header.setSpacing(8)

        i_lbl = QLabel(icon)
        i_lbl.setStyleSheet("font-size: 18px;")
        header.addWidget(i_lbl)

        t_lbl = QLabel(test_name)
        t_lbl.setStyleSheet("font-size: 14px; font-weight: 700; color: #0F172A;")
        header.addWidget(t_lbl)

        s_lbl = QLabel(target_scope)
        s_lbl.setStyleSheet(
            f"background-color: {scope_color}; color: {scope_text_color}; font-weight: 700; "
            "padding: 2px 8px; border-radius: 10px; font-size: 10px;"
        )
        header.addWidget(s_lbl)

        p_lbl = QLabel(protocol)
        p_lbl.setStyleSheet(
            "background-color: #F1F5F9; color: #475569; font-weight: 600; "
            "padding: 2px 8px; border-radius: 10px; font-size: 10px; border: 1px solid #E2E8F0;"
        )
        header.addWidget(p_lbl)
        header.addStretch(1)
        layout.addLayout(header)

        grid = QGridLayout()
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(4)
        grid.setContentsMargins(4, 2, 4, 2)

        def_title = QLabel("• What it checks:")
        def_title.setStyleSheet("font-size: 11px; font-weight: 600; color: #1E293B;")
        def_val = QLabel(definition)
        def_val.setStyleSheet("font-size: 11px; color: #475569;")
        def_val.setWordWrap(True)
        grid.addWidget(def_title, 0, 0, alignment=Qt.AlignmentFlag.AlignTop)
        grid.addWidget(def_val, 0, 1)

        scen_title = QLabel("• Business Scenario:")
        scen_title.setStyleSheet("font-size: 11px; font-weight: 600; color: #1E293B;")
        scen_val = QLabel(scenario)
        scen_val.setStyleSheet("font-size: 11px; color: #475569;")
        scen_val.setWordWrap(True)
        grid.addWidget(scen_title, 1, 0, alignment=Qt.AlignmentFlag.AlignTop)
        grid.addWidget(scen_val, 1, 1)

        cfg_title = QLabel("• ⚙️ Settings Criteria:")
        cfg_title.setStyleSheet("font-size: 11px; font-weight: 600; color: #1E293B;")
        cfg_val = QLabel(config_summary)
        cfg_val.setStyleSheet("font-size: 11px; color: #475569;")
        cfg_val.setWordWrap(True)
        grid.addWidget(cfg_title, 2, 0, alignment=Qt.AlignmentFlag.AlignTop)
        grid.addWidget(cfg_val, 2, 1)

        grid.setColumnStretch(1, 1)
        layout.addLayout(grid)

        # Executed Query / Formula Code Frame
        if formula_dax:
            code_frame = QFrame()
            code_frame.setStyleSheet(
                "background-color: #0F172A; border: 1px solid #1E293B; border-radius: 6px; padding: 10px 14px;"
            )
            code_layout = QVBoxLayout(code_frame)
            code_layout.setContentsMargins(0, 0, 0, 0)
            code_layout.setSpacing(4)

            code_title = QLabel("💻  UNDERLYING FORMULA / EXECUTED DAX QUERY:")
            code_title.setStyleSheet("font-size: 10px; font-weight: 700; color: #94A3B8; letter-spacing: 0.5px;")
            code_layout.addWidget(code_title)

            code_body = QLabel(formula_dax)
            code_body.setStyleSheet(
                "font-family: Consolas, 'Cascadia Code', 'Courier New', monospace; font-size: 11px; "
                "color: #38BDF8; line-height: 1.45; background-color: transparent;"
            )
            code_body.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            code_layout.addWidget(code_body)
            layout.addWidget(code_frame)

        # Evaluation & Pass/Fail Criteria Box
        if formula_logic:
            eval_frame = QFrame()
            eval_frame.setStyleSheet(
                "background-color: #F8FAFC; border: 1px solid #E2E8F0; border-left: 3px solid #1668DC; "
                "border-radius: 4px; padding: 8px 12px;"
            )
            eval_layout = QVBoxLayout(eval_frame)
            eval_layout.setContentsMargins(0, 0, 0, 0)
            eval_layout.setSpacing(4)

            eval_title = QLabel("⚖️  EVALUATION FORMULA & PASS / FAIL CRITERIA:")
            eval_title.setStyleSheet("font-size: 10px; font-weight: 700; color: #1E293B; letter-spacing: 0.5px;")
            eval_layout.addWidget(eval_title)

            eval_body = QLabel(formula_logic)
            eval_body.setStyleSheet("font-size: 11px; color: #334155; line-height: 1.45;")
            eval_body.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            eval_layout.addWidget(eval_body)
            layout.addWidget(eval_frame)

        return card

    # =========================================================================
    # Tab 4: System Diagnostics & Environment
    # =========================================================================

    def _build_diagnostics_tab(self) -> QWidget:
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(20, 16, 20, 20)
        layout.setSpacing(14)

        intro_lbl = QLabel(
            "Runtime diagnostics, storage path inspection, local data privacy architecture, and component verification."
        )
        intro_lbl.setStyleSheet("font-size: 13px; font-weight: 600; color: #1E293B;")
        layout.addWidget(intro_lbl)

        # Card 1: Runtime Details
        info_card = QFrame()
        info_card.setObjectName("Card")
        info_card.setStyleSheet(
            "QFrame#Card { background-color: #FFFFFF; border: 1px solid #E2E8F0; "
            "border-radius: 8px; padding: 14px 18px; }"
        )
        info_layout = QVBoxLayout(info_card)
        info_layout.setContentsMargins(4, 4, 4, 4)
        info_layout.setSpacing(10)

        info_heading = QLabel("💻  Environment & Runtime Specifications")
        info_heading.setStyleSheet("font-size: 14px; font-weight: 700; color: #0F172A;")
        info_layout.addWidget(info_heading)

        grid = QGridLayout()
        grid.setHorizontalSpacing(16)
        grid.setVerticalSpacing(6)
        grid.setColumnStretch(1, 1)

        details = [
            ("Application:", APP_NAME),
            ("Version:", f"v{APP_VERSION}"),
            ("Architecture Stage:", APP_STAGE),
            ("Python Runtime:", f"{sys.version.split()[0]} ({platform.system()} {platform.release()})"),
            ("UI Framework:", f"PySide6 {pyside_version} (Qt6)"),
            ("Log Level:", self._config.log_level),
            ("Log Directory:", str(self._logs_dir) if self._logs_dir else "Not configured"),
            ("Local SQLite Database:", str(self._db_path) if self._db_path else "Not configured"),
            ("Protected Token Cache:", str(self._token_cache_path) if self._token_cache_path else "Not configured"),
        ]

        for row_idx, (label_text, value_text) in enumerate(details):
            key_lbl = QLabel(label_text)
            key_lbl.setStyleSheet("color: #475569; font-weight: 600; font-size: 12px;")
            val_lbl = QLabel(value_text)
            val_lbl.setStyleSheet("color: #0F172A; font-size: 12px;")
            val_lbl.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            val_lbl.setWordWrap(True)
            grid.addWidget(key_lbl, row_idx, 0, alignment=Qt.AlignmentFlag.AlignTop)
            grid.addWidget(val_lbl, row_idx, 1)

        info_layout.addLayout(grid)

        # Quick Actions
        action_row = QHBoxLayout()
        action_row.setSpacing(10)

        self.open_logs_button = QPushButton("📁  Open Log Folder")
        self.open_logs_button.setObjectName("SecondaryButton")
        self.open_logs_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.open_logs_button.setStyleSheet(
            "padding: 6px 12px; font-size: 12px; border-radius: 5px;"
        )
        self.open_logs_button.clicked.connect(self._open_log_folder)
        action_row.addWidget(self.open_logs_button)

        self.open_db_button = QPushButton("💾  Open Data Folder")
        self.open_db_button.setObjectName("SecondaryButton")
        self.open_db_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.open_db_button.setStyleSheet(
            "padding: 6px 12px; font-size: 12px; border-radius: 5px;"
        )
        self.open_db_button.clicked.connect(self._open_db_folder)
        action_row.addWidget(self.open_db_button)

        action_row.addStretch(1)
        info_layout.addLayout(action_row)

        layout.addWidget(info_card)

        # Card 2: Security & Privacy Architecture
        sec_card = QFrame()
        sec_card.setObjectName("Card")
        sec_card.setStyleSheet(
            "QFrame#Card { background-color: #FFFFFF; border: 1px solid #E2E8F0; "
            "border-radius: 8px; padding: 14px 18px; }"
        )
        sec_layout = QVBoxLayout(sec_card)
        sec_layout.setContentsMargins(4, 4, 4, 4)
        sec_layout.setSpacing(8)

        sec_heading = QLabel("🔒  Local-First Privacy & Enterprise Security")
        sec_heading.setStyleSheet("font-size: 14px; font-weight: 700; color: #0F172A;")
        sec_layout.addWidget(sec_heading)

        sec_points = [
            ("100% Local-First Storage", "Validation rules, schedules, and historical audit records reside exclusively in your local SQLite database on your Windows PC."),
            ("Zero Cloud Telemetry", "No customer data, queries, or validation results are transmitted to third-party cloud servers."),
            ("Official Microsoft Authentication", "Direct connection to your Power BI tenant via Microsoft Entra ID (MSAL). Tokens are encrypted using Windows Data Protection API (DPAPI)."),
        ]

        sec_grid = QGridLayout()
        sec_grid.setHorizontalSpacing(12)
        sec_grid.setVerticalSpacing(4)
        for r_idx, (p_title, p_desc) in enumerate(sec_points):
            pt_lbl = QLabel(f"✓ {p_title}:")
            pt_lbl.setStyleSheet("font-size: 12px; font-weight: 600; color: #059669;")
            pd_lbl = QLabel(p_desc)
            pd_lbl.setStyleSheet("font-size: 12px; color: #475569;")
            pd_lbl.setWordWrap(True)
            sec_grid.addWidget(pt_lbl, r_idx, 0, alignment=Qt.AlignmentFlag.AlignTop)
            sec_grid.addWidget(pd_lbl, r_idx, 1)
        sec_grid.setColumnStretch(1, 1)
        sec_layout.addLayout(sec_grid)

        layout.addWidget(sec_card)

        # Card 3: Interactive Component Health & Diagnostics
        demo_card = QFrame()
        demo_card.setObjectName("Card")
        demo_card.setStyleSheet(
            "QFrame#Card { background-color: #FFFFFF; border: 1px solid #E2E8F0; "
            "border-radius: 8px; padding: 14px 18px; }"
        )
        demo_layout = QVBoxLayout(demo_card)
        demo_layout.setContentsMargins(4, 4, 4, 4)
        demo_layout.setSpacing(10)

        demo_heading = QLabel("🧪  Component Health & Interactive Sandbox")
        demo_heading.setStyleSheet("font-size: 14px; font-weight: 700; color: #0F172A;")
        demo_layout.addWidget(demo_heading)

        demo_desc = QLabel(
            "Interactive verification of reusable UI components (NotificationBanner, Qt Model/View DataTableWidget, and ConfirmDialog)."
        )
        demo_desc.setStyleSheet("font-size: 12px; color: #64748B;")
        demo_desc.setWordWrap(True)
        demo_layout.addWidget(demo_desc)

        button_row = QHBoxLayout()
        button_row.setSpacing(10)

        self.demo_notify_btn = QPushButton("Show Sample Notice")
        self.demo_notify_btn.setObjectName("SecondaryButton")
        self.demo_notify_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.demo_notify_btn.clicked.connect(self._show_demo_notice)
        button_row.addWidget(self.demo_notify_btn)

        self.demo_confirm_btn = QPushButton("Test Confirm Dialog")
        self.demo_confirm_btn.setObjectName("PrimaryButton")
        self.demo_confirm_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.demo_confirm_btn.clicked.connect(self._run_demo_confirm)
        button_row.addWidget(self.demo_confirm_btn)

        button_row.addStretch(1)
        demo_layout.addLayout(button_row)

        self.demo_table = DataTableWidget(
            columns=_DEMO_COLUMNS,
            rows=_DEMO_ROWS,
            show_search=True,
            filter_column_key="status",
            filter_options=[s.value for s in ValidationStatus],
            parent=self,
        )
        self.demo_table.setMinimumHeight(200)
        self.demo_table.table_view.setColumnWidth(0, 52)
        self.demo_table.table_view.setColumnWidth(1, 210)
        self.demo_table.table_view.setColumnWidth(2, 340)
        self.demo_table.row_activated.connect(self._on_demo_row_activated)
        demo_layout.addWidget(self.demo_table)

        layout.addWidget(demo_card)
        return self._wrap_in_scroll_area(container)

    # =========================================================================
    # Helpers
    # =========================================================================

    def _wrap_in_scroll_area(self, content_widget: QWidget) -> QScrollArea:
        scroll = QScrollArea(self)
        scroll.setObjectName("PageScrollArea")
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setStyleSheet("QScrollArea#PageScrollArea { background-color: transparent; border: none; }")
        content_widget.setStyleSheet("background-color: transparent;")
        apply_smooth_scrolling(scroll)
        scroll.setWidget(content_widget)
        return scroll

    def _open_log_folder(self) -> None:
        if self._logs_dir is not None:
            self._logs_dir.mkdir(parents=True, exist_ok=True)
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(self._logs_dir)))

    def _open_db_folder(self) -> None:
        if self._db_path is not None:
            folder = self._db_path.parent
            folder.mkdir(parents=True, exist_ok=True)
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(folder)))

    def _show_demo_notice(self) -> None:
        self.demo_banner.show_message(
            "Shared NotificationBanner is active and ready for production validation runs.",
            level=NotificationLevel.INFO,
            title="Preview Notice",
        )

    def _run_demo_confirm(self) -> None:
        confirmed = ConfirmDialog.ask(
            self,
            title="Confirm Sample Action",
            message="Do you want to test accepting the reusable confirmation dialog?",
            detail="No local data or Power BI resources are modified by this preview.",
            confirm_text="Yes, Confirm",
            cancel_text="Cancel",
        )
        if confirmed:
            self.demo_banner.show_message(
                "Confirmation dialog accepted successfully.",
                level=NotificationLevel.SUCCESS,
                title="Confirmed",
            )
        else:
            self.demo_banner.show_message(
                "Confirmation dialog cancelled.",
                level=NotificationLevel.WARNING,
                title="Cancelled",
            )

    def _on_demo_row_activated(self, row: dict[str, object]) -> None:
        self.demo_banner.show_message(
            f"Selected row #{row.get('sr')}: {row.get('component')} ({row.get('status')})",
            level=NotificationLevel.INFO,
            title="Row Activated",
        )
