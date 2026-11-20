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
        sub_banner = QLabel(f"Target: <b>{target_desc}</b>: Configure what this test should verify.")
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
        self.rule_name_input.setToolTip("Custom descriptive label for this rule. Leave blank for auto-generated name.")
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
        self.cancel_button.setToolTip("Discard changes and close this dialog.")
        self.cancel_button.clicked.connect(self.reject)
        btn_row.addWidget(self.cancel_button)

        self.apply_button = QPushButton("✔  Apply Settings")
        self.apply_button.setObjectName("PrimaryButton")
        self.apply_button.setStyleSheet(
            "background-color: #1668DC; color: #FFFFFF; font-weight: 600; padding: 8px 18px; border-radius: 6px;"
        )
        self.apply_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.apply_button.setToolTip("Apply and save these settings for the validation check.")
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
            self.null_max_count.setToolTip("Maximum number of blank rows permitted before the test fails.")
            form.addRow("Allowed Blank Rows:", self.null_max_count)

            self.null_max_pct = QDoubleSpinBox()
            self.null_max_pct.setRange(0.0, 100.0)
            self.null_max_pct.setDecimals(2)
            self.null_max_pct.setSuffix(" %")
            pct_val = self._config.get("allowed_blank_percentage")
            self.null_max_pct.setValue(float(pct_val) if pct_val is not None else 0.0)
            self.null_max_pct.setToolTip("Maximum percentage of blank rows permitted (0 to 100%).")
            form.addRow("Allowed Blank %:", self.null_max_pct)

            self.null_chk_empty = QCheckBox('Count empty text ("" and spaces) as blanks')
            self.null_chk_empty.setChecked(self._config.get("include_empty_string", True))
            self.null_chk_empty.setToolTip('When checked, empty strings and spaces are treated as blank values.')
            form.addRow("", self.null_chk_empty)

        elif vtype == VALIDATION_TYPE_DUPLICATE:
            self.dup_max_count = QSpinBox()
            self.dup_max_count.setRange(0, 10_000_000)
            self.dup_max_count.setValue(int(self._config.get("allowed_duplicate_count", 0)))
            self.dup_max_count.setToolTip("Maximum number of duplicate values permitted before the test fails.")
            form.addRow("Allowed Duplicates:", self.dup_max_count)

            self.dup_case_sensitive = QCheckBox("Case-sensitive text comparison")
            self.dup_case_sensitive.setChecked(self._config.get("case_sensitive", False))
            self.dup_case_sensitive.setToolTip("When checked, comparisons distinguish between uppercase and lowercase letters.")
            form.addRow("", self.dup_case_sensitive)

        elif vtype == VALIDATION_TYPE_LATEST_DATE:
            self.date_max_age = QSpinBox()
            self.date_max_age.setRange(1, 8760)
            self.date_max_age.setValue(int(self._config.get("max_age_hours", 24)))
            self.date_max_age.setSuffix(" hours")
            self.date_max_age.setToolTip("Maximum hours allowed since the newest recorded date before flagging stale data.")
            form.addRow("Freshness SLA (Max Age):", self.date_max_age)

            self.date_disallow_future = QCheckBox("Fail if future dates are present")
            self.date_disallow_future.setChecked(not self._config.get("allow_future_dates", False))
            self.date_disallow_future.setToolTip("When checked, marks the test as failed if dates from tomorrow or beyond are found.")
            form.addRow("", self.date_disallow_future)

        elif vtype == VALIDATION_TYPE_ROW_COUNT:
            self.row_method = AnimatedComboBox()
            row_methods = [
                ("Minimum row count threshold", "Fails if total rows fall below this number."),
                ("Fixed expected count", "Checks if total row count matches an exact expected number."),
                ("Range [Min to Max]", "Checks if total row count stays within lower and upper bounds."),
                ("Compare with previous run", "Compares table row count against the last validation run."),
            ]
            for text, tip in row_methods:
                self.row_method.addItem(text)
                self.row_method.setItemData(self.row_method.count() - 1, tip, Qt.ItemDataRole.ToolTipRole)
            self.row_method.setToolTip("Evaluation method used to check the table row count.")
            self.row_method.currentIndexChanged.connect(
                lambda idx: self.row_method.setToolTip(self.row_method.itemData(idx, Qt.ItemDataRole.ToolTipRole) or "Evaluation method used to check the table row count.")
            )
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
            self.row_baseline.setToolTip("Threshold or expected number of rows for this table.")
            form.addRow("Threshold / Expected Rows:", self.row_baseline)

            self.row_dev_pct = QDoubleSpinBox()
            self.row_dev_pct.setRange(0.0, 100.0)
            self.row_dev_pct.setDecimals(1)
            self.row_dev_pct.setSuffix(" %")
            self.row_dev_pct.setValue(float(self._config.get("allowed_deviation_pct", 5.0)))
            self.row_dev_pct.setToolTip("Allowed percentage deviation before the row count test fails.")
            form.addRow("Allowed Deviation %:", self.row_dev_pct)

        elif vtype == VALIDATION_TYPE_REFRESH:
            self.ref_status = AnimatedComboBox()
            ref_status_items = [
                ("Completed", "Requires the dataset refresh to be completed successfully."),
                ("In Progress", "Accepts a refresh that is currently running."),
                ("Any", "Accepts any recorded refresh status."),
            ]
            for text, tip in ref_status_items:
                self.ref_status.addItem(text)
                self.ref_status.setItemData(self.ref_status.count() - 1, tip, Qt.ItemDataRole.ToolTipRole)
            self.ref_status.setToolTip("Required status of the Power BI dataset refresh.")
            self.ref_status.currentIndexChanged.connect(
                lambda idx: self.ref_status.setToolTip(self.ref_status.itemData(idx, Qt.ItemDataRole.ToolTipRole) or "Required status of the Power BI dataset refresh.")
            )
            cur_st = self._config.get("expected_status", "Completed")
            idx = self.ref_status.findText(cur_st)
            if idx >= 0:
                self.ref_status.setCurrentIndex(idx)
            form.addRow("Expected Refresh Status:", self.ref_status)

            self.ref_max_age = QSpinBox()
            self.ref_max_age.setRange(1, 720)
            self.ref_max_age.setValue(int(self._config.get("max_age_hours", 24)))
            self.ref_max_age.setSuffix(" hours")
            self.ref_max_age.setToolTip("Maximum allowed hours since the dataset was refreshed.")
            form.addRow("Max Age Since Refresh:", self.ref_max_age)

            self.ref_definition = AnimatedComboBox()
            self.ref_definition.addItem("Latest refresh attempt must succeed", "latest_attempt")
            self.ref_definition.setItemData(0, "Fails if the most recent refresh attempt resulted in an error.", Qt.ItemDataRole.ToolTipRole)
            self.ref_definition.addItem("At least one successful refresh within window", "latest_success")
            self.ref_definition.setItemData(1, "Passes if any refresh finished successfully within the max age window.", Qt.ItemDataRole.ToolTipRole)
            self.ref_definition.setToolTip("Rule criteria for verifying dataset refresh health.")
            self.ref_definition.currentIndexChanged.connect(
                lambda idx: self.ref_definition.setToolTip(self.ref_definition.itemData(idx, Qt.ItemDataRole.ToolTipRole) or "Rule criteria for verifying dataset refresh health.")
            )
            cur_def = self._config.get("definition", "latest_attempt")
            idx = 1 if cur_def == "latest_success" else 0
            self.ref_definition.setCurrentIndex(idx)
            form.addRow("SLA Rule Definition:", self.ref_definition)

        elif vtype == VALIDATION_TYPE_DAX_MEASURE:
            self.dax_expected = QDoubleSpinBox()
            self.dax_expected.setRange(-1_000_000_000.0, 1_000_000_000.0)
            self.dax_expected.setDecimals(2)
            self.dax_expected.setValue(float(self._config.get("expected_value", 0.0)))
            self.dax_expected.setToolTip("The expected numerical target value that this DAX measure should return.")
            form.addRow("Expected Measure Value:", self.dax_expected)

            self.dax_dev_pct = QDoubleSpinBox()
            self.dax_dev_pct.setRange(0.0, 100.0)
            self.dax_dev_pct.setDecimals(2)
            self.dax_dev_pct.setSuffix(" %")
            self.dax_dev_pct.setValue(float(self._config.get("allowed_deviation_pct", 0.0)))
            self.dax_dev_pct.setToolTip("Allowed percentage difference from the expected measure value.")
            form.addRow("Allowed Deviation %:", self.dax_dev_pct)

        elif vtype == VALIDATION_TYPE_ANOMALY:
            # 1. Baseline Floor (Min)
            self.anom_chk_min = QCheckBox("Enable Minimum Baseline (Floor):")
            self.anom_chk_min.setStyleSheet("font-weight: 600; color: #1E293B;")
            self.anom_chk_min.setToolTip("Turn on a minimum lower bound. Any value below this number is flagged as an anomaly.")
            self.anom_spin_min = QDoubleSpinBox()
            self.anom_spin_min.setRange(-1e12, 1e12)
            self.anom_spin_min.setDecimals(2)
            self.anom_spin_min.setToolTip("Minimum allowed numerical value (floor).")
            has_min = self._config.get("min_baseline") is not None or self._config.get("min_value") is not None
            cur_min = float(self._config.get("min_baseline") if self._config.get("min_baseline") is not None else self._config.get("min_value", 0.0))
            self.anom_spin_min.setValue(cur_min)
            self.anom_spin_min.setEnabled(has_min)
            self.anom_chk_min.setChecked(has_min)
            self.anom_chk_min.toggled.connect(self.anom_spin_min.setEnabled)

            h_min = QHBoxLayout()
            h_min.addWidget(self.anom_chk_min)
            h_min.addWidget(self.anom_spin_min, stretch=1)
            form.addRow("Minimum Floor:", h_min)

            # 2. Baseline Ceiling (Max)
            self.anom_chk_max = QCheckBox("Enable Maximum Baseline (Ceiling):")
            self.anom_chk_max.setStyleSheet("font-weight: 600; color: #1E293B;")
            self.anom_chk_max.setToolTip("Turn on a maximum upper bound. Any value above this number is flagged as an anomaly.")
            self.anom_spin_max = QDoubleSpinBox()
            self.anom_spin_max.setRange(-1e12, 1e12)
            self.anom_spin_max.setDecimals(2)
            self.anom_spin_max.setToolTip("Maximum allowed numerical value (ceiling).")
            has_max = self._config.get("max_baseline") is not None or self._config.get("max_value") is not None
            cur_max = float(self._config.get("max_baseline") if self._config.get("max_baseline") is not None else self._config.get("max_value", 0.0))
            self.anom_spin_max.setValue(cur_max)
            self.anom_spin_max.setEnabled(has_max)
            self.anom_chk_max.setChecked(has_max)
            self.anom_chk_max.toggled.connect(self.anom_spin_max.setEnabled)

            h_max = QHBoxLayout()
            h_max.addWidget(self.anom_chk_max)
            h_max.addWidget(self.anom_spin_max, stretch=1)
            form.addRow("Maximum Ceiling:", h_max)

            # 3. Secondary Anomaly Detection Check Method
            self.anom_method_combo = AnimatedComboBox()
            anom_method_items = [
                ("Baseline Thresholds Only (Min / Max)", "threshold_only", "Only checks against minimum floor and maximum ceiling limits."),
                ("± % Change from Fixed Baseline", "percentage", "Flags values that differ by more than a percentage from a fixed target."),
                ("± % Change from Previous Run", "previous_run", "Flags values that jump or drop significantly compared to the last run."),
                ("± % from Historical Median", "median", "Flags values that deviate from the historical median across past runs."),
                ("± Standard Deviation (Z-Score)", "z_score", "Flags statistical outliers using rolling mean and standard deviation."),
            ]
            for text, val, tip in anom_method_items:
                self.anom_method_combo.addItem(text, val)
                self.anom_method_combo.setItemData(self.anom_method_combo.count() - 1, tip, Qt.ItemDataRole.ToolTipRole)
            self.anom_method_combo.setToolTip("Method used to detect statistical anomalies.")
            self.anom_method_combo.currentIndexChanged.connect(
                lambda idx: self.anom_method_combo.setToolTip(self.anom_method_combo.itemData(idx, Qt.ItemDataRole.ToolTipRole) or "Method used to detect statistical anomalies.")
            )

            cur_m = str(self._config.get("comparison_method", "z_score")).strip().lower()
            if cur_m in ("threshold_only", "baseline_only", "none"):
                target_key = "threshold_only"
            elif cur_m in ("percentage", "fixed_baseline"):
                target_key = "percentage"
            elif cur_m in ("previous_run", "previous_period"):
                target_key = "previous_run"
            elif cur_m == "median":
                target_key = "median"
            else:
                target_key = "z_score"

            m_idx = next((i for i in range(self.anom_method_combo.count()) if self.anom_method_combo.itemData(i) == target_key), 4)
            self.anom_method_combo.setCurrentIndex(m_idx)
            form.addRow("Detection Method:", self.anom_method_combo)

            # Fixed Baseline Value (for "percentage")
            self.anom_fixed_baseline = QDoubleSpinBox()
            self.anom_fixed_baseline.setRange(-1e12, 1e12)
            self.anom_fixed_baseline.setDecimals(2)
            self.anom_fixed_baseline.setValue(float(self._config.get("baseline_value", 0.0)))
            self.anom_fixed_baseline.setToolTip("Fixed baseline target value to calculate percentage deviation against.")
            self.anom_fixed_baseline_row_lbl = QLabel("Fixed Baseline Value:")
            form.addRow(self.anom_fixed_baseline_row_lbl, self.anom_fixed_baseline)

            # Allowed Deviation % (for "percentage", "previous_run", "median")
            self.anom_dev_pct = QDoubleSpinBox()
            self.anom_dev_pct.setRange(0.1, 500.0)
            self.anom_dev_pct.setDecimals(1)
            self.anom_dev_pct.setSuffix(" %")
            self.anom_dev_pct.setValue(float(self._config.get("allowed_deviation_pct", 10.0)))
            self.anom_dev_pct.setToolTip("Maximum allowed percentage change before flagging an anomaly.")
            self.anom_dev_pct_row_lbl = QLabel("Allowed Deviation %:")
            form.addRow(self.anom_dev_pct_row_lbl, self.anom_dev_pct)

            # Sensitivity (for "z_score")
            self.anom_sensitivity = AnimatedComboBox()
            anom_sens_items = [
                ("Standard (Z-Score ±2.5)", "z_score", "Flags values more than 2.5 standard deviations from the average."),
                ("High Sensitivity (Z-Score ±2.0)", "z_score_high", "Flags smaller variations for earlier warning (more alerts)."),
                ("Tolerant (Z-Score ±3.0)", "z_score_tolerant", "Only flags extreme outliers (fewer alerts)."),
            ]
            for text, val, tip in anom_sens_items:
                self.anom_sensitivity.addItem(text, val)
                self.anom_sensitivity.setItemData(self.anom_sensitivity.count() - 1, tip, Qt.ItemDataRole.ToolTipRole)
            self.anom_sensitivity.setToolTip("Statistical sensitivity threshold for outlier detection.")
            self.anom_sensitivity.currentIndexChanged.connect(
                lambda idx: self.anom_sensitivity.setToolTip(self.anom_sensitivity.itemData(idx, Qt.ItemDataRole.ToolTipRole) or "Statistical sensitivity threshold for outlier detection.")
            )
            cur_z = self._config.get("z_score_threshold", 2.5)
            z_code = "z_score_high" if cur_z == 2.0 else ("z_score_tolerant" if cur_z == 3.0 else "z_score")
            sm_idx = next((i for i in range(self.anom_sensitivity.count()) if self.anom_sensitivity.itemData(i) == z_code), 0)
            self.anom_sensitivity.setCurrentIndex(sm_idx)
            self.anom_sens_row_lbl = QLabel("Detection Sensitivity:")
            form.addRow(self.anom_sens_row_lbl, self.anom_sensitivity)

            # Lookback Window (for "median", "z_score")
            self.anom_lookback = AnimatedComboBox()
            anom_lookback_items = [
                ("7 Days Lookback", 7, "Calculate historical average using the past 7 days of runs."),
                ("15 Days Lookback", 15, "Calculate historical average using the past 15 days of runs."),
                ("30 Days Lookback (Recommended)", 30, "Calculate historical average using the past 30 days of runs."),
                ("60 Days Lookback", 60, "Calculate historical average using the past 60 days of runs."),
                ("90 Days Lookback", 90, "Calculate historical average using the past 90 days of runs."),
            ]
            for text, val, tip in anom_lookback_items:
                self.anom_lookback.addItem(text, val)
                self.anom_lookback.setItemData(self.anom_lookback.count() - 1, tip, Qt.ItemDataRole.ToolTipRole)
            self.anom_lookback.setToolTip("Lookback window used to compute historical averages.")
            self.anom_lookback.currentIndexChanged.connect(
                lambda idx: self.anom_lookback.setToolTip(self.anom_lookback.itemData(idx, Qt.ItemDataRole.ToolTipRole) or "Lookback window used to compute historical averages.")
            )
            cur_lb = self._config.get("lookback_days", 30)
            lb_idx = next((i for i in range(self.anom_lookback.count()) if self.anom_lookback.itemData(i) == cur_lb), 2)
            self.anom_lookback.setCurrentIndex(lb_idx)
            self.anom_lookback_row_lbl = QLabel("Historical Lookback:")
            form.addRow(self.anom_lookback_row_lbl, self.anom_lookback)

            def _update_method_visibility():
                meth = self.anom_method_combo.currentData()
                is_pct = meth == "percentage"
                is_prev = meth == "previous_run"
                is_med = meth == "median"
                is_z = meth == "z_score"

                self.anom_fixed_baseline_row_lbl.setVisible(is_pct)
                self.anom_fixed_baseline.setVisible(is_pct)

                self.anom_dev_pct_row_lbl.setVisible(is_pct or is_prev or is_med)
                self.anom_dev_pct.setVisible(is_pct or is_prev or is_med)

                self.anom_sens_row_lbl.setVisible(is_z)
                self.anom_sensitivity.setVisible(is_z)

                self.anom_lookback_row_lbl.setVisible(is_med or is_z)
                self.anom_lookback.setVisible(is_med or is_z)

            self.anom_method_combo.currentIndexChanged.connect(lambda _: _update_method_visibility())
            _update_method_visibility()

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
            if self.anom_chk_min.isChecked():
                cfg["min_baseline"] = self.anom_spin_min.value()
                cfg["min_value"] = self.anom_spin_min.value()
            else:
                cfg.pop("min_baseline", None)
                cfg.pop("min_value", None)

            if self.anom_chk_max.isChecked():
                cfg["max_baseline"] = self.anom_spin_max.value()
                cfg["max_value"] = self.anom_spin_max.value()
            else:
                cfg.pop("max_baseline", None)
                cfg.pop("max_value", None)

            method = self.anom_method_combo.currentData()
            cfg["comparison_method"] = method
            if method == "percentage":
                cfg["baseline_value"] = self.anom_fixed_baseline.value()
                cfg["allowed_deviation_pct"] = self.anom_dev_pct.value()
            elif method in ("previous_run", "previous_period"):
                cfg["allowed_deviation_pct"] = self.anom_dev_pct.value()
            elif method == "median":
                cfg["allowed_deviation_pct"] = self.anom_dev_pct.value()
                cfg["lookback_days"] = self.anom_lookback.currentData()
            elif method == "z_score":
                z_data = self.anom_sensitivity.currentData()
                z_val = 2.0 if z_data == "z_score_high" else (3.0 if z_data == "z_score_tolerant" else 2.5)
                cfg["z_score_threshold"] = z_val
                cfg["lookback_days"] = self.anom_lookback.currentData()

        self._result_config = cfg
        self._result_rule_name = self.rule_name_input.text().strip()
        self.accept()
