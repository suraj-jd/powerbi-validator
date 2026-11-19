"""Home / Dashboard page with authentication banner, access verifier, and refresh monitoring (Stage 8)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from app.core.status import NotificationLevel, RefreshStatus
from app.integrations.file_import import RegistrationInput
from app.integrations.powerbi.models import (
    AccessVerificationResult,
    PowerBIDataset,
    PowerBIReport,
    PowerBIWorkspace,
)
from app.ui.dialogs.refresh_details_dialog import RefreshDetailsDialog, make_status_pill
from app.ui.widgets.auth_banner import AuthBanner
from app.ui.widgets.notification_banner import NotificationBanner

if TYPE_CHECKING:
    from app.services.refresh_service import RefreshService
    from app.services.registry_service import RegistryService


class HomePage(QWidget):
    """Dashboard page housing authentication banner, connectivity verifier, and refresh monitoring."""

    load_workspaces_requested = Signal()
    load_workspace_assets_requested = Signal(str)
    verify_access_requested = Signal(str, str, str)

    def __init__(
        self,
        parent: QWidget | None = None,
        *,
        refresh_service: RefreshService | None = None,
        registry_service: RegistryService | None = None,
    ) -> None:
        super().__init__(parent)
        self._refresh_service = refresh_service
        self._registry_service = registry_service
        self._workspaces: list[PowerBIWorkspace] = []
        self._datasets: list[PowerBIDataset] = []
        self._reports: list[PowerBIReport] = []
        self._build_ui()
        self._connect_refresh_service()

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

        badge = QLabel("Stage 8 — Refresh Monitoring Active")
        badge.setObjectName("StageBadge")
        badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        header_row.addWidget(badge, alignment=Qt.AlignmentFlag.AlignTop)

        layout.addLayout(header_row)

        # Stage 4 Power BI Connectivity & Permission Verification Card
        verify_card = QFrame()
        verify_card.setObjectName("Card")
        verify_layout = QVBoxLayout(verify_card)
        verify_layout.setContentsMargins(22, 20, 22, 20)
        verify_layout.setSpacing(12)

        card_header = QHBoxLayout()
        section_title = QLabel("Power BI Connectivity & Access Verification")
        section_title.setObjectName("SectionTitle")
        card_header.addWidget(section_title, stretch=1)

        self.load_workspaces_button = QPushButton("Load My Workspaces")
        self.load_workspaces_button.setObjectName("SecondaryButton")
        self.load_workspaces_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.load_workspaces_button.clicked.connect(self.load_workspaces_requested.emit)
        card_header.addWidget(self.load_workspaces_button)
        verify_layout.addLayout(card_header)

        desc = QLabel(
            "Select an accessible workspace or paste Workspace, Dataset, and optional Report GUIDs "
            "to verify that your signed-in Microsoft account has the required Power BI access."
        )
        desc.setObjectName("PageSubtitle")
        desc.setWordWrap(True)
        verify_layout.addWidget(desc)

        form = QFormLayout()
        form.setSpacing(10)

        self.workspace_combo = QComboBox()
        self.workspace_combo.setObjectName("FilterCombo")
        self.workspace_combo.addItem("Select a loaded workspace (optional)", "")
        self.workspace_combo.currentIndexChanged.connect(self._on_workspace_selected)
        form.addRow("Accessible Workspaces:", self.workspace_combo)

        self.dataset_combo = QComboBox()
        self.dataset_combo.setObjectName("FilterCombo")
        self.dataset_combo.addItem("Select a loaded dataset (optional)", "")
        self.dataset_combo.currentIndexChanged.connect(self._on_dataset_selected)
        form.addRow("Workspace Datasets:", self.dataset_combo)

        self.workspace_id_input = QLineEdit()
        self.workspace_id_input.setObjectName("SearchInput")
        self.workspace_id_input.setPlaceholderText("Workspace GUID (required)")
        form.addRow("Workspace ID:", self.workspace_id_input)

        self.dataset_id_input = QLineEdit()
        self.dataset_id_input.setObjectName("SearchInput")
        self.dataset_id_input.setPlaceholderText("Semantic Model / Dataset GUID (required)")
        form.addRow("Dataset ID:", self.dataset_id_input)

        self.report_id_input = QLineEdit()
        self.report_id_input.setObjectName("SearchInput")
        self.report_id_input.setPlaceholderText("Report GUID (optional)")
        form.addRow("Report ID:", self.report_id_input)

        verify_layout.addLayout(form)

        action_row = QHBoxLayout()
        self.verify_access_button = QPushButton("Verify Access")
        self.verify_access_button.setObjectName("PrimaryButton")
        self.verify_access_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.verify_access_button.clicked.connect(self._emit_verify_access)
        action_row.addWidget(self.verify_access_button)
        action_row.addStretch(1)
        verify_layout.addLayout(action_row)

        self.verification_banner = NotificationBanner(verify_card)
        verify_layout.addWidget(self.verification_banner)

        self.verification_details_label = QLabel("")
        self.verification_details_label.setObjectName("InfoBanner")
        self.verification_details_label.setWordWrap(True)
        self.verification_details_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        self.verification_details_label.hide()
        verify_layout.addWidget(self.verification_details_label)

        layout.addWidget(verify_card)

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

    def set_workspace_assets(
        self,
        workspace_id: str,
        datasets: list[PowerBIDataset],
        reports: list[PowerBIReport],
    ) -> None:
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
        ds_name = self.dataset_combo.currentText().split(" (")[0] if self.dataset_combo.currentIndex() > 0 else (f"Dataset {ds_id[:8]}" if ds_id else "")
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
        ws_name = self.workspace_combo.currentText().split(" (")[0] if self.workspace_combo.currentIndex() > 0 else f"Workspace {ws_id[:8]}"
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
