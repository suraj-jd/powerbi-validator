"""Home / Dashboard page with authentication banner, access verifier, validation runner, and refresh monitoring (Stage 13)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QFormLayout,
    QFrame,
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

from app.core.status import NotificationLevel, RefreshStatus, ValidationStatus
from app.integrations.file_import import RegistrationInput
from app.integrations.powerbi.models import (
    AccessVerificationResult,
    PowerBIDataset,
    PowerBIReport,
    PowerBIWorkspace,
)
from app.ui.dialogs.refresh_details_dialog import RefreshDetailsDialog, make_status_pill
from app.ui.dialogs.result_details_dialog import (
    ResultDetailsDialog,
    make_status_table_item,
    make_validation_status_pill,
)
from app.ui.widgets.animated_combo import AnimatedComboBox
from app.ui.widgets.auth_banner import AuthBanner
from app.ui.widgets.notification_banner import NotificationBanner
from app.ui.widgets.smooth_scroller import apply_smooth_scrolling

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
    ) -> None:
        super().__init__(parent)
        self._refresh_service = refresh_service
        self._registry_service = registry_service
        self._orchestrator_service = orchestrator_service
        self._rule_service = rule_service
        self._powerbi_service = powerbi_service
        self._validation_worker: ValidationWorker | None = None
        self._current_results: list[ValidationResultDTO] = []
        self._workspaces: list[PowerBIWorkspace] = []
        self._workspace_assets: dict[str, tuple[list[PowerBIDataset], list[PowerBIReport]]] = {}
        self._datasets: list[PowerBIDataset] = []
        self._reports: list[PowerBIReport] = []
        self._build_ui()
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

    def _on_model_selector_changed(self, index: int) -> None:
        if index < 0:
            return
        reg = self.model_selector_combo.itemData(index)
        if reg is not None and hasattr(reg, "workspace_id"):
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

        container = QWidget()
        container.setObjectName("PageContainer")
        layout = QVBoxLayout(container)
        layout.setContentsMargins(28, 20, 28, 24)
        layout.setSpacing(18)

        # Stage 3 Authentication Banner
        self.auth_banner = AuthBanner(container)
        layout.addWidget(self.auth_banner)

        # Header row
        header_row = QHBoxLayout()
        header_row.setSpacing(12)

        title_block = QVBoxLayout()
        title_block.setSpacing(4)

        title_label = QLabel("Power BI Report Health Monitor")
        title_label.setObjectName("PageTitle")
        title_block.addWidget(title_label)

        subtitle_label = QLabel("Validate. Detect. Ensure Data Integrity.")
        subtitle_label.setObjectName("PageSubtitle")
        title_block.addWidget(subtitle_label)

        header_row.addLayout(title_block, stretch=1)

        badge = QLabel("Stage 13 — Health Dashboard Active")
        badge.setObjectName("StageBadge")
        badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        header_row.addWidget(badge, alignment=Qt.AlignmentFlag.AlignTop)

        layout.addLayout(header_row)

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

        self.verification_banner = NotificationBanner(container)
        self.verification_banner.hide()

        self.verification_details_label = QLabel("", container)
        self.verification_details_label.hide()

        # Stage 13 Validation Results & Model Health Dashboard Card
        self.validation_card = self._create_validation_dashboard_card(container)
        layout.addWidget(self.validation_card)

        # Stage 8 Dataset Refresh Health & Monitoring Card
        self.refresh_card = self._create_refresh_monitoring_card(container)
        layout.addWidget(self.refresh_card)

        layout.addStretch(1)

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

        self.verification_banner.show_message(
            f"Loaded {len(workspaces)} accessible Power BI workspace(s).",
            level=NotificationLevel.INFO,
            title="Workspaces Loaded",
        )
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

        self.verification_banner.show_message(
            f"Workspace {workspace_id}: found {len(datasets)} dataset(s) and {len(reports)} report(s).",
            level=NotificationLevel.INFO,
            title="Assets Loaded",
        )
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
                f"{ws_label} — {result.effective_access_level}"
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
        section_title = QLabel("Power BI Dataset Refresh Monitoring")
        section_title.setObjectName("SectionTitle")
        card_header.addWidget(section_title, stretch=1)

        self.fetch_refresh_button = QPushButton("↻  Fetch Live Refresh History")
        self.fetch_refresh_button.setObjectName("SecondaryButton")
        self.fetch_refresh_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.fetch_refresh_button.clicked.connect(self._handle_fetch_refresh)
        card_header.addWidget(self.fetch_refresh_button)

        self.view_refresh_details_button = QPushButton("View Full History & Diagnostics...")
        self.view_refresh_details_button.setObjectName("PrimaryButton")
        self.view_refresh_details_button.setStyleSheet(
            "background-color: #1668DC; color: #FFFFFF; font-weight: 600; padding: 7px 14px; border-radius: 6px;"
        )
        self.view_refresh_details_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.view_refresh_details_button.clicked.connect(self._handle_view_refresh_details)
        card_header.addWidget(self.view_refresh_details_button)
        layout.addLayout(card_header)

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
            "background-color: #F8FAFC; border: 1px solid #E2E8F0; border-radius: 8px; padding: 8px;"
        )
        lay_att = QVBoxLayout(card_attempt)
        lay_att.setContentsMargins(10, 8, 10, 8)
        lay_att.setSpacing(4)
        lbl_att_title = QLabel("LATEST REFRESH ATTEMPT")
        lbl_att_title.setStyleSheet("color: #64748B; font-size: 10px; font-weight: 700; letter-spacing: 0.5px;")
        lay_att.addWidget(lbl_att_title)

        self.home_attempt_pill_container = QWidget()
        p_layout = QHBoxLayout(self.home_attempt_pill_container)
        p_layout.setContentsMargins(0, 0, 0, 0)
        self.home_attempt_pill = make_status_pill(RefreshStatus.UNKNOWN)
        p_layout.addWidget(self.home_attempt_pill)
        p_layout.addStretch(1)
        lay_att.addWidget(self.home_attempt_pill_container)

        self.home_attempt_start = QLabel("Start: —")
        self.home_attempt_start.setStyleSheet("color: #475569; font-size: 11px;")
        lay_att.addWidget(self.home_attempt_start)
        self.home_attempt_duration = QLabel("Duration: —")
        self.home_attempt_duration.setStyleSheet("color: #0F172A; font-size: 12px; font-weight: 600;")
        lay_att.addWidget(self.home_attempt_duration)
        kpi_row.addWidget(card_attempt)

        # 2. Latest Success
        card_success = QFrame()
        card_success.setObjectName("Card")
        card_success.setStyleSheet(
            "background-color: #F8FAFC; border: 1px solid #E2E8F0; border-radius: 8px; padding: 8px;"
        )
        lay_suc = QVBoxLayout(card_success)
        lay_suc.setContentsMargins(10, 8, 10, 8)
        lay_suc.setSpacing(4)
        lbl_suc_title = QLabel("LATEST SUCCESSFUL REFRESH")
        lbl_suc_title.setStyleSheet("color: #64748B; font-size: 10px; font-weight: 700; letter-spacing: 0.5px;")
        lay_suc.addWidget(lbl_suc_title)

        self.home_success_time = QLabel("—")
        self.home_success_time.setStyleSheet("color: #065F46; font-size: 13px; font-weight: 700;")
        lay_suc.addWidget(self.home_success_time)
        self.home_success_age = QLabel("Age: —")
        self.home_success_age.setStyleSheet("color: #475569; font-size: 11px;")
        lay_suc.addWidget(self.home_success_age)
        self.home_success_duration = QLabel("Duration: —")
        self.home_success_duration.setStyleSheet("color: #0F172A; font-size: 12px; font-weight: 600;")
        lay_suc.addWidget(self.home_success_duration)
        kpi_row.addWidget(card_success)

        # 3. Overall Reliability
        card_rel = QFrame()
        card_rel.setObjectName("Card")
        card_rel.setStyleSheet(
            "background-color: #F8FAFC; border: 1px solid #E2E8F0; border-radius: 8px; padding: 8px;"
        )
        lay_rel = QVBoxLayout(card_rel)
        lay_rel.setContentsMargins(10, 8, 10, 8)
        lay_rel.setSpacing(4)
        lbl_rel_title = QLabel("HISTORICAL RELIABILITY")
        lbl_rel_title.setStyleSheet("color: #64748B; font-size: 10px; font-weight: 700; letter-spacing: 0.5px;")
        lay_rel.addWidget(lbl_rel_title)

        self.home_reliability_rate = QLabel("No Data")
        self.home_reliability_rate.setStyleSheet("color: #1668DC; font-size: 14px; font-weight: 700;")
        lay_rel.addWidget(self.home_reliability_rate)
        self.home_reliability_detail = QLabel("Recorded Runs: 0")
        self.home_reliability_detail.setStyleSheet("color: #475569; font-size: 11px;")
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
            lbl_layout = self.home_attempt_pill_container.layout()
            if self.home_attempt_pill is not None:
                lbl_layout.removeWidget(self.home_attempt_pill)
                self.home_attempt_pill.deleteLater()
            self.home_attempt_pill = make_status_pill(latest.status)
            lbl_layout.addWidget(self.home_attempt_pill)
            lbl_layout.addStretch(1)

            self.home_attempt_start.setText(f"Start: {latest.start_time_display}")
            self.home_attempt_duration.setText(f"Duration: {latest.duration_display}")
        else:
            self._reset_attempt_pill()
            self.home_attempt_start.setText("Start: —")
            self.home_attempt_duration.setText("Duration: —")

        # Update Latest Success
        latest_success = summary.latest_successful
        if latest_success is not None:
            self.home_success_time.setText(latest_success.end_time_display)
            age_str = f"Age: {latest_success.age_hours}h ago" if latest_success.age_hours is not None else "Age: —"
            self.home_success_age.setText(age_str)
            self.home_success_duration.setText(f"Duration: {latest_success.duration_display}")
        else:
            self.home_success_time.setText("None Recorded")
            self.home_success_age.setText("Age: —")
            self.home_success_duration.setText("Duration: —")

        # Update Reliability
        self.home_reliability_rate.setText(summary.success_rate_display)
        self.home_reliability_detail.setText(
            f"Total: {summary.total_runs} (Passed: {summary.success_count}, Failed: {summary.failure_count})"
        )

    def _reset_attempt_pill(self) -> None:
        lbl_layout = self.home_attempt_pill_container.layout()
        if self.home_attempt_pill is not None:
            lbl_layout.removeWidget(self.home_attempt_pill)
            self.home_attempt_pill.deleteLater()
        self.home_attempt_pill = make_status_pill(RefreshStatus.UNKNOWN)
        lbl_layout.addWidget(self.home_attempt_pill)
        lbl_layout.addStretch(1)

    def _reset_refresh_cards(self) -> None:
        self._reset_attempt_pill()
        self.home_attempt_start.setText("Start: —")
        self.home_attempt_duration.setText("Duration: —")
        self.home_success_time.setText("—")
        self.home_success_age.setText("Age: —")
        self.home_success_duration.setText("Duration: —")
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
        layout.setContentsMargins(22, 20, 22, 20)
        layout.setSpacing(12)

        # Header with Run Validation button
        card_header = QHBoxLayout()
        card_header.setSpacing(10)
        section_title = QLabel("Validation Report & Health Dashboard")
        section_title.setObjectName("SectionTitle")
        card_header.addWidget(section_title)

        # Retain hidden controls for backward-compatible API and tests
        self.model_selector_combo = AnimatedComboBox(card)
        self.model_selector_combo.setObjectName("FilterCombo")
        self.model_selector_combo.currentIndexChanged.connect(self._on_model_selector_changed)
        self.model_selector_combo.hide()

        self.refresh_models_button = QPushButton("↻", card)
        self.refresh_models_button.setObjectName("SecondaryButton")
        self.refresh_models_button.clicked.connect(self._handle_refresh_models_clicked)
        self.refresh_models_button.hide()

        card_header.addStretch(1)

        self.cancel_validation_button = QPushButton("✕ Cancel")
        self.cancel_validation_button.setObjectName("SecondaryButton")
        self.cancel_validation_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.cancel_validation_button.clicked.connect(self._cancel_validation)
        self.cancel_validation_button.hide()
        card_header.addWidget(self.cancel_validation_button)

        self.run_validation_button = QPushButton("▶  Run Validation")
        self.run_validation_button.setObjectName("PrimaryButton")
        self.run_validation_button.setStyleSheet(
            "background-color: #1668DC; color: #FFFFFF; font-weight: 700; font-size: 13px; "
            "padding: 8px 18px; border-radius: 6px;"
        )
        self.run_validation_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.run_validation_button.clicked.connect(self._run_validation)
        card_header.addWidget(self.run_validation_button)
        layout.addLayout(card_header)

        desc = QLabel(
            "Execute all configured validation checks from the Validation Sheet across your Power BI datasets "
            "and generate a consolidated health report."
        )
        desc.setObjectName("PageSubtitle")
        desc.setWordWrap(True)
        layout.addWidget(desc)

        # Progress bar & running status label
        self.validation_progress_label = QLabel("Initializing validation...")
        self.validation_progress_label.setStyleSheet("font-size: 12px; font-weight: 600; color: #1668DC;")
        self.validation_progress_label.hide()
        layout.addWidget(self.validation_progress_label)

        self.validation_progress_bar = QProgressBar()
        self.validation_progress_bar.setRange(0, 100)
        self.validation_progress_bar.setValue(0)
        self.validation_progress_bar.setStyleSheet(
            "QProgressBar { border: 1px solid #CBD5E1; border-radius: 4px; text-align: center; height: 16px; font-size: 10px; font-weight: 600; background: #F1F5F9; }"
            "QProgressBar::chunk { background-color: #1668DC; border-radius: 3px; }"
        )
        self.validation_progress_bar.hide()
        layout.addWidget(self.validation_progress_bar)

        self.validation_banner = NotificationBanner(card)
        layout.addWidget(self.validation_banner)

        # 5 Summary KPI Cards Row
        kpi_row = QHBoxLayout()
        kpi_row.setSpacing(10)

        # 1. Overall Status
        card_ov = QFrame()
        card_ov.setStyleSheet("background-color: #F8FAFC; border: 1px solid #E2E8F0; border-radius: 8px; padding: 6px;")
        lay_ov = QVBoxLayout(card_ov)
        lay_ov.setContentsMargins(8, 8, 8, 8)
        lay_ov.setSpacing(4)
        lbl_ov_t = QLabel("OVERALL HEALTH")
        lbl_ov_t.setStyleSheet("color: #64748B; font-size: 10px; font-weight: 700; letter-spacing: 0.5px;")
        lay_ov.addWidget(lbl_ov_t)

        self.home_overall_pill_container = QWidget()
        ov_p_lay = QHBoxLayout(self.home_overall_pill_container)
        ov_p_lay.setContentsMargins(0, 0, 0, 0)
        self.home_overall_pill = make_validation_status_pill("NOT RUN")
        ov_p_lay.addWidget(self.home_overall_pill)
        ov_p_lay.addStretch(1)
        lay_ov.addWidget(self.home_overall_pill_container)

        self.home_overall_timing = QLabel("Last Run: —")
        self.home_overall_timing.setStyleSheet("color: #64748B; font-size: 11px;")
        lay_ov.addWidget(self.home_overall_timing)
        kpi_row.addWidget(card_ov, stretch=1)

        # 2. Passed
        card_pass = QFrame()
        card_pass.setStyleSheet("background-color: #F8FAFC; border: 1px solid #E2E8F0; border-radius: 8px; padding: 6px;")
        lay_p = QVBoxLayout(card_pass)
        lay_p.setContentsMargins(8, 8, 8, 8)
        lay_p.setSpacing(4)
        lbl_p_t = QLabel("PASSED CHECKS")
        lbl_p_t.setStyleSheet("color: #166534; font-size: 10px; font-weight: 700; letter-spacing: 0.5px;")
        lay_p.addWidget(lbl_p_t)
        self.home_passed_count = QLabel("0")
        self.home_passed_count.setStyleSheet("color: #166534; font-size: 20px; font-weight: 700;")
        lay_p.addWidget(self.home_passed_count)
        lbl_p_sub = QLabel("Within expected SLA")
        lbl_p_sub.setStyleSheet("color: #64748B; font-size: 11px;")
        lay_p.addWidget(lbl_p_sub)
        kpi_row.addWidget(card_pass, stretch=1)

        # 3. Failed
        card_fail = QFrame()
        card_fail.setStyleSheet("background-color: #F8FAFC; border: 1px solid #E2E8F0; border-radius: 8px; padding: 6px;")
        lay_f = QVBoxLayout(card_fail)
        lay_f.setContentsMargins(8, 8, 8, 8)
        lay_f.setSpacing(4)
        lbl_f_t = QLabel("FAILED CHECKS")
        lbl_f_t.setStyleSheet("color: #991B1B; font-size: 10px; font-weight: 700; letter-spacing: 0.5px;")
        lay_f.addWidget(lbl_f_t)
        self.home_failed_count = QLabel("0")
        self.home_failed_count.setStyleSheet("color: #991B1B; font-size: 20px; font-weight: 700;")
        lay_f.addWidget(self.home_failed_count)
        lbl_f_sub = QLabel("Violations detected")
        lbl_f_sub.setStyleSheet("color: #64748B; font-size: 11px;")
        lay_f.addWidget(lbl_f_sub)
        kpi_row.addWidget(card_fail, stretch=1)

        # 4. Warnings
        card_warn = QFrame()
        card_warn.setStyleSheet("background-color: #F8FAFC; border: 1px solid #E2E8F0; border-radius: 8px; padding: 6px;")
        lay_w = QVBoxLayout(card_warn)
        lay_w.setContentsMargins(8, 8, 8, 8)
        lay_w.setSpacing(4)
        lbl_w_t = QLabel("WARNINGS / ANOMALIES")
        lbl_w_t.setStyleSheet("color: #92400E; font-size: 10px; font-weight: 700; letter-spacing: 0.5px;")
        lay_w.addWidget(lbl_w_t)
        self.home_warning_count = QLabel("0")
        self.home_warning_count.setStyleSheet("color: #92400E; font-size: 20px; font-weight: 700;")
        lay_w.addWidget(self.home_warning_count)
        lbl_w_sub = QLabel("Deviations or empty")
        lbl_w_sub.setStyleSheet("color: #64748B; font-size: 11px;")
        lay_w.addWidget(lbl_w_sub)
        kpi_row.addWidget(card_warn, stretch=1)

        # 5. Errors
        card_err = QFrame()
        card_err.setStyleSheet("background-color: #F8FAFC; border: 1px solid #E2E8F0; border-radius: 8px; padding: 6px;")
        lay_e = QVBoxLayout(card_err)
        lay_e.setContentsMargins(8, 8, 8, 8)
        lay_e.setSpacing(4)
        lbl_e_t = QLabel("EXECUTION ERRORS")
        lbl_e_t.setStyleSheet("color: #6B21A8; font-size: 10px; font-weight: 700; letter-spacing: 0.5px;")
        lay_e.addWidget(lbl_e_t)
        self.home_error_count = QLabel("0")
        self.home_error_count.setStyleSheet("color: #6B21A8; font-size: 20px; font-weight: 700;")
        lay_e.addWidget(self.home_error_count)
        lbl_e_sub = QLabel("Query or engine errors")
        lbl_e_sub.setStyleSheet("color: #64748B; font-size: 11px;")
        lay_e.addWidget(lbl_e_sub)
        kpi_row.addWidget(card_err, stretch=1)

        layout.addLayout(kpi_row)

        # Search & Filter row
        filter_row = QHBoxLayout()
        filter_row.setSpacing(10)

        self.results_search_input = QLineEdit()
        self.results_search_input.setObjectName("SearchInput")
        self.results_search_input.setPlaceholderText("Filter checks by rule name, target, or outcome...")
        self.results_search_input.textChanged.connect(lambda _: self._apply_results_filter())
        filter_row.addWidget(self.results_search_input, stretch=1)

        self.results_status_filter = AnimatedComboBox()
        self.results_status_filter.setObjectName("FilterCombo")
        self.results_status_filter.addItems([
            "All Check Outcomes",
            "Failed Only",
            "Warnings Only",
            "Errors Only",
            "Passed Only",
        ])
        self.results_status_filter.currentIndexChanged.connect(lambda _: self._apply_results_filter())
        filter_row.addWidget(self.results_status_filter)
        layout.addLayout(filter_row)

        # Detailed Results Table
        self.results_table = QTableWidget()
        self.results_table.setObjectName("DataTable")
        self.results_table.setColumnCount(9)
        self.results_table.setHorizontalHeaderLabels([
            "Status",
            "Rule Name",
            "Target",
            "Check Type",
            "Actual Value",
            "Expected Value",
            "Deviation",
            "Duration",
            "Action",
        ])
        header = self.results_table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        header.setMinimumSectionSize(70)

        self.results_table.setColumnWidth(0, 110)  # Status (bold colorful text)
        self.results_table.setColumnWidth(1, 230)  # Rule Name
        self.results_table.setColumnWidth(2, 160)  # Target
        self.results_table.setColumnWidth(3, 130)  # Check Type
        self.results_table.setColumnWidth(4, 120)  # Actual Value
        self.results_table.setColumnWidth(5, 120)  # Expected Value
        self.results_table.setColumnWidth(6, 100)  # Deviation
        self.results_table.setColumnWidth(7, 90)   # Duration
        self.results_table.setColumnWidth(8, 90)   # Action

        self.results_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.results_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.results_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.results_table.setAlternatingRowColors(True)
        self.results_table.verticalHeader().setVisible(False)
        self.results_table.verticalHeader().setDefaultSectionSize(34)
        self.results_table.setMinimumHeight(240)
        apply_smooth_scrolling(self.results_table)
        self.results_table.cellDoubleClicked.connect(self._handle_table_double_clicked)
        self.results_table.hide()
        layout.addWidget(self.results_table)

        self.empty_results_label = QLabel(
            "No validation runs recorded yet. Click 'Run Validation' above to execute checks from your Validation Sheet."
        )
        self.empty_results_label.setStyleSheet(
            "color: #64748B; font-size: 13px; font-style: italic; padding: 24px 0; qproperty-alignment: AlignCenter;"
        )
        layout.addWidget(self.empty_results_label)

        return card

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
        lbl_layout = self.home_overall_pill_container.layout()
        if self.home_overall_pill is not None:
            lbl_layout.removeWidget(self.home_overall_pill)
            self.home_overall_pill.deleteLater()
        self.home_overall_pill = make_validation_status_pill("NOT RUN")
        lbl_layout.addWidget(self.home_overall_pill)
        lbl_layout.addStretch(1)

        self.home_overall_timing.setText("Last Run: —")
        self.home_passed_count.setText("0")
        self.home_failed_count.setText("0")
        self.home_warning_count.setText("0")
        self.home_error_count.setText("0")

        self.results_table.setRowCount(0)
        self.results_table.hide()
        self.empty_results_label.show()
        self._current_results = []

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
        self.validation_banner.show_message(msg, level=lvl, title=ttl)

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
        lbl_layout = self.home_overall_pill_container.layout()
        if self.home_overall_pill is not None:
            lbl_layout.removeWidget(self.home_overall_pill)
            self.home_overall_pill.deleteLater()
        self.home_overall_pill = make_validation_status_pill(summary.overall_status)
        lbl_layout.addWidget(self.home_overall_pill)
        lbl_layout.addStretch(1)

        self.home_overall_timing.setText(f"Run: {summary.duration_display} ({summary.started_at_display})")
        self.home_passed_count.setText(str(summary.passed_count))
        self.home_failed_count.setText(str(summary.failed_count))
        self.home_warning_count.setText(str(summary.warning_count))
        self.home_error_count.setText(str(summary.error_count))

        self._populate_results_table(summary.results)

    def _populate_results_table(self, results: list[Any]) -> None:
        self._current_results = list(results)
        if not results:
            self.results_table.setRowCount(0)
            self.results_table.hide()
            self.empty_results_label.show()
            return

        self.empty_results_label.hide()
        self.results_table.show()
        self.results_table.setRowCount(len(results))

        for row_idx, res in enumerate(results):
            # 0: Status (Native bold colorful text, no shrinked widget)
            item_status = make_status_table_item(res.status)
            item_status.setData(Qt.ItemDataRole.UserRole, res.id)
            self.results_table.setItem(row_idx, 0, item_status)

            # 1: Rule Name
            item_name = QTableWidgetItem(res.rule_name)
            item_name.setToolTip(res.result_summary)
            self.results_table.setItem(row_idx, 1, item_name)

            # 2: Target
            self.results_table.setItem(row_idx, 2, QTableWidgetItem(res.target_display))

            # 3: Check Type
            self.results_table.setItem(row_idx, 3, QTableWidgetItem(res.validation_type))

            # 4: Actual Value
            self.results_table.setItem(row_idx, 4, QTableWidgetItem(res.actual_value or "—"))

            # 5: Expected Value
            self.results_table.setItem(row_idx, 5, QTableWidgetItem(res.expected_value or "—"))

            # 6: Deviation
            self.results_table.setItem(row_idx, 6, QTableWidgetItem(res.deviation or "None"))

            # 7: Duration
            self.results_table.setItem(row_idx, 7, QTableWidgetItem(f"{res.duration_ms} ms"))

            # 8: Action button
            btn_details = QPushButton("Details...")
            btn_details.setObjectName("SecondaryButton")
            btn_details.setStyleSheet(
                "padding: 3px 8px; font-size: 11px; font-weight: 600; border-radius: 4px;"
            )
            btn_details.setCursor(Qt.CursorShape.PointingHandCursor)
            # Capture res in default argument of lambda
            btn_details.clicked.connect(lambda _, r=res: self._open_result_details(r))
            self.results_table.setCellWidget(row_idx, 8, btn_details)

        self._apply_results_filter()

    def _apply_results_filter(self) -> None:
        query = self.results_search_input.text().strip().lower()
        filter_mode = self.results_status_filter.currentIndex()

        for row_idx in range(self.results_table.rowCount()):
            if row_idx >= len(self._current_results):
                continue
            res = self._current_results[row_idx]

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

            self.results_table.setRowHidden(row_idx, not (status_match and query_match))

    def _handle_table_double_clicked(self, row: int, _col: int) -> None:
        if 0 <= row < len(self._current_results):
            self._open_result_details(self._current_results[row])

    def _open_result_details(self, result: Any) -> None:
        dialog = ResultDetailsDialog(result, parent=self)
        dialog.exec()

