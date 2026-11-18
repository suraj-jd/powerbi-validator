"""Modal dialog for creating or editing an individual validation rule (BRD 5.2)."""

from __future__ import annotations

import copy
import logging
from typing import TYPE_CHECKING, Any

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QDialog,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QRadioButton,
    QVBoxLayout,
    QWidget,
)

from app.integrations.powerbi.models import DatasetMetadata
from app.services.rule_service import (
    COMPATIBLE_CHECKS,
    TARGET_TYPE_COLUMN,
    TARGET_TYPE_MEASURE,
    TARGET_TYPE_MODEL,
    TARGET_TYPES,
    VALIDATION_TYPE_ANOMALY,
    VALIDATION_TYPE_DAX_MEASURE,
    VALIDATION_TYPE_DUPLICATE,
    VALIDATION_TYPE_LATEST_DATE,
    VALIDATION_TYPE_NULL,
    VALIDATION_TYPE_REFRESH,
    VALIDATION_TYPE_ROW_COUNT,
    VALIDATION_TYPES,
    RuleInput,
    RuleRecord,
    format_rule_conditions_summary,
    validate_rule_input,
)
from app.ui.dialogs.advanced_settings_dialog import AdvancedSettingsDialog
from app.ui.widgets.searchable_combo import SearchableComboBox

logger = logging.getLogger(__name__)


