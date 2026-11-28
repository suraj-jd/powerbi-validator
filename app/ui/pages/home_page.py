"""Home / Dashboard page with authentication banner, access verifier, validation runner, and refresh monitoring (Stage 13)."""

from __future__ import annotations

from datetime import datetime
import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QFormLayout,
    QFrame,
    QFileDialog,
    QMenu,
    QInputDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.core.formatting import format_hours_duration
from app.core.status import NotificationLevel, RefreshStatus, ValidationStatus
from app.integrations.file_import import RegistrationInput
from app.integrations.powerbi.models import (
    AccessVerificationResult,
    PowerBIDataset,
    PowerBIReport,
    PowerBIWorkspace,
)
from app.ui.dialogs.refresh_details_dialog import (
    RefreshDetailsDialog,
    make_status_pill,
    update_refresh_status_pill,
)
from app.ui.dialogs.result_details_dialog import (
    ResultDetailsDialog,
    make_status_table_item,
    make_validation_status_pill,
    update_validation_status_pill,
)
from app.ui.widgets.animated_combo import AnimatedComboBox
from app.ui.widgets.enterprise import PageHeader, MetricCard, ResultsTable, action_button
from app.ui.widgets.auth_banner import AuthBanner
from app.ui.widgets.notification_banner import NotificationBanner
from app.ui.widgets.smooth_scroller import apply_smooth_scrolling

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from app.services.orchestrator_service import (
        OrchestratorService,
        ValidationResultDTO,
        ValidationRunSummaryDTO,
        ValidationWorker,
    )
    from app.services.powerbi_service import PowerBIService
    from app.services.refresh_service import RefreshService
    from app.services.registry_service import RegistryService
    from app.services.rule_service import RuleService


@dataclass
class ModelOption:
    """Option entry for semantic models discovered dynamically from Power BI."""

    workspace_name: str
    workspace_id: str
    report_name: str
    dataset_name: str
    dataset_id: str
    report_id: str | None = None
    id: int | None = None


