"""Simplified, non-technical popup dialog for configuring validation rules in the sheet UI.

Allows non-technical users to set thresholds, tolerances, and SLAs for any
validation test row via the ⚙️ gear icon button.
"""

from __future__ import annotations

import copy
import logging
from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDoubleSpinBox,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSpinBox,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from app.services.rule_service import (
    VALIDATION_TYPE_ANOMALY,
    VALIDATION_TYPE_DAX_MEASURE,
    VALIDATION_TYPE_DUPLICATE,
    VALIDATION_TYPE_LATEST_DATE,
    VALIDATION_TYPE_NULL,
    VALIDATION_TYPE_REFRESH,
    VALIDATION_TYPE_ROW_COUNT,
    VALIDATION_TYPES,
)
from app.services.sheet_service import FRIENDLY_TEST_NAMES
from app.ui.widgets.animated_combo import AnimatedComboBox

logger = logging.getLogger(__name__)


class SheetRuleConfigDialog(QDialog):
    """Clean, friendly popup dialog triggered by the ⚙️ gear icon on a sheet row."""

    def __init__(
        self,
        *,
        validation_type: str,
        target_display: str = "",
        current_config: dict[str, Any] | None = None,
        rule_name: str = "",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setModal(True)
        self.setMinimumWidth(540)
        self.setObjectName("ConfirmDialog")

        self._validation_type = validation_type
        self._target_display = target_display
        self._config: dict[str, Any] = copy.deepcopy(current_config or {})
        self._initial_rule_name = rule_name
        self._result_config: dict[str, Any] | None = None
        self._result_rule_name: str = rule_name

        test_title = FRIENDLY_TEST_NAMES.get(validation_type, "Validation Check")
        self.setWindowTitle(f"Configure: {test_title}")

        self._init_ui()

    @property
    def config(self) -> dict[str, Any]:
        return self._result_config if self._result_config is not None else self._config

    @property
    def rule_name(self) -> str:
        return self._result_rule_name

    def _init_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(14)

        # Header Title
        test_title = FRIENDLY_TEST_NAMES.get(self._validation_type, "Validation Check")
        header_row = QHBoxLayout()
        header_row.setSpacing(8)

        icon_lbl = QLabel("⚙️")
        icon_lbl.setStyleSheet("font-size: 20px;")
        header_row.addWidget(icon_lbl)

        title_lbl = QLabel(f"{test_title} Settings")
        title_lbl.setObjectName("DialogTitle")
        header_row.addWidget(title_lbl, stretch=1)
        layout.addLayout(header_row)

        target_desc = self._target_display if self._target_display else "Selected Target"
        sub_banner = QLabel(f"Target: <b>{target_desc}</b> — Configure what this test should verify.")
        sub_banner.setObjectName("InfoBanner")
        sub_banner.setStyleSheet(
            "background-color: #EFF6FF; border: 1px solid #BFDBFE; color: #1E3A8A; "
            "border-radius: 6px; padding: 8px 12px; font-size: 12px;"
        )
        sub_banner.setWordWrap(True)
        layout.addWidget(sub_banner)

        # Main configuration card
        card = QFrame()
        card.setObjectName("DialogCard")
        card.setStyleSheet(
            "#DialogCard { background-color: #F8FAFC; border: 1px solid #E2E8F0; "
            "border-radius: 8px; padding: 16px; }"
        )
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(14, 12, 14, 12)
        card_layout.setSpacing(12)

        # Build controls based on test type
        self._build_type_controls(card_layout)

        # Optional Custom Rule Name row
        name_form = QFormLayout()
        name_form.setSpacing(8)
        self.rule_name_input = QLineEdit()
        self.rule_name_input.setObjectName("SearchInput")
        self.rule_name_input.setText(self._initial_rule_name)
        self.rule_name_input.setPlaceholderText("Leave blank to use auto-generated name")
        name_form.addRow("Rule Label (Optional):", self.rule_name_input)
        card_layout.addLayout(name_form)

        layout.addWidget(card)

        # Bottom Action Buttons
        btn_row = QHBoxLayout()
        btn_row.setSpacing(10)
        btn_row.addStretch(1)

        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.setObjectName("SecondaryButton")
        self.cancel_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.cancel_button.clicked.connect(self.reject)
        btn_row.addWidget(self.cancel_button)

        self.apply_button = QPushButton("✔  Apply Settings")
        self.apply_button.setObjectName("PrimaryButton")
        self.apply_button.setStyleSheet(
            "background-color: #1668DC; color: #FFFFFF; font-weight: 600; padding: 8px 18px; border-radius: 6px;"
        )
        self.apply_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.apply_button.setDefault(True)
        self.apply_button.clicked.connect(self._apply_and_close)
        btn_row.addWidget(self.apply_button)

        layout.addLayout(btn_row)

    def _build_type_controls(self, layout: QVBoxLayout) -> None:
        vtype = self._validation_type
        form = QFormLayout()
        form.setSpacing(10)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        if vtype == VALIDATION_TYPE_NULL:
            self.null_max_count = QSpinBox()
            self.null_max_count.setRange(0, 10_000_000)
            self.null_max_count.setValue(int(self._config.get("allowed_blank_count", 0)))
            form.addRow("Allowed Blank Rows:", self.null_max_count)

            self.null_max_pct = QDoubleSpinBox()
            self.null_max_pct.setRange(0.0, 100.0)
            self.null_max_pct.setDecimals(2)
            self.null_max_pct.setSuffix(" %")
            pct_val = self._config.get("allowed_blank_percentage")
            self.null_max_pct.setValue(float(pct_val) if pct_val is not None else 0.0)
            form.addRow("Allowed Blank %:", self.null_max_pct)

            self.null_chk_empty = QCheckBox('Count empty text ("" and spaces) as blanks')
            self.null_chk_empty.setChecked(self._config.get("include_empty_string", True))
            form.addRow("", self.null_chk_empty)

        elif vtype == VALIDATION_TYPE_DUPLICATE:
            self.dup_max_count = QSpinBox()
            self.dup_max_count.setRange(0, 10_000_000)
            self.dup_max_count.setValue(int(self._config.get("allowed_duplicate_count", 0)))
            form.addRow("Allowed Duplicates:", self.dup_max_count)

            self.dup_case_sensitive = QCheckBox("Case-sensitive text comparison")
            self.dup_case_sensitive.setChecked(self._config.get("case_sensitive", False))
            form.addRow("", self.dup_case_sensitive)

        elif vtype == VALIDATION_TYPE_LATEST_DATE:
            self.date_max_age = QSpinBox()
            self.date_max_age.setRange(1, 8760)
            self.date_max_age.setValue(int(self._config.get("max_age_hours", 24)))
            self.date_max_age.setSuffix(" hours")
            form.addRow("Freshness SLA (Max Age):", self.date_max_age)

            self.date_disallow_future = QCheckBox("Fail if future dates are present")
            self.date_disallow_future.setChecked(not self._config.get("allow_future_dates", False))
            form.addRow("", self.date_disallow_future)

        elif vtype == VALIDATION_TYPE_ROW_COUNT:
            self.row_method = AnimatedComboBox()
            self.row_method.addItems([
                "Minimum row count threshold",
                "Fixed expected count",
                "Range [Min - Max]",
                "Compare with previous run",
            ])
            cur_meth = self._config.get("method", "min_threshold")
            if cur_meth == "fixed":
                self.row_method.setCurrentIndex(1)
            elif cur_meth == "min_max":
                self.row_method.setCurrentIndex(2)
            elif cur_meth == "previous_run":
                self.row_method.setCurrentIndex(3)
            else:
                self.row_method.setCurrentIndex(0)
            form.addRow("Evaluation Method:", self.row_method)

            self.row_baseline = QSpinBox()
            self.row_baseline.setRange(0, 1_000_000_000)
            self.row_baseline.setValue(int(self._config.get("min_rows", self._config.get("expected_rows", 1))))
            form.addRow("Threshold / Expected Rows:", self.row_baseline)

            self.row_dev_pct = QDoubleSpinBox()
            self.row_dev_pct.setRange(0.0, 100.0)
            self.row_dev_pct.setDecimals(1)
            self.row_dev_pct.setSuffix(" %")
            self.row_dev_pct.setValue(float(self._config.get("allowed_deviation_pct", 5.0)))
            form.addRow("Allowed Deviation %:", self.row_dev_pct)

        elif vtype == VALIDATION_TYPE_REFRESH:
            self.ref_status = AnimatedComboBox()
            self.ref_status.addItems(["Completed", "In Progress", "Any"])
            cur_st = self._config.get("expected_status", "Completed")
            idx = self.ref_status.findText(cur_st)
            if idx >= 0:
                self.ref_status.setCurrentIndex(idx)
            form.addRow("Expected Refresh Status:", self.ref_status)

            self.ref_max_age = QSpinBox()
            self.ref_max_age.setRange(1, 720)
            self.ref_max_age.setValue(int(self._config.get("max_age_hours", 24)))
            self.ref_max_age.setSuffix(" hours")
            form.addRow("Max Age Since Refresh:", self.ref_max_age)

            self.ref_definition = AnimatedComboBox()
            self.ref_definition.addItem("Latest refresh attempt must succeed", "latest_attempt")
            self.ref_definition.addItem("At least one successful refresh within window", "latest_success")
            cur_def = self._config.get("definition", "latest_attempt")
            idx = 1 if cur_def == "latest_success" else 0
            self.ref_definition.setCurrentIndex(idx)
            form.addRow("SLA Rule Definition:", self.ref_definition)

        elif vtype == VALIDATION_TYPE_DAX_MEASURE:
            self.dax_expected = QDoubleSpinBox()
            self.dax_expected.setRange(-1_000_000_000.0, 1_000_000_000.0)
            self.dax_expected.setDecimals(2)
            self.dax_expected.setValue(float(self._config.get("expected_value", 0.0)))
            form.addRow("Expected Measure Value:", self.dax_expected)

            self.dax_dev_pct = QDoubleSpinBox()
            self.dax_dev_pct.setRange(0.0, 100.0)
            self.dax_dev_pct.setDecimals(2)
            self.dax_dev_pct.setSuffix(" %")
            self.dax_dev_pct.setValue(float(self._config.get("allowed_deviation_pct", 0.0)))
            form.addRow("Allowed Deviation %:", self.dax_dev_pct)

        elif vtype == VALIDATION_TYPE_ANOMALY:
            self.anom_lookback = AnimatedComboBox()
            self.anom_lookback.addItem("7 Days Lookback", 7)
            self.anom_lookback.addItem("15 Days Lookback", 15)
            self.anom_lookback.addItem("30 Days Lookback (Recommended)", 30)
            self.anom_lookback.addItem("60 Days Lookback", 60)
            self.anom_lookback.addItem("90 Days Lookback", 90)
            cur_lb = self._config.get("lookback_days", 30)
            lb_idx = next((i for i in range(self.anom_lookback.count()) if self.anom_lookback.itemData(i) == cur_lb), 2)
            self.anom_lookback.setCurrentIndex(lb_idx)
            form.addRow("Historical Baseline:", self.anom_lookback)

            self.anom_sensitivity = AnimatedComboBox()
            self.anom_sensitivity.addItem("Standard (Z-Score ±2.5)", "z_score")
            self.anom_sensitivity.addItem("High Sensitivity (Z-Score ±2.0)", "z_score_high")
            self.anom_sensitivity.addItem("Tolerant (Z-Score ±3.0)", "z_score_tolerant")
            self.anom_sensitivity.addItem("Interquartile Range (IQR)", "iqr")
            self.anom_sensitivity.addItem("Percentage Threshold", "percentage")
            cur_m = self._config.get("comparison_method", "z_score")
            sm_idx = next((i for i in range(self.anom_sensitivity.count()) if self.anom_sensitivity.itemData(i) == cur_m), 0)
            self.anom_sensitivity.setCurrentIndex(sm_idx)
            form.addRow("Detection Sensitivity:", self.anom_sensitivity)

            self.anom_dev_pct = QDoubleSpinBox()
            self.anom_dev_pct.setRange(0.1, 500.0)
            self.anom_dev_pct.setDecimals(1)
            self.anom_dev_pct.setSuffix(" %")
            self.anom_dev_pct.setValue(float(self._config.get("allowed_deviation_pct", 10.0)))
            form.addRow("Allowed Deviation %:", self.anom_dev_pct)

        layout.addLayout(form)

    def _apply_and_close(self) -> None:
        cfg = copy.deepcopy(self._config)
        vtype = self._validation_type

        if vtype == VALIDATION_TYPE_NULL:
            cfg["allowed_blank_count"] = self.null_max_count.value()
            if self.null_max_pct.value() > 0:
                cfg["allowed_blank_percentage"] = self.null_max_pct.value()
            else:
                cfg.pop("allowed_blank_percentage", None)
            cfg["include_empty_string"] = self.null_chk_empty.isChecked()

        elif vtype == VALIDATION_TYPE_DUPLICATE:
            cfg["allowed_duplicate_count"] = self.dup_max_count.value()
            cfg["case_sensitive"] = self.dup_case_sensitive.isChecked()

        elif vtype == VALIDATION_TYPE_LATEST_DATE:
            cfg["max_age_hours"] = self.date_max_age.value()
            cfg["allow_future_dates"] = not self.date_disallow_future.isChecked()

        elif vtype == VALIDATION_TYPE_ROW_COUNT:
            method_idx = self.row_method.currentIndex()
            methods = ["min_threshold", "fixed", "min_max", "previous_run"]
            chosen = methods[method_idx] if method_idx < len(methods) else "min_threshold"
            cfg["method"] = chosen
            if chosen == "min_threshold":
                cfg["min_rows"] = self.row_baseline.value()
            elif chosen == "fixed":
                cfg["expected_rows"] = self.row_baseline.value()
                cfg["allowed_deviation_pct"] = self.row_dev_pct.value()
            elif chosen == "min_max":
                cfg["min_rows"] = self.row_baseline.value()
                cfg["max_rows"] = int(self.row_baseline.value() * 1.5)
            elif chosen == "previous_run":
                cfg["allowed_deviation_pct"] = self.row_dev_pct.value()

        elif vtype == VALIDATION_TYPE_REFRESH:
            cfg["expected_status"] = self.ref_status.currentText()
            cfg["max_age_hours"] = self.ref_max_age.value()
            cfg["definition"] = self.ref_definition.currentData()

        elif vtype == VALIDATION_TYPE_DAX_MEASURE:
            cfg["expected_value"] = self.dax_expected.value()
            cfg["allowed_deviation_pct"] = self.dax_dev_pct.value()

        elif vtype == VALIDATION_TYPE_ANOMALY:
            cfg["lookback_days"] = self.anom_lookback.currentData()
            cfg["comparison_method"] = self.anom_sensitivity.currentData()
            cfg["allowed_deviation_pct"] = self.anom_dev_pct.value()

        self._result_config = cfg
        self._result_rule_name = self.rule_name_input.text().strip()
        self.accept()
