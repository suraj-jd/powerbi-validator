"""Home / Dashboard page with authentication banner and Stage 4 Power BI access verifier."""

from __future__ import annotations

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

from app.core.status import NotificationLevel
from app.integrations.powerbi.models import (
    AccessVerificationResult,
    PowerBIDataset,
    PowerBIReport,
    PowerBIWorkspace,
)
from app.ui.widgets.auth_banner import AuthBanner
from app.ui.widgets.notification_banner import NotificationBanner


class HomePage(QWidget):
    """Dashboard page housing the authentication banner and Stage 4 connectivity check."""

    load_workspaces_requested = Signal()
    load_workspace_assets_requested = Signal(str)
    verify_access_requested = Signal(str, str, str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._workspaces: list[PowerBIWorkspace] = []
        self._datasets: list[PowerBIDataset] = []
        self._reports: list[PowerBIReport] = []
        self._build_ui()

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

        badge = QLabel("Stage 4 — Connectivity Ready")
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
