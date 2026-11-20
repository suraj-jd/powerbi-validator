"""Modal dialog for editing row-specific advanced validation rule configuration (BRD 5.4)."""

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

from app.ui.widgets.animated_combo import AnimatedComboBox

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

logger = logging.getLogger(__name__)


class AdvancedSettingsDialog(QDialog):
    """Row-specific advanced configuration modal (BRD 5.4)."""

    def __init__(
        self,
        *,
        rule_name: str,
        validation_type: str,
        current_config: dict[str, Any] | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(f"Advanced Settings: {rule_name}")
        self.setModal(True)
        self.setMinimumWidth(560)
        self.setObjectName("ConfirmDialog")

        # Independent copy of config to ensure isolation
        self._config: dict[str, Any] = copy.deepcopy(current_config or {})
        self._validation_type = validation_type
        self._result_config: dict[str, Any] | None = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(14)

        # Header Title
        title = QLabel(f"Advanced Settings: {rule_name}")
        title.setObjectName("DialogTitle")
        layout.addWidget(title)

        val_display = VALIDATION_TYPES.get(validation_type, validation_type)
        banner = QLabel(f"Configuring advanced thresholds, tolerances, and filter conditions for {val_display}.")
        banner.setObjectName("InfoBanner")
        banner.setWordWrap(True)
        layout.addWidget(banner)

        # Container card
        card = QFrame()
        card.setObjectName("DialogCard")
        card.setStyleSheet(
            "#DialogCard { background-color: #F8FAFC; border: 1px solid #E2E8F0; "
            "border-radius: 8px; padding: 16px; }"
        )
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(12, 10, 12, 10)

        # Build settings panel for the specific validation type
        self._build_type_settings(card_layout)
        layout.addWidget(card)

        # Bottom Buttons
        btn_row = QHBoxLayout()
        btn_row.setSpacing(10)
        btn_row.addStretch(1)

        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.setObjectName("SecondaryButton")
        self.cancel_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.cancel_button.clicked.connect(self.reject)
        btn_row.addWidget(self.cancel_button)

        self.save_button = QPushButton("Save Settings")
        self.save_button.setObjectName("PrimaryButton")
        self.save_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.save_button.setDefault(True)
        self.save_button.clicked.connect(self._save_and_accept)
        btn_row.addWidget(self.save_button)

        layout.addLayout(btn_row)

    @property
    def config(self) -> dict[str, Any]:
        return self._result_config if self._result_config is not None else self._config

    def _build_type_settings(self, container_layout: QVBoxLayout) -> None:
        form = QFormLayout()
        form.setSpacing(10)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        vtype = self._validation_type

        if vtype == VALIDATION_TYPE_NULL:
            # Null definition checks
            self.chk_db_null = QCheckBox("Database NULL")
            self.chk_db_null.setChecked(self._config.get("include_db_null", True))
            self.chk_dax_blank = QCheckBox("DAX BLANK")
            self.chk_dax_blank.setChecked(self._config.get("include_dax_blank", True))
            self.chk_empty_str = QCheckBox('Empty String ("")')
            self.chk_empty_str.setChecked(self._config.get("include_empty_string", True))
            self.chk_whitespace = QCheckBox("Whitespace-only String")
            self.chk_whitespace.setChecked(self._config.get("include_whitespace", False))

            null_types_box = QVBoxLayout()
            null_types_box.setSpacing(4)
            null_types_box.addWidget(self.chk_db_null)
            null_types_box.addWidget(self.chk_dax_blank)
            null_types_box.addWidget(self.chk_empty_str)
            null_types_box.addWidget(self.chk_whitespace)
            form.addRow(self._make_label("Null Definition:"), null_types_box)

            self.spin_blank_count = QSpinBox()
            self.spin_blank_count.setRange(0, 10_000_000)
            self.spin_blank_count.setValue(self._config.get("allowed_blank_count", 0))
            form.addRow(self._make_label("Allowed Blank Count:"), self.spin_blank_count)

            self.spin_blank_pct = QDoubleSpinBox()
            self.spin_blank_pct.setRange(0.0, 100.0)
            self.spin_blank_pct.setSuffix(" %")
            self.spin_blank_pct.setDecimals(2)
            self.spin_blank_pct.setValue(float(self._config.get("allowed_blank_percentage", 0.0)))
            form.addRow(self._make_label("Allowed Blank %:"), self.spin_blank_pct)

            self.edit_filter = QLineEdit(self._config.get("filter_condition", ""))
            self.edit_filter.setPlaceholderText('e.g. [Status] = "Active"')
            form.addRow(self._make_label("Filter Condition (opt):"), self.edit_filter)

        elif vtype == VALIDATION_TYPE_DUPLICATE:
            self.edit_keys = QLineEdit(", ".join(self._config.get("key_columns", [])))
            self.edit_keys.setPlaceholderText("Comma-separated key columns (defaults to target column)")
            form.addRow(self._make_label("Key Columns:"), self.edit_keys)

            self.spin_dup_count = QSpinBox()
            self.spin_dup_count.setRange(0, 10_000_000)
            self.spin_dup_count.setValue(self._config.get("allowed_duplicate_count", 0))
            form.addRow(self._make_label("Allowed Duplicates:"), self.spin_dup_count)

            self.edit_filter = QLineEdit(self._config.get("filter_condition", ""))
            self.edit_filter.setPlaceholderText('e.g. [Country] = "US"')
            form.addRow(self._make_label("Filter Condition (opt):"), self.edit_filter)

        elif vtype == VALIDATION_TYPE_LATEST_DATE:
            self.spin_max_age = QDoubleSpinBox()
            self.spin_max_age.setRange(0.1, 87600.0)
            self.spin_max_age.setSuffix(" hours")
            self.spin_max_age.setValue(float(self._config.get("max_age_hours", 24.0)))
            form.addRow(self._make_label("Max Allowed Age:"), self.spin_max_age)

            self.combo_tz = AnimatedComboBox()
            self.combo_tz.addItems(["UTC", "Local Machine Time", "America/New_York", "Europe/London", "Asia/Kolkata"])
            saved_tz = self._config.get("timezone", "UTC")
            idx = self.combo_tz.findText(saved_tz)
            if idx >= 0:
                self.combo_tz.setCurrentIndex(idx)
            form.addRow(self._make_label("Comparison Timezone:"), self.combo_tz)

            self.chk_allow_future = QCheckBox("Allow future dates (do not fail if date > current timestamp)")
            self.chk_allow_future.setChecked(self._config.get("allow_future_dates", False))
            form.addRow("", self.chk_allow_future)

        elif vtype == VALIDATION_TYPE_ROW_COUNT:
            self.combo_baseline_method = AnimatedComboBox()
            self.combo_baseline_method.addItems([
                "Fixed Count",
                "Previous Successful Run",
                "Historical Mean",
            ])
            method_key = self._config.get("baseline_method", "fixed")
            method_map = {"fixed": 0, "previous_run": 1, "historical_mean": 2}
            self.combo_baseline_method.setCurrentIndex(method_map.get(method_key, 0))
            form.addRow(self._make_label("Baseline Method:"), self.combo_baseline_method)

            self.spin_baseline_val = QSpinBox()
            self.spin_baseline_val.setRange(0, 2_000_000_000)
            self.spin_baseline_val.setValue(self._config.get("baseline_value", 10_000))
            form.addRow(self._make_label("Fixed Baseline Count:"), self.spin_baseline_val)

            self.spin_deviation_pct = QDoubleSpinBox()
            self.spin_deviation_pct.setRange(0.0, 100.0)
            self.spin_deviation_pct.setSuffix(" %")
            self.spin_deviation_pct.setValue(float(self._config.get("allowed_deviation_pct", 5.0)))
            form.addRow(self._make_label("Allowed Deviation:"), self.spin_deviation_pct)

            self.spin_min_count = QSpinBox()
            self.spin_min_count.setRange(0, 2_000_000_000)
            self.spin_min_count.setValue(self._config.get("min_count", 0))
            form.addRow(self._make_label("Min Hard Limit:"), self.spin_min_count)

            self.spin_max_count = QSpinBox()
            self.spin_max_count.setRange(0, 2_000_000_000)
            self.spin_max_count.setValue(self._config.get("max_count", 0))
            self.spin_max_count.setSpecialValueText("No Maximum")
            form.addRow(self._make_label("Max Hard Limit:"), self.spin_max_count)

        elif vtype == VALIDATION_TYPE_DAX_MEASURE:
            self.combo_exp_method = AnimatedComboBox()
            self.combo_exp_method.addItems([
                "Fixed Baseline",
                "Min / Max Range",
                "Previous Successful Run",
                "Historical Mean",
                "Historical Median",
            ])
            saved_m = self._config.get("expected_method", "fixed")
            m_map = {"fixed": 0, "min_max": 1, "previous_run": 2, "historical_mean": 3, "historical_median": 4}
            self.combo_exp_method.setCurrentIndex(m_map.get(saved_m, 0))
            form.addRow(self._make_label("Expected Method:"), self.combo_exp_method)

            self.spin_exp_val = QDoubleSpinBox()
            self.spin_exp_val.setRange(-1_000_000_000.0, 1_000_000_000.0)
            self.spin_exp_val.setDecimals(2)
            self.spin_exp_val.setValue(float(self._config.get("expected_value", 0.0)))
            form.addRow(self._make_label("Expected Value:"), self.spin_exp_val)

            self.spin_min_val = QDoubleSpinBox()
            self.spin_min_val.setRange(-1_000_000_000.0, 1_000_000_000.0)
            self.spin_min_val.setValue(float(self._config.get("min_value", 0.0)))
            form.addRow(self._make_label("Min Allowed:"), self.spin_min_val)

            self.spin_max_val = QDoubleSpinBox()
            self.spin_max_val.setRange(-1_000_000_000.0, 1_000_000_000.0)
            self.spin_max_val.setValue(float(self._config.get("max_value", 1_000_000.0)))
            form.addRow(self._make_label("Max Allowed:"), self.spin_max_val)

            self.spin_dax_dev = QDoubleSpinBox()
            self.spin_dax_dev.setRange(0.0, 100.0)
            self.spin_dax_dev.setSuffix(" %")
            self.spin_dax_dev.setValue(float(self._config.get("allowed_deviation_pct", 5.0)))
            form.addRow(self._make_label("Allowed Deviation:"), self.spin_dax_dev)

            self.edit_filter = QLineEdit(self._config.get("filter_context", ""))
            self.edit_filter.setPlaceholderText('e.g. FILTER(All(Dates), Dates[Year] = 2024)')
            form.addRow(self._make_label("DAX Filter Context:"), self.edit_filter)

        elif vtype == VALIDATION_TYPE_ANOMALY:
            # Baseline Floor & Ceiling thresholds
            self.spin_min_baseline = QDoubleSpinBox()
            self.spin_min_baseline.setRange(-1e12, 1e12)
            self.spin_min_baseline.setDecimals(2)
            cur_min = self._config.get("min_baseline") if self._config.get("min_baseline") is not None else self._config.get("min_value")
            self.spin_min_baseline.setValue(float(cur_min) if cur_min is not None else 0.0)
            self.chk_min_baseline = QCheckBox("Enable Min Floor:")
            self.chk_min_baseline.setChecked(cur_min is not None)
            self.spin_min_baseline.setEnabled(cur_min is not None)
            self.chk_min_baseline.toggled.connect(self.spin_min_baseline.setEnabled)
            h_min = QHBoxLayout()
            h_min.addWidget(self.chk_min_baseline)
            h_min.addWidget(self.spin_min_baseline, stretch=1)
            form.addRow(self._make_label("Minimum Baseline (Floor):"), h_min)

            self.spin_max_baseline = QDoubleSpinBox()
            self.spin_max_baseline.setRange(-1e12, 1e12)
            self.spin_max_baseline.setDecimals(2)
            cur_max = self._config.get("max_baseline") if self._config.get("max_baseline") is not None else self._config.get("max_value")
            self.spin_max_baseline.setValue(float(cur_max) if cur_max is not None else 0.0)
            self.chk_max_baseline = QCheckBox("Enable Max Ceiling:")
            self.chk_max_baseline.setChecked(cur_max is not None)
            self.spin_max_baseline.setEnabled(cur_max is not None)
            self.chk_max_baseline.toggled.connect(self.spin_max_baseline.setEnabled)
            h_max = QHBoxLayout()
            h_max.addWidget(self.chk_max_baseline)
            h_max.addWidget(self.spin_max_baseline, stretch=1)
            form.addRow(self._make_label("Maximum Baseline (Ceiling):"), h_max)

            self.combo_agg = AnimatedComboBox()
            self.combo_agg.addItems(["MEASURE", "SUM", "COUNT", "DISTINCTCOUNT", "AVERAGE", "MIN", "MAX"])
            agg_idx = self.combo_agg.findText(self._config.get("aggregation", "MEASURE"))
            if agg_idx >= 0:
                self.combo_agg.setCurrentIndex(agg_idx)
            form.addRow(self._make_label("Aggregation:"), self.combo_agg)

            self.edit_date_col = QLineEdit(self._config.get("date_column", ""))
            self.edit_date_col.setPlaceholderText("e.g. OrderDate or Calendar[Date]")
            form.addRow(self._make_label("Time / Date Column:"), self.edit_date_col)

            self.combo_comp_method = AnimatedComboBox()
            self.combo_comp_method.addItems([
                "Z-Score (Standard Deviation)",
                "Historical Median",
                "Historical Mean",
                "Previous Period",
            ])
            comp_idx = {"z_score": 0, "historical_median": 1, "historical_mean": 2, "previous_period": 3}.get(
                self._config.get("comparison_method", "z_score"), 0
            )
            self.combo_comp_method.setCurrentIndex(comp_idx)
            form.addRow(self._make_label("Comparison Method:"), self.combo_comp_method)

            self.spin_lookback = QSpinBox()
            self.spin_lookback.setRange(1, 365)
            self.spin_lookback.setSuffix(" days")
            self.spin_lookback.setValue(self._config.get("lookback_days", 30))
            form.addRow(self._make_label("Lookback Period:"), self.spin_lookback)

            self.spin_anom_dev = QDoubleSpinBox()
            self.spin_anom_dev.setRange(0.0, 100.0)
            self.spin_anom_dev.setSuffix(" %")
            self.spin_anom_dev.setValue(float(self._config.get("allowed_deviation_pct", 10.0)))
            form.addRow(self._make_label("Allowed Deviation:"), self.spin_anom_dev)

            self.spin_min_obs = QSpinBox()
            self.spin_min_obs.setRange(1, 1000)
            self.spin_min_obs.setValue(self._config.get("min_observations", 10))
            form.addRow(self._make_label("Min Observations:"), self.spin_min_obs)

            self.chk_ignore_weekends = QCheckBox("Ignore Saturdays & Sundays in historical baseline")
            self.chk_ignore_weekends.setChecked(self._config.get("ignore_weekends", True))
            form.addRow("", self.chk_ignore_weekends)

            self.combo_direction = AnimatedComboBox()
            self.combo_direction.addItems(["Both (Increase or Decrease)", "Increase Only", "Decrease Only"])
            dir_idx = {"both": 0, "increase_only": 1, "decrease_only": 2}.get(
                self._config.get("direction", "both"), 0
            )
            self.combo_direction.setCurrentIndex(dir_idx)
            form.addRow(self._make_label("Flag Direction:"), self.combo_direction)

            self.combo_missing = AnimatedComboBox()
            self.combo_missing.addItems(["Warning (continue run)", "Fail (flag rule failed)", "Skip Rule"])
            miss_idx = {"warning": 0, "fail": 1, "skip": 2}.get(
                self._config.get("missing_history_behavior", "warning"), 0
            )
            self.combo_missing.setCurrentIndex(miss_idx)
            form.addRow(self._make_label("Missing History Action:"), self.combo_missing)

        elif vtype == VALIDATION_TYPE_REFRESH:
            self.combo_definition = AnimatedComboBox()
            self.combo_definition.addItems([
                "Latest Refresh Attempt",
                "Latest Successful Refresh",
                "Latest Completed Refresh",
            ])
            def_map = {"latest_attempt": 0, "latest_success": 1, "latest_completed": 2}
            self.combo_definition.setCurrentIndex(def_map.get(self._config.get("definition", "latest_attempt"), 0))
            form.addRow(self._make_label("Evaluation Target:"), self.combo_definition)

            self.combo_status = AnimatedComboBox()
            self.combo_status.addItems(["Completed", "Success", "Any Active"])
            s_idx = self.combo_status.findText(self._config.get("expected_status", "Completed"))
            if s_idx >= 0:
                self.combo_status.setCurrentIndex(s_idx)
            form.addRow(self._make_label("Expected Status:"), self.combo_status)

            self.spin_ref_age = QDoubleSpinBox()
            self.spin_ref_age.setRange(0.1, 720.0)
            self.spin_ref_age.setSuffix(" hours")
            self.spin_ref_age.setValue(float(self._config.get("max_age_hours", 24.0)))
            form.addRow(self._make_label("Max Refresh Age:"), self.spin_ref_age)

            self.spin_ref_duration = QDoubleSpinBox()
            self.spin_ref_duration.setRange(1.0, 1440.0)
            self.spin_ref_duration.setSuffix(" minutes")
            self.spin_ref_duration.setValue(float(self._config.get("max_duration_minutes", 60.0)))
            form.addRow(self._make_label("Max Allowed Duration:"), self.spin_ref_duration)

        container_layout.addLayout(form)

    def _make_label(self, text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setStyleSheet("color: #334155; font-weight: 600; font-size: 12px;")
        return lbl

    def _save_and_accept(self) -> None:
        vtype = self._validation_type
        cfg: dict[str, Any] = copy.deepcopy(self._config)

        if vtype == VALIDATION_TYPE_NULL:
            cfg["include_db_null"] = self.chk_db_null.isChecked()
            cfg["include_dax_blank"] = self.chk_dax_blank.isChecked()
            cfg["include_empty_string"] = self.chk_empty_str.isChecked()
            cfg["include_whitespace"] = self.chk_whitespace.isChecked()
            cfg["allowed_blank_count"] = self.spin_blank_count.value()
            cfg["allowed_blank_percentage"] = self.spin_blank_pct.value()
            cfg["filter_condition"] = self.edit_filter.text().strip()

        elif vtype == VALIDATION_TYPE_DUPLICATE:
            raw_keys = [k.strip() for k in self.edit_keys.text().split(",") if k.strip()]
            cfg["key_columns"] = raw_keys
            cfg["allowed_duplicate_count"] = self.spin_dup_count.value()
            cfg["filter_condition"] = self.edit_filter.text().strip()

        elif vtype == VALIDATION_TYPE_LATEST_DATE:
            cfg["max_age_hours"] = self.spin_max_age.value()
            cfg["timezone"] = self.combo_tz.currentText()
            cfg["allow_future_dates"] = self.chk_allow_future.isChecked()

        elif vtype == VALIDATION_TYPE_ROW_COUNT:
            method_keys = ["fixed", "previous_run", "historical_mean"]
            cfg["baseline_method"] = method_keys[self.combo_baseline_method.currentIndex()]
            cfg["baseline_value"] = self.spin_baseline_val.value()
            cfg["allowed_deviation_pct"] = self.spin_deviation_pct.value()
            cfg["min_count"] = self.spin_min_count.value()
            cfg["max_count"] = self.spin_max_count.value()

        elif vtype == VALIDATION_TYPE_DAX_MEASURE:
            m_keys = ["fixed", "min_max", "previous_run", "historical_mean", "historical_median"]
            cfg["expected_method"] = m_keys[self.combo_exp_method.currentIndex()]
            cfg["expected_value"] = self.spin_exp_val.value()
            cfg["min_value"] = self.spin_min_val.value()
            cfg["max_value"] = self.spin_max_val.value()
            cfg["allowed_deviation_pct"] = self.spin_dax_dev.value()
            cfg["filter_context"] = self.edit_filter.text().strip()

        elif vtype == VALIDATION_TYPE_ANOMALY:
            if self.chk_min_baseline.isChecked():
                cfg["min_baseline"] = self.spin_min_baseline.value()
                cfg["min_value"] = self.spin_min_baseline.value()
            else:
                cfg.pop("min_baseline", None)
                cfg.pop("min_value", None)

            if self.chk_max_baseline.isChecked():
                cfg["max_baseline"] = self.spin_max_baseline.value()
                cfg["max_value"] = self.spin_max_baseline.value()
            else:
                cfg.pop("max_baseline", None)
                cfg.pop("max_value", None)

            cfg["aggregation"] = self.combo_agg.currentText()
            cfg["date_column"] = self.edit_date_col.text().strip()
            comp_keys = ["z_score", "historical_median", "historical_mean", "previous_period"]
            cfg["comparison_method"] = comp_keys[self.combo_comp_method.currentIndex()]
            cfg["lookback_days"] = self.spin_lookback.value()
            cfg["allowed_deviation_pct"] = self.spin_anom_dev.value()
            cfg["min_observations"] = self.spin_min_obs.value()
            cfg["ignore_weekends"] = self.chk_ignore_weekends.isChecked()
            dir_keys = ["both", "increase_only", "decrease_only"]
            cfg["direction"] = dir_keys[self.combo_direction.currentIndex()]
            miss_keys = ["warning", "fail", "skip"]
            cfg["missing_history_behavior"] = miss_keys[self.combo_missing.currentIndex()]

        elif vtype == VALIDATION_TYPE_REFRESH:
            def_keys = ["latest_attempt", "latest_success", "latest_completed"]
            cfg["definition"] = def_keys[self.combo_definition.currentIndex()]
            cfg["expected_status"] = self.combo_status.currentText()
            cfg["max_age_hours"] = self.spin_ref_age.value()
            cfg["max_duration_minutes"] = self.spin_ref_duration.value()

        self._result_config = cfg
        self.accept()
