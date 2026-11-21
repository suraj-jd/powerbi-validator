"""Power BI-style recurring validation schedule dialog."""

from __future__ import annotations

from datetime import datetime, time
import logging

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from app.services.scheduler_service import (
    DEFAULT_DAILY_TIMES,
    ScheduleConfig,
    ValidationSchedulerService,
    compute_next_run,
    format_next_run_display,
)

logger = logging.getLogger(__name__)

# Standard 30-minute intervals for Power BI style time picker
TIME_OPTIONS_30M = [f"{h:02d}:{m:02d}" for h in range(24) for m in (0, 30)]


class ScheduleValidationDialog(QDialog):
    """Dialog configuring recurring automated validation runs inspired by Power BI Scheduled Refresh."""

    def __init__(
        self,
        scheduler_service: ValidationSchedulerService,
        rule_count: int = 0,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._scheduler_service = scheduler_service
        self._rule_count = rule_count
        self._config = scheduler_service.config

        # Working list of times (sorted)
        self._times: list[str] = list(self._config.times) if self._config.times else list(DEFAULT_DAILY_TIMES)
        self._times.sort()

        self.setWindowTitle("Schedule Automated Validations")
        self.setMinimumWidth(560)
        self.resize(600, 680)

        self._build_ui()
        self._apply_initial_state()
        self._update_preview()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 22, 24, 20)
        layout.setSpacing(16)

        # Header Title
        title_box = QVBoxLayout()
        title_box.setSpacing(3)
        lbl_title = QLabel("Automated Validation Scheduler")
        lbl_title.setStyleSheet("font-size: 17px; font-weight: 700; color: #0F172A;")
        title_box.addWidget(lbl_title)

        lbl_sub = QLabel(
            "Mirroring Power BI Scheduled Refresh: automatically evaluate all rules "
            "from your Validation Sheet at configured times while the application is active."
        )
        lbl_sub.setWordWrap(True)
        lbl_sub.setStyleSheet("font-size: 12px; color: #64748B; line-height: 1.4;")
        title_box.addWidget(lbl_sub)
        layout.addLayout(title_box)

        # 1. Validation Sheet Prerequisite Status Pill
        self.sheet_status_frame = QFrame()
        self.sheet_status_layout = QHBoxLayout(self.sheet_status_frame)
        self.sheet_status_layout.setContentsMargins(12, 10, 12, 10)
        self.sheet_status_layout.setSpacing(8)

        self.lbl_sheet_icon = QLabel()
        self.lbl_sheet_icon.setFixedSize(18, 18)
        self.sheet_status_layout.addWidget(self.lbl_sheet_icon)

        self.lbl_sheet_msg = QLabel()
        self.lbl_sheet_msg.setWordWrap(True)
        self.lbl_sheet_msg.setStyleSheet("font-size: 12px; font-weight: 600;")
        self.sheet_status_layout.addWidget(self.lbl_sheet_msg, stretch=1)
        layout.addWidget(self.sheet_status_frame)

        self._update_sheet_status_banner()

        # 2. Main Master Toggle (Power BI style: "Keep your data up to date")
        toggle_box = QFrame()
        toggle_box.setStyleSheet(
            "QFrame { background-color: #FFFFFF; border: 1px solid #E2E8F0; border-radius: 8px; padding: 12px; }"
        )
        t_lay = QVBoxLayout(toggle_box)
        t_lay.setContentsMargins(4, 4, 4, 4)
        t_lay.setSpacing(4)

        self.chk_enabled = QCheckBox("Keep your validations up to date")
        self.chk_enabled.setStyleSheet("font-size: 14px; font-weight: 700; color: #0F172A;")
        self.chk_enabled.toggled.connect(self._on_enabled_toggled)
        t_lay.addWidget(self.chk_enabled)

        lbl_toggle_sub = QLabel(
            "Run automated validations in the background without requiring manual clicks."
        )
        lbl_toggle_sub.setStyleSheet("font-size: 11px; color: #64748B; margin-left: 24px;")
        t_lay.addWidget(lbl_toggle_sub)
        layout.addWidget(toggle_box)

        # 3. Schedule Settings Container (Disabled when toggle is OFF)
        self.settings_card = QFrame()
        self.settings_card.setStyleSheet(
            "QFrame#SettingsCard { background-color: #FFFFFF; border: 1px solid #E2E8F0; border-radius: 8px; }"
        )
        self.settings_card.setObjectName("SettingsCard")
        s_lay = QVBoxLayout(self.settings_card)
        s_lay.setContentsMargins(16, 16, 16, 16)
        s_lay.setSpacing(14)

        # Frequency Row
        freq_row = QHBoxLayout()
        freq_row.setSpacing(12)
        lbl_freq = QLabel("Refresh Frequency:")
        lbl_freq.setStyleSheet("font-size: 12px; font-weight: 600; color: #334155; min-width: 130px;")
        freq_row.addWidget(lbl_freq)

        self.combo_frequency = QComboBox()
        self.combo_frequency.addItems(["Daily (Multiple Times of Day)", "Hourly Interval"])
        self.combo_frequency.currentIndexChanged.connect(self._on_frequency_changed)
        freq_row.addWidget(self.combo_frequency, stretch=1)
        s_lay.addLayout(freq_row)

        # Container for Daily Times
        self.daily_container = QWidget()
        d_lay = QVBoxLayout(self.daily_container)
        d_lay.setContentsMargins(0, 0, 0, 0)
        d_lay.setSpacing(10)

        lbl_times_head = QLabel("Time Slots (Local Time):")
        lbl_times_head.setStyleSheet("font-size: 12px; font-weight: 600; color: #334155;")
        d_lay.addWidget(lbl_times_head)

        lbl_times_desc = QLabel(
            "Specify multiple times during the day when validation should execute (up to 8 slots):"
        )
        lbl_times_desc.setStyleSheet("font-size: 11px; color: #64748B;")
        d_lay.addWidget(lbl_times_desc)

        # Scroll Area for times list
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setMaximumHeight(150)
        scroll.setStyleSheet("QScrollArea { border: 1px solid #E2E8F0; border-radius: 6px; background: #F8FAFC; }")

        self.times_list_widget = QWidget()
        self.times_list_widget.setStyleSheet("background: transparent;")
        self.times_list_layout = QVBoxLayout(self.times_list_widget)
        self.times_list_layout.setContentsMargins(8, 8, 8, 8)
        self.times_list_layout.setSpacing(6)
        scroll.setWidget(self.times_list_widget)
        d_lay.addWidget(scroll)

        # Add Time Bar
        add_bar = QHBoxLayout()
        add_bar.setSpacing(8)

        self.combo_add_time = QComboBox()
        self.combo_add_time.addItems(TIME_OPTIONS_30M)
        self.combo_add_time.setCurrentText("09:00")
        add_bar.addWidget(self.combo_add_time, stretch=1)

        self.btn_add_time = QPushButton("+ Add Time")
        self.btn_add_time.setObjectName("SecondaryButton")
        self.btn_add_time.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_add_time.setStyleSheet(
            "QPushButton { font-weight: 600; font-size: 12px; padding: 5px 12px; }"
        )
        self.btn_add_time.clicked.connect(self._add_selected_time)
        add_bar.addWidget(self.btn_add_time)

        d_lay.addLayout(add_bar)
        s_lay.addWidget(self.daily_container)

        # Container for Interval
        self.interval_container = QWidget()
        i_lay = QHBoxLayout(self.interval_container)
        i_lay.setContentsMargins(0, 0, 0, 0)
        i_lay.setSpacing(12)

        lbl_int = QLabel("Execution Interval:")
        lbl_int.setStyleSheet("font-size: 12px; font-weight: 600; color: #334155; min-width: 130px;")
        i_lay.addWidget(lbl_int)

        self.combo_interval = QComboBox()
        self.combo_interval.addItem("Every 1 hour", 60)
        self.combo_interval.addItem("Every 2 hours", 120)
        self.combo_interval.addItem("Every 4 hours (Recommended)", 240)
        self.combo_interval.addItem("Every 6 hours", 360)
        self.combo_interval.addItem("Every 8 hours", 480)
        self.combo_interval.addItem("Every 12 hours", 720)
        self.combo_interval.currentIndexChanged.connect(lambda _: self._update_preview())
        i_lay.addWidget(self.combo_interval, stretch=1)
        s_lay.addWidget(self.interval_container)

        layout.addWidget(self.settings_card)

        # 4. Live Schedule Summary & Next Execution Preview
        self.preview_frame = QFrame()
        self.preview_frame.setStyleSheet(
            "QFrame { background-color: #F8FAFC; border: 1px solid #E2E8F0; border-radius: 8px; padding: 12px; }"
        )
        p_lay = QVBoxLayout(self.preview_frame)
        p_lay.setContentsMargins(6, 6, 6, 6)
        p_lay.setSpacing(4)

        lbl_p_title = QLabel("SCHEDULE PREVIEW")
        lbl_p_title.setStyleSheet("font-size: 10px; font-weight: 700; color: #64748B; letter-spacing: 0.5px;")
        p_lay.addWidget(lbl_p_title)

        self.lbl_preview_summary = QLabel()
        self.lbl_preview_summary.setStyleSheet("font-size: 12px; color: #1E293B; line-height: 1.4;")
        self.lbl_preview_summary.setWordWrap(True)
        p_lay.addWidget(self.lbl_preview_summary)

        self.lbl_preview_next = QLabel()
        self.lbl_preview_next.setStyleSheet("font-size: 12px; font-weight: 700; color: #1668DC;")
        p_lay.addWidget(self.lbl_preview_next)

        layout.addWidget(self.preview_frame)

        # Footer Buttons
        btn_row = QHBoxLayout()
        btn_row.setSpacing(10)

        btn_row.addStretch(1)

        self.btn_cancel = QPushButton("Cancel")
        self.btn_cancel.setObjectName("SecondaryButton")
        self.btn_cancel.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_cancel.clicked.connect(self.reject)
        btn_row.addWidget(self.btn_cancel)

        self.btn_save = QPushButton("Save Schedule")
        self.btn_save.setObjectName("PrimaryButton")
        self.btn_save.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_save.setStyleSheet(
            "background-color: #1668DC; color: #FFFFFF; font-weight: 700; font-size: 13px; "
            "padding: 8px 18px; border-radius: 6px;"
        )
        self.btn_save.clicked.connect(self._save_schedule)
        btn_row.addWidget(self.btn_save)

        layout.addLayout(btn_row)

    def _update_sheet_status_banner(self) -> None:
        """Render whether the sheet satisfies the >= 1 row prerequisite."""
        if self._rule_count > 0:
            self.sheet_status_frame.setStyleSheet(
                "QFrame { background-color: #F0FDF4; border: 1px solid #BBF7D0; border-radius: 6px; }"
            )
            self.lbl_sheet_msg.setText(
                f"Validation Sheet Ready: {self._rule_count} rule(s) configured. "
                "Automated executions will run across all enabled checks."
            )
            self.lbl_sheet_msg.setStyleSheet("font-size: 12px; font-weight: 600; color: #15803D;")
            self.lbl_sheet_icon.setText("✓")
            self.lbl_sheet_icon.setStyleSheet("font-size: 14px; font-weight: 700; color: #15803D;")
        else:
            self.sheet_status_frame.setStyleSheet(
                "QFrame { background-color: #FEF2F2; border: 1px solid #FECACA; border-radius: 6px; }"
            )
            self.lbl_sheet_msg.setText(
                "Validation Sheet Empty: 0 rules configured. "
                "You must add at least one validation rule in the 'Validation Sheet' tab before enabling scheduled runs."
            )
            self.lbl_sheet_msg.setStyleSheet("font-size: 12px; font-weight: 600; color: #B91C1C;")
            self.lbl_sheet_icon.setText("⚠")
            self.lbl_sheet_icon.setStyleSheet("font-size: 14px; font-weight: 700; color: #B91C1C;")

    def _apply_initial_state(self) -> None:
        """Load stored config into the UI widgets."""
        self.chk_enabled.setChecked(self._config.enabled)
        if self._config.mode == "interval":
            self.combo_frequency.setCurrentIndex(1)
        else:
            self.combo_frequency.setCurrentIndex(0)

        # Set interval index if matching
        idx = self.combo_interval.findData(self._config.interval_minutes)
        if idx >= 0:
            self.combo_interval.setCurrentIndex(idx)

        self._render_times_list()
        self._on_enabled_toggled(self.chk_enabled.isChecked())
        self._on_frequency_changed(self.combo_frequency.currentIndex())

        # If 0 rules in sheet, disable master toggle and save
        if self._rule_count == 0:
            self.chk_enabled.setChecked(False)
            self.chk_enabled.setEnabled(False)
            self.btn_save.setEnabled(False)
            self.btn_save.setToolTip("Cannot activate scheduler: Validation Sheet is empty.")

    def _on_enabled_toggled(self, enabled: bool) -> None:
        """Enable or disable scheduling configuration widgets."""
        self.settings_card.setEnabled(enabled)
        self._update_preview()

    def _on_frequency_changed(self, idx: int) -> None:
        """Toggle between Daily multiple times view and Interval view."""
        is_daily = (idx == 0)
        self.daily_container.setVisible(is_daily)
        self.interval_container.setVisible(not is_daily)
        self._update_preview()

    def _render_times_list(self) -> None:
        """Refresh the list of time chips in the UI."""
        # Clear existing items
        while self.times_list_layout.count() > 0:
            item = self.times_list_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        if not self._times:
            lbl_empty = QLabel("No execution times specified. Click '+ Add Time' below.")
            lbl_empty.setStyleSheet("font-size: 11px; color: #94A3B8; font-style: italic;")
            self.times_list_layout.addWidget(lbl_empty)
            return

        for t_str in self._times:
            row = QFrame()
            row.setStyleSheet(
                "QFrame { background-color: #FFFFFF; border: 1px solid #CBD5E1; border-radius: 5px; padding: 3px 6px; }"
            )
            r_lay = QHBoxLayout(row)
            r_lay.setContentsMargins(4, 2, 4, 2)
            r_lay.setSpacing(6)

            lbl_t = QLabel(f"⏰  {t_str}")
            lbl_t.setStyleSheet("font-size: 12px; font-weight: 600; color: #1E293B;")
            r_lay.addWidget(lbl_t)

            r_lay.addStretch(1)

            btn_del = QPushButton("✕")
            btn_del.setFixedSize(18, 18)
            btn_del.setCursor(Qt.CursorShape.PointingHandCursor)
            btn_del.setToolTip(f"Remove {t_str}")
            btn_del.setStyleSheet(
                "QPushButton { border: none; color: #94A3B8; font-size: 11px; font-weight: 700; background: transparent; } "
                "QPushButton:hover { color: #DC2626; }"
            )
            btn_del.clicked.connect(lambda _, t=t_str: self._remove_time(t))
            r_lay.addWidget(btn_del)

            self.times_list_layout.addWidget(row)

        self.btn_add_time.setEnabled(len(self._times) < 8)

    def _add_selected_time(self) -> None:
        """Add the currently selected time from the combo box."""
        t_str = self.combo_add_time.currentText().strip()
        if t_str and t_str not in self._times:
            if len(self._times) >= 8:
                return
            self._times.append(t_str)
            self._times.sort()
            self._render_times_list()
            self._update_preview()

    def _remove_time(self, t_str: str) -> None:
        """Remove a time from the scheduled list."""
        if t_str in self._times:
            self._times.remove(t_str)
            self._render_times_list()
            self._update_preview()

    def _get_current_dialog_config(self) -> ScheduleConfig:
        """Build a ScheduleConfig instance from current UI state."""
        mode = "daily" if self.combo_frequency.currentIndex() == 0 else "interval"
        interval_data = self.combo_interval.currentData()
        interval_mins = int(interval_data) if interval_data is not None else 240

        return ScheduleConfig(
            enabled=self.chk_enabled.isChecked() and self._rule_count > 0,
            mode=mode,
            times=list(self._times),
            interval_minutes=interval_mins,
            last_run_at=self._config.last_run_at,
        )

    def _update_preview(self) -> None:
        """Recalculate and update the live schedule preview."""
        cfg = self._get_current_dialog_config()

        if not cfg.enabled:
            self.lbl_preview_summary.setText("Automated scheduling is currently turned off.")
            self.lbl_preview_next.setText("Next execution: None (Schedule Disabled)")
            self.lbl_preview_next.setStyleSheet("font-size: 12px; font-weight: 600; color: #64748B;")
            return

        if cfg.mode == "daily":
            if not cfg.times:
                self.lbl_preview_summary.setText("Daily schedule enabled, but no execution times are added.")
                self.lbl_preview_next.setText("Next execution: None")
                return
            times_str = ", ".join(cfg.times)
            self.lbl_preview_summary.setText(
                f"Validations will execute automatically across all enabled sheet checks at {times_str} every day."
            )
        else:
            hrs = cfg.interval_minutes / 60.0
            hrs_str = f"{int(hrs)}h" if hrs.is_integer() else f"{hrs:.1f}h"
            self.lbl_preview_summary.setText(
                f"Validations will execute automatically every {hrs_str} in the background."
            )

        nxt = compute_next_run(cfg)
        if nxt:
            disp = format_next_run_display(nxt)
            self.lbl_preview_next.setText(f"Next execution: {disp}")
            self.lbl_preview_next.setStyleSheet("font-size: 12px; font-weight: 700; color: #1668DC;")
        else:
            self.lbl_preview_next.setText("Next execution: Calculating...")

    def _save_schedule(self) -> None:
        """Persist config to scheduler service and close dialog."""
        cfg = self._get_current_dialog_config()
        self._scheduler_service.save_config(cfg)
        self.accept()