class RuleEditorDialog(QDialog):
    """Create or edit one validation rule row with dynamic target fields and advanced modal."""

    def __init__(
        self,
        *,
        workspace_registration_id: int,
        registration_display_name: str = "",
        existing_rule: RuleRecord | None = None,
        metadata: DatasetMetadata | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._workspace_registration_id = workspace_registration_id
        self._existing_rule = existing_rule
        self._metadata = metadata
        self._config: dict[str, Any] = copy.deepcopy(existing_rule.config if existing_rule else {})
        self._result_input: RuleInput | None = None

        is_edit = existing_rule is not None
        self.setWindowTitle("Edit Validation Rule" if is_edit else "Add Validation Rule")
        self.setModal(True)
        self.setMinimumWidth(620)
        self.setObjectName("ConfirmDialog")

        self._init_ui(registration_display_name, is_edit)
        self._populate_fields(existing_rule)

    def _init_ui(self, registration_display_name: str, is_edit: bool) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(14)

        # Title
        title = QLabel("Edit Validation Rule" if is_edit else "Add Validation Rule")
        title.setObjectName("DialogTitle")
        layout.addWidget(title)

        # Registration context banner
        ctx_text = f"Target Semantic Model: {registration_display_name}" if registration_display_name else "Configure row-based validation check."
        banner = QLabel(ctx_text)
        banner.setObjectName("InfoBanner")
        banner.setWordWrap(True)
        layout.addWidget(banner)

        # Main Configuration Card
        card = QFrame()
        card.setObjectName("DialogCard")
        card.setStyleSheet(
            "#DialogCard { background-color: #F8FAFC; border: 1px solid #E2E8F0; "
            "border-radius: 8px; padding: 16px; }"
        )
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(12, 10, 12, 10)
        card_layout.setSpacing(10)

        # Form layout
        form = QFormLayout()
        form.setSpacing(10)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        # 1. Rule Name
        self.rule_name_input = QLineEdit()
        self.rule_name_input.setObjectName("SearchInput")
        self.rule_name_input.setPlaceholderText("e.g. Customer ID Not Null or Revenue Baseline")
        form.addRow(self._make_label("Rule Name *:"), self.rule_name_input)

        # 2. Target Type Radios
        type_box = QHBoxLayout()
        type_box.setSpacing(16)
        self.type_group = QButtonGroup(self)

        self.radio_column = QRadioButton("Table Column")
        self.radio_measure = QRadioButton("DAX Measure")
        self.radio_model = QRadioButton("Model / Refresh")
        self.radio_column.setChecked(True)

        for i, rb in enumerate((self.radio_column, self.radio_measure, self.radio_model)):
            rb.setStyleSheet("color: #1E293B; font-size: 13px; font-weight: 500;")
            self.type_group.addButton(rb, i)
            type_box.addWidget(rb)
        type_box.addStretch(1)
        self.type_group.idToggled.connect(self._on_target_type_toggled)
        form.addRow(self._make_label("Target Type:"), type_box)

        # 3. Target Fields (Table, Column, Measure)
        self.table_label = self._make_label("Table Name *:")
        self.table_combo = SearchableComboBox()
        self.table_combo.currentTextChanged.connect(self._on_table_changed)
        form.addRow(self.table_label, self.table_combo)

        self.column_label = self._make_label("Column Name *:")
        self.column_combo = SearchableComboBox()
        form.addRow(self.column_label, self.column_combo)

        self.measure_label = self._make_label("Measure Name *:")
        self.measure_combo = SearchableComboBox()
        form.addRow(self.measure_label, self.measure_combo)

        self.model_notice = QLabel("Model and Refresh checks apply to the entire semantic model.")
        self.model_notice.setStyleSheet("color: #0284C7; font-size: 12px; font-style: italic; padding: 4px 0;")
        self.model_notice.setVisible(False)
        form.addRow("", self.model_notice)

        # 4. Validation Check Selector
        self.check_combo = QComboBox()
        self.check_combo.currentIndexChanged.connect(self._on_check_type_changed)
        form.addRow(self._make_label("Validation Check *:"), self.check_combo)

        # 5. Conditions Summary & Advanced Settings Button
        cond_row = QHBoxLayout()
        cond_row.setSpacing(10)

        self.advanced_button = QPushButton("⚙ Advanced Settings...")
        self.advanced_button.setObjectName("SecondaryButton")
        self.advanced_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.advanced_button.clicked.connect(self._open_advanced_settings)
        cond_row.addWidget(self.advanced_button)

        self.summary_badge = QLabel("default settings")
        self.summary_badge.setStyleSheet(
            "background-color: #F1F5F9; color: #334155; border: 1px solid #CBD5E1; "
            "border-radius: 6px; padding: 5px 10px; font-size: 11px; font-weight: 600;"
        )
        cond_row.addWidget(self.summary_badge, stretch=1)
        form.addRow(self._make_label("Conditions:"), cond_row)

        # 6. Enabled Checkbox
        self.enabled_checkbox = QCheckBox("Enabled (include in validation runs)")
        self.enabled_checkbox.setStyleSheet("color: #1E293B; font-size: 13px; font-weight: 500;")
        self.enabled_checkbox.setChecked(True)
        form.addRow("", self.enabled_checkbox)

        card_layout.addLayout(form)
        layout.addWidget(card)

        # Error label
        self.error_label = QLabel("")
        self.error_label.setStyleSheet(
            "background-color: #FEE2E2; color: #991B1B; border: 1px solid #FCA5A5; "
            "border-radius: 6px; padding: 8px 12px; font-size: 12px; font-weight: 500;"
        )
        self.error_label.setWordWrap(True)
        self.error_label.hide()
        layout.addWidget(self.error_label)

        # Bottom Buttons
        btn_row = QHBoxLayout()
        btn_row.setSpacing(10)
        btn_row.addStretch(1)

        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.setObjectName("SecondaryButton")
        self.cancel_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.cancel_button.clicked.connect(self.reject)
        btn_row.addWidget(self.cancel_button)

        self.save_button = QPushButton("Save Rule")
        self.save_button.setObjectName("PrimaryButton")
        self.save_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.save_button.setDefault(True)
        self.save_button.clicked.connect(self._validate_and_accept)
        btn_row.addWidget(self.save_button)

        layout.addLayout(btn_row)

        # Populate tables and measures from metadata if available
        self._populate_metadata_items()

    def _make_label(self, text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setStyleSheet("color: #334155; font-weight: 600; font-size: 12px;")
        return lbl

    def _populate_metadata_items(self) -> None:
        tbl_names = self._metadata.table_names if self._metadata else []
        meas_names = self._metadata.measure_names if self._metadata else []

        self.table_combo.set_items(tbl_names, placeholder="-- Select or type Table name --")
        self.measure_combo.set_items(meas_names, placeholder="-- Select or type Measure name --")

    def _populate_fields(self, existing: RuleRecord | None) -> None:
        if existing is None:
            self._update_field_visibilities()
            self._update_compatible_checks()
            self._update_summary_badge()
            return

        self.rule_name_input.setText(existing.rule_name)
        self.enabled_checkbox.setChecked(existing.enabled)

        # Select target type
        if existing.target_type == TARGET_TYPE_MEASURE:
            self.radio_measure.setChecked(True)
        elif existing.target_type == TARGET_TYPE_MODEL:
            self.radio_model.setChecked(True)
        else:
            self.radio_column.setChecked(True)

        self._update_field_visibilities()
        self._update_compatible_checks()

        if existing.table_name:
            self.table_combo.set_manual_text(existing.table_name)
            self._on_table_changed(existing.table_name)
        if existing.column_name:
            self.column_combo.set_manual_text(existing.column_name)
        if existing.measure_name:
            self.measure_combo.set_manual_text(existing.measure_name)

        # Select check combo
        idx = self.check_combo.findData(existing.validation_type)
        if idx >= 0:
            self.check_combo.setCurrentIndex(idx)

        self._update_summary_badge()

    def _on_target_type_toggled(self, *_args: object) -> None:
        self._update_field_visibilities()
        self._update_compatible_checks()
        self._update_summary_badge()

    def _update_field_visibilities(self) -> None:
        is_col = self.radio_column.isChecked()
        is_meas = self.radio_measure.isChecked()
        is_model = self.radio_model.isChecked()

        self.table_label.setText("Table Name *:" if is_col else "Home Table (opt):")
        self.table_label.setVisible(is_col or is_meas)
        self.table_combo.setVisible(is_col or is_meas)

        self.column_label.setVisible(is_col)
        self.column_combo.setVisible(is_col)

        self.measure_label.setVisible(is_meas)
        self.measure_combo.setVisible(is_meas)

        self.model_notice.setVisible(is_model)

    def _update_compatible_checks(self) -> None:
        target_type = self.current_target_type
        allowed = COMPATIBLE_CHECKS.get(target_type, [])

        self.check_combo.blockSignals(True)
        self.check_combo.clear()
        for check_key in allowed:
            self.check_combo.addItem(VALIDATION_TYPES.get(check_key, check_key), check_key)
        self.check_combo.blockSignals(False)

    def _on_table_changed(self, table_name: str) -> None:
        cols: list[str] = []
        if self._metadata is not None and table_name:
            tbl = self._metadata.get_table(table_name)
            if tbl is not None:
                cols = tbl.column_names
        self.column_combo.set_items(cols, placeholder="-- Select or type Column name --")

    def _on_check_type_changed(self, *_args: object) -> None:
        self._update_summary_badge()

    def _update_summary_badge(self) -> None:
        vtype = self.current_validation_type
        summary = format_rule_conditions_summary(vtype, self._config)
        self.summary_badge.setText(summary)

    def _open_advanced_settings(self) -> None:
        vtype = self.current_validation_type
        dlg = AdvancedSettingsDialog(
            rule_name=self.rule_name_input.text().strip() or "New Rule",
            validation_type=vtype,
            current_config=self._config,
            parent=self,
        )
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self._config = dlg.config
            self._update_summary_badge()

    @property
    def current_target_type(self) -> str:
        if self.radio_measure.isChecked():
            return TARGET_TYPE_MEASURE
        if self.radio_model.isChecked():
            return TARGET_TYPE_MODEL
        return TARGET_TYPE_COLUMN

    @property
    def current_validation_type(self) -> str:
        return str(self.check_combo.currentData() or "")

    @property
    def rule_input(self) -> RuleInput | None:
        return self._result_input

    def _validate_and_accept(self) -> None:
        rule_name = self.rule_name_input.text().strip()
        target_type = self.current_target_type
        val_type = self.current_validation_type

        tbl = self.table_combo.current_text()
        col = self.column_combo.current_text()
        meas = self.measure_combo.current_text()

        payload = RuleInput(
            workspace_registration_id=self._workspace_registration_id,
            rule_name=rule_name,
            target_type=target_type,
            validation_type=val_type,
            enabled=self.enabled_checkbox.isChecked(),
            table_name=tbl if target_type in (TARGET_TYPE_COLUMN, TARGET_TYPE_MEASURE) else None,
            column_name=col if target_type == TARGET_TYPE_COLUMN else None,
            measure_name=meas if target_type == TARGET_TYPE_MEASURE else None,
            config=self._config,
        )

        errors = validate_rule_input(payload)
        if errors:
            self.error_label.setText("\n".join(f"• {e}" for e in errors))
            self.error_label.show()
            return

        self.error_label.hide()
        self._result_input = payload
        self.accept()