class HomePage(QWidget):
    """Dashboard page housing authentication banner, connectivity verifier, validation runner, and refresh monitoring."""

    load_workspaces_requested = Signal()
    load_workspace_assets_requested = Signal(str)
    verify_access_requested = Signal(str, str, str)

    def __init__(
        self,
        parent: QWidget | None = None,
        *,
        refresh_service: RefreshService | None = None,
        registry_service: RegistryService | None = None,
        orchestrator_service: OrchestratorService | None = None,
        rule_service: RuleService | None = None,
        powerbi_service: PowerBIService | None = None,
        teams_alert_service: Any | None = None,
        auth_service: Any | None = None,
    ) -> None:
        super().__init__(parent)
        self._refresh_service = refresh_service
        self._registry_service = registry_service
        self._orchestrator_service = orchestrator_service
        self._rule_service = rule_service
        self._powerbi_service = powerbi_service
        self._auth_service = auth_service
        self._validation_worker: ValidationWorker | None = None
        self._current_results: list[ValidationResultDTO] = []
        self._workspaces: list[PowerBIWorkspace] = []
        self._workspace_assets: dict[str, tuple[list[PowerBIDataset], list[PowerBIReport]]] = {}
        self._datasets: list[PowerBIDataset] = []
        self._reports: list[PowerBIReport] = []

        from app.services.scheduler_service import ValidationSchedulerService
        from app.services.teams_alert_service import TeamsAlertService

        db = getattr(self._orchestrator_service, "_db", None) if self._orchestrator_service else None
        self._scheduler_service = ValidationSchedulerService(db=db, parent=self)
        self._scheduler_service.schedule_triggered.connect(self._on_schedule_triggered)
        self._scheduler_service.schedule_config_changed.connect(self._update_schedule_badge)

        if teams_alert_service is not None:
            self._teams_alert_service = teams_alert_service
        else:
            token_prov = self._auth_service.get_access_token if self._auth_service else None
            self._teams_alert_service = TeamsAlertService(db=db, token_provider=token_prov, parent=self)
        self._teams_alert_service.config_changed.connect(self._update_teams_badge)

        self._build_ui()
        self._update_schedule_badge()
        self._update_teams_badge()
        self._connect_refresh_service()
        self._connect_validation_service()
        self.reload_registered_models()

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self.reload_registered_models()

    def _handle_refresh_models_clicked(self) -> None:
        self.load_workspaces_requested.emit()
        if self._powerbi_service is not None and not self._powerbi_service.is_busy:
            self._powerbi_service.sync_all_workspaces_and_assets_async()
        self.reload_registered_models()

    def reload_registered_models(self) -> None:
        """Populate the active semantic model dropdown with registered and live Power BI models."""
        current_ds_id = self.dataset_id_input.text().strip()
        self.model_selector_combo.blockSignals(True)
        self.model_selector_combo.clear()

        registered_keys: set[tuple[str, str]] = set()
        items: list[tuple[str, Any]] = []

        # 1. Models registered in SQLite
        if self._registry_service is not None:
            registrations = self._registry_service.list_registrations(active_only=True)
            for reg in registrations:
                display = f"{reg.report_name} ({reg.workspace_name})"
                items.append((display, reg))
                registered_keys.add((reg.workspace_id.lower(), reg.dataset_id.lower()))

        # 2. Live Power BI workspaces and datasets/reports
        workspaces_to_check = list(self._workspaces)
        if not workspaces_to_check and self._powerbi_service is not None:
            workspaces_to_check = self._powerbi_service.cached_workspaces

        for ws in workspaces_to_check:
            ws_key = ws.id.lower()
            if ws_key in self._workspace_assets:
                datasets, reports = self._workspace_assets[ws_key]
            elif self._powerbi_service is not None:
                datasets = self._powerbi_service.get_cached_datasets(ws.id)
                reports = self._powerbi_service.get_cached_reports(ws.id)
            else:
                datasets, reports = [], []

            for ds in datasets:
                pair = (ws.id.lower(), ds.id.lower())
                if pair not in registered_keys:
                    matching_rpt = next(
                        (r for r in reports if (r.dataset_id or "").lower() == ds.id.lower()),
                        None,
                    )
                    rpt_name = matching_rpt.name if matching_rpt else ds.name
                    rpt_id = matching_rpt.id if matching_rpt else None
                    display = f"{rpt_name} ({ws.name})"
                    opt = ModelOption(
                        workspace_name=ws.name,
                        workspace_id=ws.id,
                        report_name=rpt_name,
                        dataset_name=ds.name,
                        dataset_id=ds.id,
                        report_id=rpt_id,
                    )
                    items.append((display, opt))
                    registered_keys.add(pair)

        if not items:
            self.model_selector_combo.addItem("No semantic models registered yet", None)
        else:
            select_idx = 0
            for idx, (display, data) in enumerate(items):
                self.model_selector_combo.addItem(display, data)
                ds_id = getattr(data, "dataset_id", "")
                if current_ds_id and ds_id and ds_id.lower() == current_ds_id.lower():
                    select_idx = idx
            self.model_selector_combo.setCurrentIndex(select_idx)

        self.model_selector_combo.blockSignals(False)
        self._on_model_selector_changed(self.model_selector_combo.currentIndex())
        count = self._get_enabled_sheet_rules_count()
        self.overview_header.subtitle.setText(f"{count} enabled checks across your configured reports")

    def _on_model_selector_changed(self, index: int) -> None:
        if index < 0:
            return
        reg = self.model_selector_combo.itemData(index)
        if reg is not None and hasattr(reg, "workspace_id"):
            if hasattr(self, "resource_access_label"):
                current_context = (reg.workspace_id, reg.dataset_id)
                if current_context != getattr(self, "_inspected_context", None):
                    self._inspected_context = current_context
                    self.resource_access_label.setText("Report permissions have not been checked. Choose Verify Access for this report.")
            self.workspace_id_input.setText(reg.workspace_id)
            self.dataset_id_input.setText(reg.dataset_id)
            self.report_id_input.setText(reg.report_id or "")
            self._update_validation_ui()
            self._update_refresh_ui()

    def _build_ui(self) -> None:
        outer_layout = QVBoxLayout(self)
        outer_layout.setContentsMargins(0, 0, 0, 0)

        scroll_area = QScrollArea(self)
        scroll_area.setObjectName("PageScrollArea")
        scroll_area.setWidgetResizable(True)
        scroll_area.setFrameShape(QFrame.Shape.NoFrame)

        container = QWidget(scroll_area)
        container.setObjectName("PageContainer")
        layout = QVBoxLayout(container)
        layout.setContentsMargins(24, 16, 24, 16)
        layout.setSpacing(12)

        # Stage 3 Authentication Banner
        self.auth_banner = AuthBanner(container)
        layout.addWidget(self.auth_banner)

        # Verification Banner & Details (hidden by default; displayed only on explicit access verification)
        self.verification_banner = NotificationBanner(container)
        self.verification_banner.hide()
        layout.addWidget(self.verification_banner)

        self.verification_details_label = QLabel("", container)
        self.verification_details_label.setObjectName("BodyText")
        self.verification_details_label.setWordWrap(True)
        self.verification_details_label.hide()
        layout.addWidget(self.verification_details_label)

        header = PageHeader("Report health", "All configured reports · Validate your enabled checks and review what needs attention.")
        self.overview_header = header
        layout.addWidget(header)

        # Internal/backward-compatible widgets (kept hidden to support APIs and test fixtures)
        self.workspace_id_input = QLineEdit(container)
        self.workspace_id_input.hide()
        self.dataset_id_input = QLineEdit(container)
        self.dataset_id_input.hide()
        self.report_id_input = QLineEdit(container)
        self.report_id_input.hide()

        self.workspace_combo = QComboBox(container)
        self.workspace_combo.hide()
        self.workspace_combo.currentIndexChanged.connect(self._on_workspace_selected)

        self.dataset_combo = QComboBox(container)
        self.dataset_combo.hide()
        self.dataset_combo.currentIndexChanged.connect(self._on_dataset_selected)

        self.load_workspaces_button = QPushButton("Load My Workspaces", container)
        self.load_workspaces_button.hide()
        self.load_workspaces_button.clicked.connect(self.load_workspaces_requested.emit)

        self.verify_access_button = QPushButton("Verify Access", container)
        self.verify_access_button.hide()
        self.verify_access_button.clicked.connect(self._emit_verify_access)

        # Stage 13 Validation Results & Model Health Dashboard Card
        self.validation_card = self._create_validation_dashboard_card(container)
        layout.addWidget(self.validation_card, 1)

        # Stage 8 Dataset Refresh Health & Monitoring Card (hidden to keep Home focused strictly on today's validation)
        self.refresh_card = self._create_refresh_monitoring_card(container)
        self.refresh_card.hide()
        self.model_selector_combo.hide()
        self.refresh_models_button.hide()
        self.resource_access_label = QLabel("Report permissions have not been checked.")
        self.resource_access_label.hide()


        scroll_area.setWidget(container)
        outer_layout.addWidget(scroll_area)

    def set_connectivity_busy(self, busy: bool) -> None:
        self.load_workspaces_button.setEnabled(not busy)
        self.verify_access_button.setEnabled(not busy)
        self.verify_access_button.setText("Verifying..." if busy else "Verify Access")

    def set_workspaces(self, workspaces: list[PowerBIWorkspace]) -> None:
        self._workspaces = list(workspaces)
        self.workspace_combo.blockSignals(True)
        self.workspace_combo.clear()
        self.workspace_combo.addItem(f"Select workspace ({len(workspaces)} found)", "")
        for ws in workspaces:
            self.workspace_combo.addItem(f"{ws.name} ({ws.id})", ws.id)
        self.workspace_combo.blockSignals(False)
        self.reload_registered_models()

    def set_workspace_assets(
        self,
        workspace_id: str,
        datasets: list[PowerBIDataset],
        reports: list[PowerBIReport],
    ) -> None:
        self._workspace_assets[workspace_id.lower()] = (list(datasets), list(reports))
        self._datasets = list(datasets)
        self._reports = list(reports)

        self.dataset_combo.blockSignals(True)
        self.dataset_combo.clear()
        self.dataset_combo.addItem(f"Select dataset ({len(datasets)} found)", "")
        for ds in datasets:
            self.dataset_combo.addItem(f"{ds.name} ({ds.id})", ds.id)
        self.dataset_combo.blockSignals(False)
        self.reload_registered_models()

    def display_verification_result(self, result: AccessVerificationResult) -> None:
        """Render the verified permission summary and update the top AuthBanner."""
        if result.is_verified and not result.issues:
            level = NotificationLevel.SUCCESS
            title = "Access Verified"
        elif result.is_verified:
            level = NotificationLevel.WARNING
            title = "Verified with Warnings"
        else:
            level = NotificationLevel.ERROR
            title = "Access Not Verified"

        self.verification_banner.show_message(result.summary, level=level, title=title)
        if (result.workspace_id, result.dataset_id) == getattr(self, "_inspected_context", None):
            self.resource_access_label.setText("Report access verified" if result.is_verified else "Report access could not be verified. Review the details above.")

        ws_label = result.workspace.name if result.workspace else result.workspace_id
        ds_label = result.dataset.name if result.dataset else result.dataset_id
        lines = [
            f"Workspace: {ws_label}  |  Accessible: {'Yes' if result.workspace_accessible else 'No'}",
            f"Effective Access Level: {result.effective_access_level}",
            f"Dataset: {ds_label}  |  Accessible: {'Yes' if result.dataset_accessible else 'No'}",
        ]
        if result.report_id:
            rpt_label = result.report.name if result.report else result.report_id
            lines.append(
                f"Report: {rpt_label}  |  Accessible: {'Yes' if result.report_accessible else 'No'}"
            )
        if result.issues:
            lines.append("Notes / Issues:")
            lines.extend(f"• {issue}" for issue in result.issues)

        self.verification_details_label.setText("\n".join(lines))
        self.verification_details_label.show()

        if result.workspace_accessible:
            self.auth_banner.set_workspace_access_label(
                f"{ws_label} - {result.effective_access_level}"
            )
        else:
            self.auth_banner.set_workspace_access_label("Not Accessible")

    def _on_workspace_selected(self, _index: int) -> None:
        ws_id = str(self.workspace_combo.currentData() or "")
        if ws_id:
            self.workspace_id_input.setText(ws_id)
            self.load_workspace_assets_requested.emit(ws_id)

    def _on_dataset_selected(self, _index: int) -> None:
        ds_id = str(self.dataset_combo.currentData() or "")
        if ds_id:
            self.dataset_id_input.setText(ds_id)
            # Auto-fill a matching report ID if one binds to this dataset
            matching = next(
                (r for r in self._reports if (r.dataset_id or "").lower() == ds_id.lower()),
                None,
            )
            if matching is not None:
                self.report_id_input.setText(matching.id)

    def _emit_verify_access(self) -> None:
        self.verify_access_requested.emit(
            self.workspace_id_input.text().strip(),
            self.dataset_id_input.text().strip(),
            self.report_id_input.text().strip(),
        )

    def _create_refresh_monitoring_card(self, container: QWidget) -> QFrame:
        card = QFrame(container)
        card.setObjectName("Card")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(22, 20, 22, 20)
        layout.setSpacing(12)

        card_header = QHBoxLayout()
        section_title = QLabel("Power BI refresh history")
        section_title.setWordWrap(True)
        section_title.setObjectName("SectionTitle")
        card_header.addWidget(section_title, stretch=1)

        self.fetch_refresh_button = action_button("Fetch refresh history", "refresh")
        self.fetch_refresh_button.setObjectName("SecondaryButton")
        self.fetch_refresh_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.fetch_refresh_button.setToolTip("Retrieve the latest refresh history from Power BI for this dataset.")
        self.fetch_refresh_button.clicked.connect(self._handle_fetch_refresh)
        refresh_actions = QHBoxLayout()
        refresh_actions.addWidget(self.fetch_refresh_button)

        self.view_refresh_details_button = action_button("View refresh details", "history")
        self.view_refresh_details_button.setObjectName("PrimaryButton")
        self.view_refresh_details_button.setStyleSheet(
            "background-color: #2563EB; color: #FFFFFF; font-weight: 600; padding: 7px 14px; border-radius: 6px;"
        )
        self.view_refresh_details_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.view_refresh_details_button.setToolTip("Open detailed refresh history logs and diagnostics.")
        self.view_refresh_details_button.clicked.connect(self._handle_view_refresh_details)
        refresh_actions.addWidget(self.view_refresh_details_button)
        refresh_actions.addStretch(1)
        layout.addLayout(card_header)
        layout.addLayout(refresh_actions)

        desc = QLabel(
            "Inspect execution history, track refresh durations, and distinguish the latest attempt "
            "from the latest successful refresh for the selected dataset."
        )
        desc.setObjectName("PageSubtitle")
        desc.setWordWrap(True)
        layout.addWidget(desc)

        self.refresh_banner = NotificationBanner(card)
        layout.addWidget(self.refresh_banner)

        # 3 KPI summary cards row
        kpi_row = QHBoxLayout()
        kpi_row.setSpacing(12)

        # 1. Latest Attempt
        card_attempt = QFrame()
        card_attempt.setObjectName("Card")
        card_attempt.setStyleSheet(
            "QFrame#Card { background-color: #FFFFFF; border: 1px solid #DDE4ED; border-radius: 8px; } "
            "QLabel { border: none; background: transparent; }"
        )
        lay_att = QVBoxLayout(card_attempt)
        lay_att.setContentsMargins(14, 12, 14, 12)
        lay_att.setSpacing(6)
        lbl_att_title = QLabel("LATEST REFRESH ATTEMPT")
        lbl_att_title.setStyleSheet("color: #64748B; font-size: 11px; font-weight: 700; letter-spacing: 0.5px;")
        lay_att.addWidget(lbl_att_title)

        self.home_attempt_pill_container = QWidget()
        p_layout = QHBoxLayout(self.home_attempt_pill_container)
        p_layout.setContentsMargins(0, 0, 0, 0)
        self.home_attempt_pill = make_status_pill(RefreshStatus.UNKNOWN)
        p_layout.addWidget(self.home_attempt_pill)
        p_layout.addStretch(1)
        lay_att.addWidget(self.home_attempt_pill_container)

        self.home_attempt_start = QLabel("Start: -")
        self.home_attempt_start.setStyleSheet("color: #64748B; font-size: 11px;")
        lay_att.addWidget(self.home_attempt_start)
        self.home_attempt_duration = QLabel("Duration: -")
        self.home_attempt_duration.setStyleSheet("color: #16243A; font-size: 12px; font-weight: 600;")
        lay_att.addWidget(self.home_attempt_duration)
        kpi_row.addWidget(card_attempt)

        # 2. Latest Success
        card_success = QFrame()
        card_success.setObjectName("Card")
        card_success.setStyleSheet(
            "QFrame#Card { background-color: #FFFFFF; border: 1px solid #DDE4ED; border-radius: 8px; } "
            "QLabel { border: none; background: transparent; }"
        )
        lay_suc = QVBoxLayout(card_success)
        lay_suc.setContentsMargins(14, 12, 14, 12)
        lay_suc.setSpacing(6)
        lbl_suc_title = QLabel("LATEST SUCCESSFUL REFRESH")
        lbl_suc_title.setStyleSheet("color: #64748B; font-size: 11px; font-weight: 700; letter-spacing: 0.5px;")
        lay_suc.addWidget(lbl_suc_title)

        self.home_success_time = QLabel("-")
        self.home_success_time.setStyleSheet("color: #059669; font-size: 14px; font-weight: 700;")
        lay_suc.addWidget(self.home_success_time)
        self.home_success_age = QLabel("Age: -")
        self.home_success_age.setStyleSheet("color: #64748B; font-size: 11px;")
        lay_suc.addWidget(self.home_success_age)
        self.home_success_duration = QLabel("Duration: -")
        self.home_success_duration.setStyleSheet("color: #16243A; font-size: 12px; font-weight: 600;")
        lay_suc.addWidget(self.home_success_duration)
        kpi_row.addWidget(card_success)

        # 3. Overall Reliability
        card_rel = QFrame()
        card_rel.setObjectName("Card")
        card_rel.setStyleSheet(
            "QFrame#Card { background-color: #FFFFFF; border: 1px solid #DDE4ED; border-radius: 8px; } "
            "QLabel { border: none; background: transparent; }"
        )
        lay_rel = QVBoxLayout(card_rel)
        lay_rel.setContentsMargins(14, 12, 14, 12)
        lay_rel.setSpacing(6)
        lbl_rel_title = QLabel("HISTORICAL RELIABILITY")
        lbl_rel_title.setStyleSheet("color: #64748B; font-size: 11px; font-weight: 700; letter-spacing: 0.5px;")
        lay_rel.addWidget(lbl_rel_title)

        self.home_reliability_rate = QLabel("No Data")
        self.home_reliability_rate.setStyleSheet("color: #2563EB; font-size: 15px; font-weight: 700;")
        lay_rel.addWidget(self.home_reliability_rate)
        self.home_reliability_detail = QLabel("Recorded Runs: 0")
        self.home_reliability_detail.setStyleSheet("color: #64748B; font-size: 11px;")
        lay_rel.addWidget(self.home_reliability_detail)
        kpi_row.addWidget(card_rel)

        layout.addLayout(kpi_row)
        return card

    def _connect_refresh_service(self) -> None:
        if self._refresh_service is not None:
            self._refresh_service.refresh_loaded.connect(self._on_refresh_loaded)
            self._refresh_service.refresh_failed.connect(self._on_refresh_failed)
        self.dataset_id_input.textChanged.connect(lambda _: self._update_refresh_ui())

    def _get_active_workspace_and_dataset(self) -> tuple[str, str, str]:
        ws_id = self.workspace_id_input.text().strip()
        ds_id = self.dataset_id_input.text().strip()
        reg = self.model_selector_combo.currentData() if hasattr(self, "model_selector_combo") else None
        if reg is not None and hasattr(reg, "report_name") and reg.report_name:
            ds_name = reg.report_name
        elif hasattr(self, "dataset_combo") and self.dataset_combo.currentIndex() > 0:
            ds_name = self.dataset_combo.currentText().split(" (")[0]
        else:
            ds_name = f"Dataset {ds_id[:8]}" if ds_id else ""
        return ws_id, ds_id, ds_name

    def _get_or_create_registration(self) -> int | None:
        ws_id, ds_id, ds_name = self._get_active_workspace_and_dataset()
        if not ws_id or not ds_id:
            return None
        if self._registry_service is None:
            return None

        existing = self._registry_service.find_by_workspace_and_dataset(ws_id, ds_id)
        if existing is not None:
            return existing.id

        # Auto-create registration so refresh history can be indexed and persisted cleanly
        ws_name = f"Workspace {ws_id[:8]}"
        reg = self.model_selector_combo.currentData() if hasattr(self, "model_selector_combo") else None
        if reg is not None and hasattr(reg, "workspace_name") and reg.workspace_name:
            ws_name = reg.workspace_name
        elif hasattr(self, "workspace_combo") and self.workspace_combo.currentIndex() > 0:
            ws_name = self.workspace_combo.currentText().split(" (")[0]

        rpt_id = self.report_id_input.text().strip() or None
        created = self._registry_service.create_registration(
            RegistrationInput(
                workspace_name=ws_name,
                workspace_id=ws_id,
                report_name=ds_name or f"Report for {ds_id[:8]}",
                report_id=rpt_id,
                dataset_name=ds_name,
                dataset_id=ds_id,
                is_active=True,
            )
        )
        return created.id

    def _update_refresh_ui(self) -> None:
        ws_id, ds_id, _ = self._get_active_workspace_and_dataset()
        if not ws_id or not ds_id or self._refresh_service is None or self._registry_service is None:
            self._reset_refresh_cards()
            return

        existing = self._registry_service.find_by_workspace_and_dataset(ws_id, ds_id)
        if existing is None:
            self._reset_refresh_cards()
            return

        summary = self._refresh_service.get_refresh_summary(existing.id)

        # Update Latest Attempt
        latest = summary.latest_attempt
        if latest is not None:
            update_refresh_status_pill(self.home_attempt_pill, latest.status)
            self.home_attempt_start.setText(f"Start: {latest.start_time_display}")
            self.home_attempt_duration.setText(f"Duration: {latest.duration_display}")
        else:
            self._reset_attempt_pill()
            self.home_attempt_start.setText("Start: -")
            self.home_attempt_duration.setText("Duration: -")

        # Update Latest Success
        latest_success = summary.latest_successful
        if latest_success is not None:
            self.home_success_time.setText(latest_success.end_time_display)
            age_disp = format_hours_duration(latest_success.age_hours)
            age_str = f"Age: {age_disp} ago" if latest_success.age_hours is not None else "Age: -"
            self.home_success_age.setText(age_str)
            self.home_success_duration.setText(f"Duration: {latest_success.duration_display}")
        else:
            self.home_success_time.setText("None Recorded")
            self.home_success_age.setText("Age: -")
            self.home_success_duration.setText("Duration: -")

        # Update Reliability
        self.home_reliability_rate.setText(summary.success_rate_display)
        self.home_reliability_detail.setText(
            f"Total: {summary.total_runs} (Passed: {summary.success_count}, Failed: {summary.failure_count})"
        )

    def _reset_attempt_pill(self) -> None:
        update_refresh_status_pill(self.home_attempt_pill, RefreshStatus.UNKNOWN)

    def _reset_refresh_cards(self) -> None:
        self._reset_attempt_pill()
        self.home_attempt_start.setText("Start: -")
        self.home_attempt_duration.setText("Duration: -")
        self.home_success_time.setText("-")
        self.home_success_age.setText("Age: -")
        self.home_success_duration.setText("Duration: -")
        self.home_reliability_rate.setText("No Data")
        self.home_reliability_detail.setText("Recorded Runs: 0")

    def _handle_fetch_refresh(self) -> None:
        ws_id, ds_id, _ = self._get_active_workspace_and_dataset()
        if not ws_id or not ds_id:
            self.refresh_banner.show_message(
                "Please select or enter a valid Workspace ID and Dataset ID above first.",
                level=NotificationLevel.WARNING,
                title="Input Required",
            )
            return

        if self._refresh_service is None or self._registry_service is None:
            self.refresh_banner.show_message(
                "Refresh monitoring service is not initialized.",
                level=NotificationLevel.ERROR,
                title="Service Unavailable",
            )
            return

        reg_id = self._get_or_create_registration()
        if reg_id is None:
            return

        self.fetch_refresh_button.setEnabled(False)
        self.fetch_refresh_button.setText("Fetching Refreshes...")
        self.refresh_banner.hide()
        self._refresh_service.fetch_refreshes_async(
            workspace_registration_id=reg_id,
            workspace_id=ws_id,
            dataset_id=ds_id,
            top=15,
        )

    def _on_refresh_loaded(self, reg_id: int, records: list) -> None:
        self.fetch_refresh_button.setEnabled(True)
        self.fetch_refresh_button.setText("↻  Fetch Live Refresh History")
        active_reg_id = self._get_or_create_registration()
        if active_reg_id == reg_id:
            self.refresh_banner.show_message(
                f"Synchronized {len(records)} Power BI refresh records for this dataset.",
                level=NotificationLevel.SUCCESS,
                title="Refreshes Updated",
            )
            self._update_refresh_ui()

    def _on_refresh_failed(self, reg_id: int, error_message: str) -> None:
        self.fetch_refresh_button.setEnabled(True)
        self.fetch_refresh_button.setText("↻  Fetch Live Refresh History")
        self.refresh_banner.show_message(
            f"Could not retrieve refresh history: {error_message}",
            level=NotificationLevel.ERROR,
            title="Refresh Error",
        )

    def _handle_view_refresh_details(self) -> None:
        ws_id, ds_id, ds_name = self._get_active_workspace_and_dataset()
        if not ws_id or not ds_id:
            self.refresh_banner.show_message(
                "Please select or enter a valid Workspace ID and Dataset ID above first.",
                level=NotificationLevel.WARNING,
                title="Input Required",
            )
            return

        if self._refresh_service is None:
            self.refresh_banner.show_message(
                "Refresh monitoring service is not initialized.",
                level=NotificationLevel.ERROR,
                title="Service Unavailable",
            )
            return

        reg_id = self._get_or_create_registration()
        if reg_id is None:
            return

        dialog = RefreshDetailsDialog(
            workspace_registration_id=reg_id,
            workspace_id=ws_id,
            dataset_id=ds_id,
            registration_display_name=ds_name or ds_id[:8],
            refresh_service=self._refresh_service,
            parent=self,
        )
        dialog.exec()
        self._update_refresh_ui()

    # =========================================================================
    # Stage 13: Validation Execution & Health Dashboard Card
    # =========================================================================

    def _create_validation_dashboard_card(self, container: QWidget) -> QFrame:
        card = QFrame(container)
        card.setObjectName("Card")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(10)

        actions = QHBoxLayout()
        scope = QLabel("All configured reports · All enabled checks")
        scope.setObjectName("SectionTitle")
        scope.setWordWrap(True)
        scope.hide()
        self.cancel_validation_button = action_button("Cancel run", "close")
        self.cancel_validation_button.clicked.connect(self._cancel_validation)
        self.cancel_validation_button.hide()
        self.overview_header.actions.addWidget(self.cancel_validation_button)
        self.run_validation_button = action_button("Run all enabled checks", "run", primary=True)
        self.run_validation_button.setToolTip("Execute every enabled Validation Sheet check across all configured reports.")
        self.run_validation_button.clicked.connect(self._run_validation)
        self.overview_header.actions.addWidget(self.run_validation_button)

        self.home_overall_timing = QLabel("No validation runs recorded yet")
        self.home_overall_timing.setObjectName("RunContext")
        self.home_overall_timing.setWordWrap(True)
        layout.addWidget(self.home_overall_timing)
        summary = QHBoxLayout()
        self.home_overall_pill = make_validation_status_pill("NOT RUN")
        summary.addWidget(self.home_overall_pill)
        self.attention_summary = QLabel("Run validation to see which checks need attention.")
        self.attention_summary.setWordWrap(True)
        summary.addWidget(self.attention_summary, 1)
        layout.addLayout(summary)

        kpis = QHBoxLayout()
        for outcome, attribute in [("PASS", "home_passed_count"), ("FAIL", "home_failed_count"),
                                   ("WARNING", "home_warning_count"), ("ERROR", "home_error_count")]:
            metric = MetricCard(outcome)
            setattr(self, attribute, metric.value)
            kpis.addWidget(metric, 1)
        layout.addLayout(kpis)

        self.validation_progress_label = QLabel("Preparing checks…")
        self.validation_progress_bar = QProgressBar()
        self.validation_progress_bar.setRange(0, 100)
        self.validation_progress_label.hide()
        self.validation_progress_bar.hide()
        layout.addWidget(self.validation_progress_label)
        layout.addWidget(self.validation_progress_bar)
        self.validation_banner = NotificationBanner(card)
        layout.addWidget(self.validation_banner)

        tools = QHBoxLayout()
        title = QLabel("Validation results")
        title.setObjectName("SectionTitle")
        tools.addWidget(title)
        self.results_search_input = QLineEdit()
        self.results_search_input.setPlaceholderText("Search checks, targets, or outcomes…")
        self.results_search_input.setClearButtonEnabled(True)
        self.results_search_input.textChanged.connect(self._apply_results_filter)
        tools.addWidget(self.results_search_input, 1)
        self.results_status_filter = QComboBox()
        self.results_status_filter.addItems(["All outcomes", "Failed", "Warnings", "Execution errors", "Passed"])
        self.results_status_filter.currentIndexChanged.connect(self._apply_results_filter)
        tools.addWidget(self.results_status_filter)
        self.export_results_button = action_button("Export run", "export")
        menu = QMenu(self.export_results_button)
        menu.addAction("Latest displayed run as CSV", lambda: self._export_displayed_run("csv"))
        menu.addAction("Latest displayed run as Excel", lambda: self._export_displayed_run("xlsx"))
        self.export_results_button.setMenu(menu)
        self.export_results_button.setEnabled(False)
        tools.addWidget(self.export_results_button)
        layout.addLayout(tools)

        self.results_table = ResultsTable()
        self.results_table.cellDoubleClicked.connect(self._handle_table_double_clicked)
        self.results_table.cellClicked.connect(self._handle_table_clicked)
        self.results_table.model().layoutChanged.connect(lambda *_: self._apply_results_filter())
        self.results_table.hide()
        layout.addWidget(self.results_table)
        self.empty_results_label = QLabel("No validation runs yet. Add checks in Validation Sheet, then run validation.")
        self.empty_results_label.setWordWrap(True)
        self.empty_results_label.setObjectName("MutedText")
        layout.addWidget(self.empty_results_label)
        self.results_count_label = QLabel("")
        self.results_count_label.setObjectName("MutedText")
        layout.addWidget(self.results_count_label)

        self.schedule_badge = QLabel()
        self.schedule_badge.setObjectName("MutedText")
        self.schedule_badge.setWordWrap(True)
        layout.insertWidget(1, self.schedule_badge)
        self.schedule_validation_button = action_button("Schedule", "schedule")
        self.schedule_validation_button.setToolTip("Choose when all enabled validation checks run automatically.")
        self.schedule_validation_button.clicked.connect(self._open_schedule_dialog)
        self.overview_header.actions.insertWidget(0, self.schedule_validation_button)
        self.teams_alerts_button = action_button("Teams alerts", "alerts")
        self.teams_alerts_button.setToolTip("Configure Microsoft Teams validation alerts.")
        self.teams_alerts_button.clicked.connect(self._open_teams_dialog)
        self.overview_header.actions.insertWidget(1, self.teams_alerts_button)
        self.teams_badge = QLabel()
        self.teams_badge.hide()
        more = action_button("More")
        more_menu = QMenu(more)
        more_menu.addAction("Power BI refresh history…", self._open_refresh_history)
        more_menu.addAction("Sync reports", self._handle_refresh_models_clicked)
        more.setMenu(more_menu)
        tools.addWidget(more)

        self.model_selector_combo = AnimatedComboBox(card)
        self.model_selector_combo.currentIndexChanged.connect(self._on_model_selector_changed)
        self.refresh_models_button = action_button("Sync reports", "refresh")
        self.refresh_models_button.clicked.connect(self._handle_refresh_models_clicked)
        self.model_selector_combo.hide()
        self.refresh_models_button.hide()
        return card

    def _open_refresh_history(self) -> None:
        """Optional source-refresh inspection, kept out of validation results."""
        registrations = self._registry_service.list_registrations(active_only=True) if self._registry_service else []
        if not registrations or self._refresh_service is None:
            self.validation_banner.show_message("Add a report in Validation Sheet before inspecting its Power BI refresh history.", level=NotificationLevel.INFO)
            return
        registration = registrations[0]
        if len(registrations) > 1:
            names = [f"{r.workspace_name} / {r.report_name}" for r in registrations]
            selected, accepted = QInputDialog.getItem(self, "Power BI refresh history", "Report / model", names, 0, False)
            if not accepted:
                return
            registration = registrations[names.index(selected)]
        dialog = RefreshDetailsDialog(workspace_registration_id=registration.id,
            workspace_id=registration.workspace_id, dataset_id=registration.dataset_id,
            registration_display_name=f"{registration.workspace_name} / {registration.report_name}",
            refresh_service=self._refresh_service, parent=self)
        dialog.exec()

    def _export_displayed_run(self, extension: str) -> None:
        summary = getattr(self, "_displayed_summary", None)
        if summary is None:
            return
        from app.services.export_service import export_run_to_csv, export_run_to_xlsx
        destination, _ = QFileDialog.getSaveFileName(self, "Export displayed validation results",
            f"validation-results.{extension}", "CSV (*.csv)" if extension == "csv" else "Excel (*.xlsx)")
        if destination:
            try:
                dest = (export_run_to_csv if extension == "csv" else export_run_to_xlsx)(summary, destination)
                self.validation_banner.show_export_success(
                    f"Validation results exported to '{dest.name}'.",
                    dest,
                    title="Export Complete",
                )
            except Exception as exc:
                self.validation_banner.show_message(str(exc), level=NotificationLevel.ERROR, title="Export failed")

    def _connect_validation_service(self) -> None:
        self.dataset_id_input.textChanged.connect(lambda _: self._update_validation_ui())

    def _update_validation_ui(self) -> None:
        if self._orchestrator_service is None:
            self._reset_validation_ui()
            return

        latest_run = None
        if hasattr(self._orchestrator_service, "get_latest_run"):
            try:
                latest_run = self._orchestrator_service.get_latest_run()
            except Exception:
                pass

        if latest_run is None and self._registry_service is not None:
            ws_id, ds_id, _ = self._get_active_workspace_and_dataset()
            if ws_id and ds_id:
                existing = self._registry_service.find_by_workspace_and_dataset(ws_id, ds_id)
                if existing is not None and hasattr(self._orchestrator_service, "get_latest_run_for_registration"):
                    latest_run = self._orchestrator_service.get_latest_run_for_registration(existing.id)

        if latest_run is not None:
            self._display_run_summary(latest_run)
        else:
            self._reset_validation_ui()

    def _reset_validation_ui(self) -> None:
        update_validation_status_pill(self.home_overall_pill, "NOT RUN")

        self.home_overall_timing.setText("No validation runs recorded yet")
        self.attention_summary.setText("Run validation to see which checks need attention.")
        self.export_results_button.setEnabled(False)
        self._displayed_summary = None
        self.home_passed_count.setText("0")
        self.home_failed_count.setText("0")
        self.home_warning_count.setText("0")
        self.home_error_count.setText("0")

        self.results_table.setRowCount(0)
        self.results_table.hide()
        self.empty_results_label.show()
        self._current_results = []

    @property
    def scheduler_service(self):
        return self._scheduler_service

    def _get_enabled_sheet_rules_count(self) -> int:
        """Count how many validation rules are active and enabled in the Validation Sheet."""
        db = getattr(self._orchestrator_service, "_db", None) if self._orchestrator_service else None
        if db is not None:
            try:
                from app.services.sheet_service import SheetService
                sheet_svc = SheetService(
                    db=db,
                    registry_service=self._registry_service,
                    rule_service=self._rule_service,
                )
                rows = sheet_svc.load_sheet_rows()
                return sum(1 for r in rows if r.enabled and r.workspace_id and r.dataset_id)
            except Exception as exc:
                logger.debug("Error checking sheet rows count: %s", exc)
        elif self._rule_service is not None and self._registry_service is not None:
            regs = self._registry_service.list_registrations(active_only=True)
            cnt = 0
            for reg in regs:
                cnt += len(self._rule_service.list_rules(reg.id, enabled_only=True))
            return cnt
        return 0

    def _get_current_account(self) -> Any | None:
        """Retrieve the active Microsoft user account from the auth service."""
        if self._auth_service and hasattr(self._auth_service, "state"):
            return self._auth_service.state.account
        return None

    def _update_teams_badge(self, config: Any = None) -> None:
        """Render the Microsoft Teams alert status badge."""
        if not hasattr(self, "teams_badge"):
            return
        cfg = config or self._teams_alert_service.config
        if cfg.enabled:
            mode_text = "All" if cfg.notify_on == "all" else ("Critical" if cfg.notify_on == "failure_strict" else "Violations")
            self.teams_badge.setText(f"🔔 Teams: {mode_text}")
            self.teams_badge.setStyleSheet(
                "color: #15803D; background: #DCFCE7; font-size: 11px; font-weight: 600; "
                "border: 1px solid #BBF7D0; border-radius: 5px; padding: 4px 8px;"
            )
            self.teams_badge.setToolTip(f"Microsoft Teams alerts active ({cfg.notify_on} mode). Click 'Teams Alerts...' to configure.")
        else:
            self.teams_badge.setText("🔔 Teams: Off")
            self.teams_badge.setStyleSheet(
                "color: #64748B; background: #F1F5F9; font-size: 11px; font-weight: 600; "
                "border: 1px solid #DDE4ED; border-radius: 5px; padding: 4px 8px;"
            )
            self.teams_badge.setToolTip("Microsoft Teams alerts disabled. Click 'Teams Alerts...' to configure.")

    def _open_teams_dialog(self) -> None:
        """Open the Microsoft Teams alert configuration dialog."""
        from app.ui.dialogs.teams_alert_dialog import TeamsAlertConfigDialog

        dlg = TeamsAlertConfigDialog(
            teams_service=self._teams_alert_service,
            account=self._get_current_account(),
            parent=self,
        )
        if dlg.exec():
            self._update_teams_badge()

    def _update_schedule_badge(self, config: Any = None) -> None:
        if not hasattr(self, "schedule_badge"):
            return
        cfg = config or self._scheduler_service.config
        self.schedule_badge.setText(f"Next scheduled run: {self._scheduler_service.get_status_text()} · Local time" if cfg.enabled else "Schedule Off")
        self.schedule_badge.setStyleSheet("font-size: 12px; color: #64748B; background: transparent; border: none;")

    def _open_schedule_dialog(self) -> None:
        """Open the Power BI-style recurring schedule configuration dialog."""
        rule_count = self._get_enabled_sheet_rules_count()
        if rule_count == 0:
            self.validation_banner.show_message(
                "Cannot configure schedule: The Validation Sheet is currently empty. "
                "Please add at least one validation rule in the 'Validation Sheet' tab before scheduling automated runs.",
                level=NotificationLevel.WARNING,
                title="Validation Sheet Empty",
            )
            return

        from app.ui.dialogs.schedule_validation_dialog import ScheduleValidationDialog

        dlg = ScheduleValidationDialog(
            scheduler_service=self._scheduler_service,
            rule_count=rule_count,
            teams_service=self._teams_alert_service,
            account=self._get_current_account(),
            parent=self,
        )
        if dlg.exec():
            self._update_schedule_badge()

    def _on_schedule_triggered(self) -> None:
        """Handle background timer event to trigger recurring validation."""
        logger.info("Scheduler triggered automated validation run.")
        if self._get_enabled_sheet_rules_count() == 0:
            self.validation_banner.show_message(
                "Scheduled validation skipped: No enabled checks found in the Validation Sheet.",
                level=NotificationLevel.WARNING,
                title="Schedule Skipped",
            )
            return

        if self._validation_worker is not None and self._validation_worker.isRunning():
            logger.info("Validation already in progress, skipping scheduled trigger.")
            return

        self._run_validation()
        self.validation_banner.show_message(
            f"Automated scheduled validation run started at {datetime.now().strftime('%H:%M:%S')}.",
            level=NotificationLevel.INFO,
            title="Scheduled Run Started",
        )

    def _run_validation(self) -> None:
        if self._orchestrator_service is None:
            self.validation_banner.show_message(
                "Validation orchestrator service is not initialized.",
                level=NotificationLevel.ERROR,
                title="Service Unavailable",
            )
            return

        from app.services.sheet_service import SheetService

        has_tests = False
        db = getattr(self._orchestrator_service, "_db", None)
        if db is not None:
            try:
                sheet_svc = SheetService(
                    db=db,
                    registry_service=self._registry_service,
                    rule_service=self._rule_service,
                )
                rows = sheet_svc.load_sheet_rows()
                has_tests = any(r.enabled and r.workspace_id and r.dataset_id for r in rows)
            except Exception as exc:
                logger.debug("Error checking sheet rows: %s", exc)
        elif self._rule_service is not None and self._registry_service is not None:
            regs = self._registry_service.list_registrations(active_only=True)
            for reg in regs:
                if self._rule_service.list_rules(reg.id, enabled_only=True):
                    has_tests = True
                    break
        else:
            has_tests = True

        if db is not None and not has_tests:
            self.validation_banner.show_message(
                "No enabled validation checks found in the Validation Sheet. "
                "Please open the 'Validation Sheet' tab to add and enable your validation checks.",
                level=NotificationLevel.WARNING,
                title="No Checks to Run",
            )
            return

        ws_id, ds_id, _ = self._get_active_workspace_and_dataset()
        reg_id = self._get_or_create_registration()

        from app.services.orchestrator_service import ValidationWorker

        self.run_validation_button.setEnabled(False)
        self.cancel_validation_button.show()
        self.cancel_validation_button.setEnabled(True)
        self.validation_progress_bar.show()
        self.validation_progress_bar.setValue(0)
        self.validation_progress_label.show()
        self.validation_progress_label.setText("Preparing validation checks across Validation Sheet...")
        self.validation_banner.hide()

        self._validation_worker = ValidationWorker(
            self._orchestrator_service,
            workspace_registration_id=reg_id,
            workspace_id=ws_id,
            dataset_id=ds_id,
            run_all_sheet_rules=True,
            parent=self,
        )
        self._validation_worker.progress.connect(self._on_validation_progress)
        self._validation_worker.run_finished.connect(self._on_validation_finished)
        self._validation_worker.error.connect(self._on_validation_error)
        self._validation_worker.start()

    def _cancel_validation(self) -> None:
        if self._validation_worker:
            self._validation_worker.cancel()
            self.cancel_validation_button.setEnabled(False)
            self.validation_progress_label.setText("Cancelling validation run...")

    def _on_validation_progress(self, current: int, total: int, rule_name: str) -> None:
        pct = int(((current - 1) / total) * 100) if total > 0 else 0
        self.validation_progress_bar.setValue(pct)
        self.validation_progress_label.setText(f"Evaluating {current} of {total}: {rule_name}...")

    def _on_validation_finished(self, summary: Any) -> None:
        self.run_validation_button.setEnabled(True)
        self.cancel_validation_button.hide()
        self.validation_progress_bar.setValue(100)
        self.validation_progress_bar.hide()
        self.validation_progress_label.hide()

        self._display_run_summary(summary)

        st = summary.overall_status
        if st == ValidationStatus.PASS:
            lvl = NotificationLevel.SUCCESS
            ttl = "Validation Passed"
        elif st == ValidationStatus.WARNING:
            lvl = NotificationLevel.WARNING
            ttl = "Validation Completed with Warnings"
        else:
            lvl = NotificationLevel.ERROR
            ttl = "Validation Violations Detected"

        msg = (
            f"Validation completed in {summary.duration_display}: "
            f"{summary.passed_count} passed, {summary.failed_count} failed, "
            f"{summary.warning_count} warning(s), {summary.error_count} error(s)."
        )
        self.validation_banner.clear_message()

        # Dispatch Microsoft Teams alert if configured
        if self._teams_alert_service and self._teams_alert_service.should_notify(summary):
            acct = self._get_current_account()
            logger.info("Dispatching validation alert card to Microsoft Teams.")
            self._teams_alert_service.send_alert_async(summary, account=acct)

    def _on_validation_error(self, err_msg: str) -> None:
        self.run_validation_button.setEnabled(True)
        self.cancel_validation_button.hide()
        self.validation_progress_bar.hide()
        self.validation_progress_label.hide()
        self.validation_banner.show_message(
            f"Validation execution aborted: {err_msg}",
            level=NotificationLevel.ERROR,
            title="Execution Failed",
        )

    def _display_run_summary(self, summary: Any) -> None:
        update_validation_status_pill(self.home_overall_pill, summary.overall_status)

        self._displayed_summary = summary
        self.export_results_button.setEnabled(True)
        run_ids = {result.validation_run_id for result in summary.results}
        identity = f"Run #{summary.id}" if len(run_ids) <= 1 else f"Combined results · {len(run_ids)} saved model runs"
        latest = max((r.validated_at_display for r in summary.results), default=summary.started_at_display)
        context = ""
        if self._registry_service is not None and len(run_ids) <= 1:
            registrations = self._registry_service.list_registrations(active_only=False)
            registration = next((r for r in registrations if r.id == summary.workspace_registration_id), None)
            if registration is not None:
                context = f" · {registration.workspace_name} / {registration.report_name}"
        self.home_overall_timing.setText(f"{identity}{context} · Validated {latest} · Duration {summary.duration_display}")
        concerns = []
        if summary.failed_count:
            concerns.append(f"{summary.failed_count} failed")
        if summary.warning_count:
            concerns.append(f"{summary.warning_count} warnings")
        if summary.error_count:
            concerns.append(f"{summary.error_count} execution errors")
        self.attention_summary.setText(" · ".join(concerns) if concerns else "All evaluated checks passed.")
        self.home_passed_count.setText(str(summary.passed_count))
        self.home_failed_count.setText(str(summary.failed_count))
        self.home_warning_count.setText(str(summary.warning_count))
        self.home_error_count.setText(str(summary.error_count))

        self._populate_results_table(summary.results)

    def _populate_results_table(self, results: list[Any]) -> None:
        self._current_results = list(results)
        self.results_table.set_results(results)
        self.results_table.setVisible(bool(results))
        self.empty_results_label.setVisible(not results)
        self._apply_results_filter()

    def _handle_table_clicked(self, row: int, col: int) -> None:
        if col == 9:  # Clicked on Details column
            self._handle_table_double_clicked(row, col)

    def _apply_results_filter(self) -> None:
        if not hasattr(self, "results_count_label"):
            return
        query = self.results_search_input.text().strip().lower()
        filter_mode = self.results_status_filter.currentIndex()
        visible_count = 0

        for row_idx in range(self.results_table.rowCount()):
            res = self.results_table.result_at(row_idx)
            if res is None:
                continue

            # Status filter
            st_val = res.status.value.upper()
            status_match = True
            if filter_mode == 1 and st_val != "FAIL":
                status_match = False
            elif filter_mode == 2 and st_val != "WARNING":
                status_match = False
            elif filter_mode == 3 and st_val != "ERROR":
                status_match = False
            elif filter_mode == 4 and st_val != "PASS":
                status_match = False

            # Query filter
            query_match = True
            if query:
                text_blob = f"{res.rule_name} {res.target_display} {res.validation_type} {res.result_summary} {res.actual_value} {res.deviation}".lower()
                query_match = query in text_blob

            matches = status_match and query_match
            self.results_table.setRowHidden(row_idx, not matches)
            visible_count += int(matches)
        total = self.results_table.rowCount()
        self.results_count_label.setText(f"Showing {visible_count} of {total} checks")
        if total:
            self.empty_results_label.setText("No matching results. Clear search or change the outcome filter.")
            self.empty_results_label.setVisible(visible_count == 0)

    def _handle_table_double_clicked(self, row: int, _col: int) -> None:
        result = self.results_table.result_at(row)
        if result is not None:
            self._open_result_details(result)

    def _open_result_details(self, result: Any) -> None:
        dialog = ResultDetailsDialog(result, parent=self)
        dialog.exec()

