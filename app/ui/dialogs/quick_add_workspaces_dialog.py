"""Dialog allowing users to batch-register multiple Power BI datasets without copying GUIDs."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.integrations.file_import import RegistrationInput
from app.integrations.powerbi.models import PowerBIDataset, PowerBIReport, PowerBIWorkspace
from app.ui.widgets.searchable_combo import SearchableComboBox

if TYPE_CHECKING:
    from app.services.powerbi_service import PowerBIService

logger = logging.getLogger(__name__)


class QuickAddWorkspacesDialog(QDialog):
    """Batch-register datasets from a connected Power BI workspace in one click."""

    def __init__(
        self,
        *,
        powerbi_service: PowerBIService,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._powerbi_service = powerbi_service
        self._workspaces: list[PowerBIWorkspace] = []
        self._datasets: list[PowerBIDataset] = []
        self._reports: list[PowerBIReport] = []
        self._selected_inputs: list[RegistrationInput] = []

        self.setWindowTitle("Quick Add Datasets from Power BI")
        self.setModal(True)
        self.resize(760, 520)
        self.setMinimumSize(640, 420)
        self.setObjectName("ConfirmDialog")

        self._init_ui()
        self._load_workspaces()

    def _init_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(14)

        # Header
        title = QLabel("Register Datasets from Connected Workspaces")
        title.setObjectName("DialogTitle")
        layout.addWidget(title)

        hint = QLabel(
            "Select a workspace to view its semantic models and reports. "
            "Check the models you want to register and click 'Register Selected'—no copying GUIDs required."
        )
        hint.setObjectName("InfoBanner")
        hint.setWordWrap(True)
        layout.addWidget(hint)

        # Workspace selector row
        ws_row = QHBoxLayout()
        ws_row.setSpacing(10)

        ws_label = QLabel("Power BI Workspace:")
        ws_label.setStyleSheet("color: #0F172A; font-weight: 600; font-size: 12px;")
        ws_row.addWidget(ws_label)

        self.workspace_combo = SearchableComboBox()
        self.workspace_combo.currentIndexChanged.connect(self._on_workspace_changed)
        ws_row.addWidget(self.workspace_combo, stretch=1)

        self.refresh_button = QPushButton("↻ Refresh Workspaces")
        self.refresh_button.setObjectName("SecondaryButton")
        self.refresh_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.refresh_button.clicked.connect(self._load_workspaces)
        ws_row.addWidget(self.refresh_button)

        layout.addLayout(ws_row)

        # Table frame
        self.table = QTableWidget()
        self.table.setObjectName("DataTable")
        self.table.setColumnCount(5)
        self.table.setHorizontalHeaderLabels([
            "Select",
            "Dataset / Model Name",
            "Dataset ID",
            "Matching Report",
            "Report ID",
        ])
        header = self.table.horizontalHeader()
        if header is not None:
            header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
            header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
            header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
            header.setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
            header.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(36)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setAlternatingRowColors(True)
        layout.addWidget(self.table, stretch=1)

        # Selection helpers
        sel_row = QHBoxLayout()
        sel_row.setSpacing(10)

        self.select_all_btn = QPushButton("Select All")
        self.select_all_btn.setObjectName("SecondaryButton")
        self.select_all_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.select_all_btn.clicked.connect(self._select_all)
        sel_row.addWidget(self.select_all_btn)

        self.deselect_all_btn = QPushButton("Deselect All")
        self.deselect_all_btn.setObjectName("SecondaryButton")
        self.deselect_all_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.deselect_all_btn.clicked.connect(self._deselect_all)
        sel_row.addWidget(self.deselect_all_btn)

        self.count_label = QLabel("0 models found")
        self.count_label.setStyleSheet("color: #475569; font-size: 12px; font-weight: 500;")
        sel_row.addWidget(self.count_label)
        sel_row.addStretch(1)

        layout.addLayout(sel_row)

        # Status / Error Label
        self.status_label = QLabel("")
        self.status_label.setStyleSheet(
            "background-color: #FEE2E2; color: #991B1B; border: 1px solid #FCA5A5; "
            "border-radius: 6px; padding: 6px 12px; font-size: 12px; font-weight: 500;"
        )
        self.status_label.setWordWrap(True)
        self.status_label.hide()
        layout.addWidget(self.status_label)

        # Bottom buttons
        btn_row = QHBoxLayout()
        btn_row.setSpacing(10)
        btn_row.addStretch(1)

        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.setObjectName("SecondaryButton")
        self.cancel_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.cancel_button.clicked.connect(self.reject)
        btn_row.addWidget(self.cancel_button)

        self.register_button = QPushButton("Register Selected (0)")
        self.register_button.setObjectName("PrimaryButton")
        self.register_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.register_button.clicked.connect(self._collect_and_accept)
        btn_row.addWidget(self.register_button)

        layout.addLayout(btn_row)

    def _load_workspaces(self) -> None:
        try:
            self._workspaces = self._powerbi_service.list_workspaces_sync()
        except Exception as exc:
            logger.warning("Failed listing workspaces: %s", exc)
            self._workspaces = self._powerbi_service.cached_workspaces

        self.workspace_combo.blockSignals(True)
        self.workspace_combo.clear()
        if not self._workspaces:
            self.workspace_combo.addItem("-- No accessible workspaces found --", "")
        else:
            for ws in self._workspaces:
                label = f"{ws.name} ({ws.id})"
                self.workspace_combo.addItem(label, ws.id)
        self.workspace_combo.blockSignals(False)

        if self._workspaces:
            self._on_workspace_changed(0)

    def _on_workspace_changed(self, index: int) -> None:
        ws_id = str(self.workspace_combo.itemData(index) or "")
        if not ws_id:
            self.table.setRowCount(0)
            self.count_label.setText("0 models found")
            return

        try:
            self._datasets, self._reports = self._powerbi_service.list_workspace_assets_sync(ws_id)
        except Exception as exc:
            logger.warning("Failed listing assets for workspace %s: %s", ws_id, exc)
            self._datasets = []
            self._reports = []

        self._populate_table()

    def _populate_table(self) -> None:
        self.table.setRowCount(len(self._datasets))
        for row, ds in enumerate(self._datasets):
            # Column 0: Checkbox
            chk = QCheckBox()
            chk.setChecked(True)
            chk.stateChanged.connect(self._update_selected_count)
            cell_widget = QWidget()
            ch_layout = QHBoxLayout(cell_widget)
            ch_layout.addWidget(chk)
            ch_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
            ch_layout.setContentsMargins(0, 0, 0, 0)
            self.table.setCellWidget(row, 0, cell_widget)

            # Column 1: Dataset Name
            item_name = QTableWidgetItem(ds.name)
            item_name.setFlags(item_name.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.table.setItem(row, 1, item_name)

            # Column 2: Dataset ID
            item_id = QTableWidgetItem(ds.id)
            item_id.setFlags(item_id.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.table.setItem(row, 2, item_id)

            # Column 3 & 4: Matching Report Name & ID
            matching_rpt = next(
                (r for r in self._reports if (r.dataset_id or "").lower() == ds.id.lower()),
                None,
            )
            rpt_name = matching_rpt.name if matching_rpt else ds.name
            rpt_id = matching_rpt.id if matching_rpt else ""

            item_rpt_name = QTableWidgetItem(rpt_name)
            self.table.setItem(row, 3, item_rpt_name)

            item_rpt_id = QTableWidgetItem(rpt_id)
            item_rpt_id.setFlags(item_rpt_id.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.table.setItem(row, 4, item_rpt_id)

        self.count_label.setText(f"{len(self._datasets)} semantic model(s) available")
        self._update_selected_count()

    def _select_all(self) -> None:
        for r in range(self.table.rowCount()):
            w = self.table.cellWidget(r, 0)
            if w:
                chk = w.findChild(QCheckBox)
                if chk:
                    chk.setChecked(True)
        self._update_selected_count()

    def _deselect_all(self) -> None:
        for r in range(self.table.rowCount()):
            w = self.table.cellWidget(r, 0)
            if w:
                chk = w.findChild(QCheckBox)
                if chk:
                    chk.setChecked(False)
        self._update_selected_count()

    def _update_selected_count(self) -> None:
        checked_count = 0
        for r in range(self.table.rowCount()):
            w = self.table.cellWidget(r, 0)
            if w:
                chk = w.findChild(QCheckBox)
                if chk and chk.isChecked():
                    checked_count += 1
        self.register_button.setText(f"Register Selected ({checked_count})")
        self.register_button.setEnabled(checked_count > 0)

    @property
    def selected_registrations(self) -> list[RegistrationInput]:
        return list(self._selected_inputs)

    def _collect_and_accept(self) -> None:
        ws_idx = self.workspace_combo.currentIndex()
        ws_id = str(self.workspace_combo.itemData(ws_idx) or "")
        ws = next((w for w in self._workspaces if w.id == ws_id), None)
        ws_name = ws.name if ws else ws_id

        collected: list[RegistrationInput] = []
        for r in range(self.table.rowCount()):
            w = self.table.cellWidget(r, 0)
            chk = w.findChild(QCheckBox) if w else None
            if chk and chk.isChecked():
                ds_name = self.table.item(r, 1).text().strip()
                ds_id = self.table.item(r, 2).text().strip()
                rpt_name = self.table.item(r, 3).text().strip() or ds_name
                rpt_id = self.table.item(r, 4).text().strip() or None

                collected.append(
                    RegistrationInput(
                        workspace_name=ws_name,
                        workspace_id=ws_id,
                        report_name=rpt_name,
                        report_id=rpt_id,
                        dataset_name=ds_name,
                        dataset_id=ds_id,
                        is_active=True,
                    )
                )

        if not collected:
            self.status_label.setText("Please select at least one dataset to register.")
            self.status_label.show()
            return

        self._selected_inputs = collected
        self.accept()
