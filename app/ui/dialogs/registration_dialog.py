"""Modal dialog for adding or editing a Power BI workspace, report, and dataset registration."""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import TYPE_CHECKING

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from app.integrations.file_import import RegistrationInput, validate_registration_fields
from app.integrations.powerbi.models import PowerBIDataset, PowerBIReport, PowerBIWorkspace
from app.services.registry_service import RegistrationRecord
from app.ui.widgets.searchable_combo import SearchableComboBox

if TYPE_CHECKING:
    from app.services.powerbi_service import PowerBIService

logger = logging.getLogger(__name__)


class RegistrationDialog(QDialog):
    """Add or edit one Workspace / Report / Semantic Model registration."""

    record_saved = Signal(object)  # RegistrationInput

    def __init__(
        self,
        *,
        existing: RegistrationRecord | None = None,
        powerbi_service: PowerBIService | None = None,
        available_workspaces: list[PowerBIWorkspace] | None = None,
        on_save_another: Callable[[RegistrationInput], bool] | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._existing = existing
        self._powerbi_service = powerbi_service
        self._workspaces: list[PowerBIWorkspace] = list(
            available_workspaces
            or (powerbi_service.cached_workspaces if powerbi_service else [])
        )
        self._on_save_another = on_save_another
        self._result_input: RegistrationInput | None = None
        self._current_datasets: list[PowerBIDataset] = []
        self._current_reports: list[PowerBIReport] = []

        is_edit = existing is not None
        self.setWindowTitle("Edit Workspace / Dataset" if is_edit else "Add Workspace / Dataset")
        self.setModal(True)
        self.setMinimumWidth(560)
        self.setObjectName("ConfirmDialog")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(14)

        title = QLabel(
            "Edit Workspace & Dataset Registration"
            if is_edit
            else "Register Workspace, Report & Semantic Model"
        )
        title.setObjectName("DialogTitle")
        layout.addWidget(title)

        hint = QLabel(
            "Pick from connected Power BI to auto-fill names and IDs without copying GUIDs, "
            "or type custom values manually below."
        )
        hint.setObjectName("InfoBanner")
        hint.setWordWrap(True)
        layout.addWidget(hint)

        # Auto-Fill from Power BI Box (only shown if not editing or when workspaces available)
        self._build_autofill_section(layout)

        form = QFormLayout()
        form.setSpacing(10)

        self.workspace_name_input = QLineEdit(existing.workspace_name if existing else "")
        self.workspace_name_input.setObjectName("SearchInput")
        self.workspace_name_input.setPlaceholderText("e.g. My Workspace (Personal)")
        form.addRow("Workspace Name *:", self.workspace_name_input)

        self.workspace_id_input = QLineEdit(existing.workspace_id if existing else "")
        self.workspace_id_input.setObjectName("SearchInput")
        self.workspace_id_input.setPlaceholderText("xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx or 'me'")
        form.addRow("Workspace ID *:", self.workspace_id_input)

        self.report_name_input = QLineEdit(existing.report_name if existing else "")
        self.report_name_input.setObjectName("SearchInput")
        self.report_name_input.setPlaceholderText("e.g. Sales Analysis Report")
        form.addRow("Report Name *:", self.report_name_input)

        self.report_id_input = QLineEdit(existing.report_id or "" if existing else "")
        self.report_id_input.setObjectName("SearchInput")
        self.report_id_input.setPlaceholderText("Recommended GUID (optional)")
        form.addRow("Report ID:", self.report_id_input)

        self.dataset_name_input = QLineEdit(existing.dataset_name or "" if existing else "")
        self.dataset_name_input.setObjectName("SearchInput")
        self.dataset_name_input.setPlaceholderText("Friendly semantic model name (optional)")
        form.addRow("Dataset / Model Name:", self.dataset_name_input)

        self.dataset_id_input = QLineEdit(existing.dataset_id if existing else "")
        self.dataset_id_input.setObjectName("SearchInput")
        self.dataset_id_input.setPlaceholderText("xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx")
        form.addRow("Dataset ID *:", self.dataset_id_input)

        self.active_checkbox = QCheckBox("Active (include in validation)")
        self.active_checkbox.setChecked(existing.is_active if existing else True)
        form.addRow("Status:", self.active_checkbox)

        layout.addLayout(form)

        # Feedback & Error Labels
        self.feedback_label = QLabel("")
        self.feedback_label.setStyleSheet("color: #34D399; font-size: 11px; font-weight: 600;")
        self.feedback_label.setWordWrap(True)
        self.feedback_label.hide()
        layout.addWidget(self.feedback_label)

        self.error_label = QLabel("")
        self.error_label.setStyleSheet("color: #F87171; font-size: 11px; font-weight: 500;")
        self.error_label.setWordWrap(True)
        self.error_label.hide()
        layout.addWidget(self.error_label)

        # Buttons
        buttons = QHBoxLayout()
        buttons.setSpacing(10)

        if not is_edit:
            self.save_and_add_another_button = QPushButton("Save & Add Another")
            self.save_and_add_another_button.setObjectName("SecondaryButton")
            self.save_and_add_another_button.setCursor(Qt.CursorShape.PointingHandCursor)
            self.save_and_add_another_button.clicked.connect(self._handle_save_and_add_another)
            buttons.addWidget(self.save_and_add_another_button)

        buttons.addStretch(1)

        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.setObjectName("SecondaryButton")
        self.cancel_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.cancel_button.clicked.connect(self.reject)
        buttons.addWidget(self.cancel_button)

        self.save_button = QPushButton("Save Registration")
        self.save_button.setObjectName("PrimaryButton")
        self.save_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.save_button.setDefault(True)
        self.save_button.clicked.connect(self._validate_and_accept)
        buttons.addWidget(self.save_button)

        layout.addLayout(buttons)

        # Populate workspaces dropdown if available
        self._populate_workspaces_combo()

    def _build_autofill_section(self, parent_layout: QVBoxLayout) -> None:
        box = QFrame()
        box.setObjectName("Card")
        box.setStyleSheet(
            "#Card { background-color: #0F172A; border: 1px solid #1E293B; "
            "border-radius: 8px; padding: 12px; }"
        )
        box_layout = QVBoxLayout(box)
        box_layout.setContentsMargins(10, 8, 10, 8)
        box_layout.setSpacing(8)

        head_row = QHBoxLayout()
        head_label = QLabel("✨ Auto-fill from Connected Power BI")
        head_label.setStyleSheet("color: #38BDF8; font-weight: 700; font-size: 12px;")
        head_row.addWidget(head_label)
        head_row.addStretch(1)
        box_layout.addLayout(head_row)

        form_sub = QFormLayout()
        form_sub.setSpacing(6)

        self.autofill_ws_combo = SearchableComboBox()
        self.autofill_ws_combo.currentIndexChanged.connect(self._on_autofill_workspace_changed)
        form_sub.addRow("Workspace:", self.autofill_ws_combo)

        self.autofill_ds_combo = SearchableComboBox()
        self.autofill_ds_combo.currentIndexChanged.connect(self._on_autofill_dataset_changed)
        form_sub.addRow("Semantic Model:", self.autofill_ds_combo)

        self.autofill_rpt_combo = SearchableComboBox()
        self.autofill_rpt_combo.currentIndexChanged.connect(self._on_autofill_report_changed)
        form_sub.addRow("Report (opt):", self.autofill_rpt_combo)

        box_layout.addLayout(form_sub)
        parent_layout.addWidget(box)

    def _populate_workspaces_combo(self) -> None:
        if not self._workspaces and self._powerbi_service is not None:
            try:
                self._workspaces = self._powerbi_service.list_workspaces_sync()
            except Exception as exc:
                logger.debug("Workspaces sync fetch skipped: %s", exc)

        self._workspace_by_id = {ws.id: ws for ws in self._workspaces}

        self.autofill_ws_combo.blockSignals(True)
        self.autofill_ws_combo.clear()
        if not self._workspaces:
            self.autofill_ws_combo.addItem("-- Load workspaces from Home page or type below --", "")
        else:
            self.autofill_ws_combo.addItem("-- Select Workspace to auto-fill --", "")
            for ws in self._workspaces:
                self.autofill_ws_combo.addItem(f"{ws.name} ({ws.id})", ws.id)
        self.autofill_ws_combo.blockSignals(False)

    def _on_autofill_workspace_changed(self, index: int) -> None:
        ws_id = str(self.autofill_ws_combo.itemData(index) or "")
        ws = getattr(self, "_workspace_by_id", {}).get(ws_id)
        if ws is None:
            return

        self.workspace_name_input.setText(ws.name)
        self.workspace_id_input.setText(ws.id)
        self.feedback_label.hide()

        # Fetch / load datasets and reports for this workspace
        datasets: list[PowerBIDataset] = []
        reports: list[PowerBIReport] = []
        if self._powerbi_service is not None:
            try:
                datasets, reports = self._powerbi_service.list_workspace_assets_sync(ws_id)
            except Exception as exc:
                logger.debug("Failed fetching assets for %s: %s", ws_id, exc)

        self._current_datasets = datasets
        self._current_reports = reports
        self._dataset_by_id = {ds.id: ds for ds in datasets}
        self._report_by_id = {rpt.id: rpt for rpt in reports}

        # Populate dataset dropdown
        self.autofill_ds_combo.blockSignals(True)
        self.autofill_ds_combo.clear()
        self.autofill_ds_combo.addItem(f"-- Select Semantic Model ({len(datasets)} found) --", "")
        for ds in datasets:
            self.autofill_ds_combo.addItem(f"{ds.name} ({ds.id})", ds.id)
        self.autofill_ds_combo.blockSignals(False)

        # Populate report dropdown
        self.autofill_rpt_combo.blockSignals(True)
        self.autofill_rpt_combo.clear()
        self.autofill_rpt_combo.addItem(f"-- Select Report ({len(reports)} found) --", "")
        for rpt in reports:
            self.autofill_rpt_combo.addItem(f"{rpt.name} ({rpt.id})", rpt.id)
        self.autofill_rpt_combo.blockSignals(False)

    def _on_autofill_dataset_changed(self, index: int) -> None:
        ds_id = str(self.autofill_ds_combo.itemData(index) or "")
        ds = getattr(self, "_dataset_by_id", {}).get(ds_id)
        if ds is None:
            return

        self.dataset_name_input.setText(ds.name)
        self.dataset_id_input.setText(ds.id)

        # If report name is empty, default to dataset name
        if not self.report_name_input.text().strip():
            self.report_name_input.setText(ds.name)

        # Find matching report
        matching_rpt = next(
            (r for r in self._current_reports if (r.dataset_id or "").lower() == ds_id.lower()),
            None,
        )
        if matching_rpt is not None:
            self.report_id_input.setText(matching_rpt.id)
            self.report_name_input.setText(matching_rpt.name)
            # Match in report combo
            r_idx = self.autofill_rpt_combo.findData(matching_rpt.id)
            if r_idx >= 0:
                self.autofill_rpt_combo.blockSignals(True)
                self.autofill_rpt_combo.setCurrentIndex(r_idx)
                self.autofill_rpt_combo.blockSignals(False)

    def _on_autofill_report_changed(self, index: int) -> None:
        rpt_id = str(self.autofill_rpt_combo.itemData(index) or "")
        rpt = getattr(self, "_report_by_id", {}).get(rpt_id)
        if rpt is None:
            return
        self.report_name_input.setText(rpt.name)
        self.report_id_input.setText(rpt.id)

    @property
    def registration_input(self) -> RegistrationInput | None:
        return self._result_input

    def _validate_current_form(self) -> tuple[RegistrationInput | None, list[str]]:
        return validate_registration_fields(
            workspace_name=self.workspace_name_input.text(),
            workspace_id=self.workspace_id_input.text(),
            report_name=self.report_name_input.text(),
            report_id=self.report_id_input.text(),
            dataset_name=self.dataset_name_input.text(),
            dataset_id=self.dataset_id_input.text(),
            is_active=self.active_checkbox.isChecked(),
        )

    def _handle_save_and_add_another(self) -> None:
        parsed, errors = self._validate_current_form()
        if errors or parsed is None:
            self.error_label.setText("\n".join(f"• {err}" for err in errors))
            self.error_label.show()
            self.feedback_label.hide()
            return

        self.error_label.hide()
        saved_name = parsed.dataset_name or parsed.report_name

        if self._on_save_another is not None:
            success = self._on_save_another(parsed)
            if not success:
                return

        self.record_saved.emit(parsed)

        # Clear dataset and report fields for next addition, keeping workspace intact
        self.dataset_name_input.clear()
        self.dataset_id_input.clear()
        self.report_name_input.clear()
        self.report_id_input.clear()
        self.autofill_ds_combo.setCurrentIndex(0)
        self.autofill_rpt_combo.setCurrentIndex(0)

        self.feedback_label.setText(
            f"✓ Saved '{saved_name}'! You can pick another dataset from the dropdown."
        )
        self.feedback_label.show()

    def _validate_and_accept(self) -> None:
        parsed, errors = self._validate_current_form()
        if errors or parsed is None:
            self.error_label.setText("\n".join(f"• {err}" for err in errors))
            self.error_label.show()
            self.feedback_label.hide()
            return

        self.error_label.hide()
        self._result_input = parsed
        self.accept()
