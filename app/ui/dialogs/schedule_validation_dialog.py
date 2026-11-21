"""Power BI-style recurring validation schedule dialog with a green/red toggle switch and grayed-out inactive state."""

from __future__ import annotations

from datetime import datetime, time
import logging

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QBrush, QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
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

TIME_OPTIONS_30M = [f"{h:02d}:{m:02d}" for h in range(24) for m in (0, 30)]


class ToggleSwitch(QCheckBox):
    """Custom graphical ON/OFF toggle switch with green/red indicator pill."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedSize(58, 28)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        checked = self.isChecked()
        enabled = self.isEnabled()

        if not enabled:
            bg_color = QColor("#CBD5E1")
        elif checked:
            bg_color = QColor("#16A34A")  # Vibrant Green when ON
        else:
            bg_color = QColor("#DC2626")  # Vibrant Red when OFF

        # Outer capsule
        p.setBrush(QBrush(bg_color))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawRoundedRect(0, 0, 58, 28, 14, 14)

        # ON / OFF Label
        p.setPen(QPen(QColor("#FFFFFF")))
        font = QFont("Segoe UI", 8, QFont.Weight.Bold)
        p.setFont(font)
        if checked:
            p.drawText(QRectF(8, 0, 26, 28), Qt.AlignmentFlag.AlignCenter, "ON")
            knob_x = 58 - 25
        else:
            p.drawText(QRectF(24, 0, 28, 28), Qt.AlignmentFlag.AlignCenter, "OFF")
            knob_x = 3

        # Circular sliding knob
        p.setBrush(QBrush(QColor("#FFFFFF")))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawEllipse(knob_x, 3, 22, 22)
        p.end()


class ScheduleValidationDialog(QDialog):
    """Refined dialog configuring recurring validation runs inspired by Power BI Scheduled Refresh."""

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
        self.setMinimumWidth(720)
        self.resize(740, 470)

        self._build_ui()
        self._apply_initial_state()
        self._update_preview()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(14)

        # 1. Header Row (Title on Left, Sheet Status Pill on Right)
        header_row = QHBoxLayout()
        header_row.setSpacing(12)

        title_box = QVBoxLayout()
        title_box.setSpacing(2)
        lbl_title = QLabel("Automated Validation Scheduler")
        lbl_title.setStyleSheet("font-size: 17px; font-weight: 700; color: #0F172A;")
        title_box.addWidget(lbl_title)

        lbl_sub = QLabel(
            "Automatically evaluate all enabled checks from your Validation Sheet on a recurring schedule."
        )
        lbl_sub.setWordWrap(True)
        lbl_sub.setStyleSheet("font-size: 12px; color: #64748B;")
        title_box.addWidget(lbl_sub)
        header_row.addLayout(title_box, stretch=1)

        # Sheet Status Pill (Top-Right)
        self.sheet_status_frame = QFrame()
        self.sheet_status_layout = QHBoxLayout(self.sheet_status_frame)
        self.sheet_status_layout.setContentsMargins(8, 5, 10, 5)
        self.sheet_status_layout.setSpacing(6)

        self.lbl_sheet_icon = QLabel()
        self.sheet_status_layout.addWidget(self.lbl_sheet_icon)

        self.lbl_sheet_msg = QLabel()
        self.sheet_status_layout.addWidget(self.lbl_sheet_msg)
        header_row.addWidget(self.sheet_status_frame, alignment=Qt.AlignmentFlag.AlignTop)

        layout.addLayout(header_row)
        self._update_sheet_status_banner()

        # 2. Master Toggle Row (Green/Red ON-OFF Switch)
        self.toggle_card = QFrame()
        self.toggle_card.setStyleSheet(
            "QFrame { background-color: #FFFFFF; border: 1px solid #E2E8F0; border-radius: 7px; padding: 6px 12px; }"
        )
        t_lay = QHBoxLayout(self.toggle_card)
        t_lay.setContentsMargins(2, 2, 2, 2)
        t_lay.setSpacing(12)

        self.chk_enabled = ToggleSwitch()
        self.chk_enabled.toggled.connect(self._on_enabled_toggled)
        t_lay.addWidget(self.chk_enabled)

        lbl_toggle_title = QLabel("Keep your validations up to date")
        lbl_toggle_title.setStyleSheet("font-size: 13px; font-weight: 700; color: #0F172A;")
        lbl_toggle_title.setCursor(Qt.CursorShape.PointingHandCursor)
        lbl_toggle_title.mousePressEvent = lambda _: self.chk_enabled.toggle()
        t_lay.addWidget(lbl_toggle_title)

        lbl_toggle_sub = QLabel("(Executes in the background without requiring manual clicks)")
        lbl_toggle_sub.setStyleSheet("font-size: 11px; color: #64748B;")
        t_lay.addWidget(lbl_toggle_sub)
        t_lay.addStretch(1)

        layout.addWidget(self.toggle_card)

        # 3. Schedule Settings Card
        self.settings_card = QFrame()
        self.settings_card.setObjectName("SettingsCard")
        s_lay = QVBoxLayout(self.settings_card)
        s_lay.setContentsMargins(16, 14, 16, 14)
        s_lay.setSpacing(12)

        # Control Row: Frequency + Add Time Action (Side by Side)
        ctrl_row = QHBoxLayout()
        ctrl_row.setSpacing(14)

        self.lbl_freq = QLabel("Frequency:")
        self.lbl_freq.setStyleSheet("font-size: 12px; font-weight: 600; color: #334155;")
        ctrl_row.addWidget(self.lbl_freq)

        self.combo_frequency = QComboBox()
        self.combo_frequency.addItems(["Daily (Multiple Times of Day)", "Hourly Interval"])
        self.combo_frequency.currentIndexChanged.connect(self._on_frequency_changed)
        ctrl_row.addWidget(self.combo_frequency)

        # Daily-specific Add Time tools
        self.add_time_box = QWidget()
        a_lay = QHBoxLayout(self.add_time_box)
        a_lay.setContentsMargins(0, 0, 0, 0)
        a_lay.setSpacing(8)

        self.lbl_add = QLabel("Add Time:")
        self.lbl_add.setStyleSheet("font-size: 12px; font-weight: 600; color: #334155; margin-left: 10px;")
        a_lay.addWidget(self.lbl_add)

        self.combo_add_time = QComboBox()
        self.combo_add_time.addItems(TIME_OPTIONS_30M)
        self.combo_add_time.setCurrentText("09:00")
        self.combo_add_time.setMinimumWidth(85)
        a_lay.addWidget(self.combo_add_time)

        self.btn_add_time = QPushButton("+ Add Time")
        self.btn_add_time.setObjectName("SecondaryButton")
        self.btn_add_time.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_add_time.setStyleSheet("font-weight: 600; font-size: 12px; padding: 4px 10px;")
        self.btn_add_time.clicked.connect(self._add_selected_time)
        a_lay.addWidget(self.btn_add_time)

        ctrl_row.addWidget(self.add_time_box)
        ctrl_row.addStretch(1)

        # Interval-specific selector
        self.interval_box = QWidget()
        i_lay = QHBoxLayout(self.interval_box)
        i_lay.setContentsMargins(0, 0, 0, 0)
        i_lay.setSpacing(8)

        self.lbl_int = QLabel("Interval:")
        self.lbl_int.setStyleSheet("font-size: 12px; font-weight: 600; color: #334155; margin-left: 10px;")
        i_lay.addWidget(self.lbl_int)

        self.combo_interval = QComboBox()
        self.combo_interval.addItem("Every 1 hour", 60)
        self.combo_interval.addItem("Every 2 hours", 120)
        self.combo_interval.addItem("Every 4 hours (Recommended)", 240)
        self.combo_interval.addItem("Every 6 hours", 360)
        self.combo_interval.addItem("Every 8 hours", 480)
        self.combo_interval.addItem("Every 12 hours", 720)
        self.combo_interval.currentIndexChanged.connect(lambda _: self._update_preview())
        i_lay.addWidget(self.combo_interval)

        ctrl_row.addWidget(self.interval_box)

        s_lay.addLayout(ctrl_row)

        # Time Chips Area (Daily Mode)
        self.daily_container = QWidget()
        d_lay = QVBoxLayout(self.daily_container)
        d_lay.setContentsMargins(0, 0, 0, 0)
        d_lay.setSpacing(6)

        self.chips_card = QFrame()
        self.chips_grid = QGridLayout(self.chips_card)
        self.chips_grid.setContentsMargins(2, 2, 2, 2)
        self.chips_grid.setSpacing(8)
        d_lay.addWidget(self.chips_card)

        s_lay.addWidget(self.daily_container)
        layout.addWidget(self.settings_card)

        # 4. Schedule Preview Banner
        self.preview_frame = QFrame()
        p_lay = QVBoxLayout(self.preview_frame)
        p_lay.setContentsMargins(0, 0, 0, 0)
        p_lay.setSpacing(4)

        self.lbl_preview_summary = QLabel()
        self.lbl_preview_summary.setWordWrap(True)
        p_lay.addWidget(self.lbl_preview_summary)

        self.lbl_preview_next = QLabel()
        p_lay.addWidget(self.lbl_preview_next)

        layout.addWidget(self.preview_frame)

        # 5. Footer Buttons
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
            "padding: 7px 20px; border-radius: 6px;"
        )
        self.btn_save.clicked.connect(self._save_schedule)
        btn_row.addWidget(self.btn_save)

        layout.addLayout(btn_row)

    def _update_sheet_status_banner(self) -> None:
        """Render whether the sheet satisfies the >= 1 row prerequisite."""
        if self._rule_count > 0:
            self.sheet_status_frame.setStyleSheet(
                "QFrame { background-color: #DCFCE7; border: 1px solid #BBF7D0; border-radius: 6px; padding: 4px 10px; }"
            )
            self.lbl_sheet_msg.setText(f"{self._rule_count} rule(s) configured")
            self.lbl_sheet_msg.setStyleSheet("font-size: 11px; font-weight: 600; color: #15803D;")
            self.lbl_sheet_icon.setText("✓")
            self.lbl_sheet_icon.setStyleSheet("font-size: 12px; font-weight: 700; color: #15803D;")
            self.sheet_status_frame.setToolTip(
                f"Validation Sheet Ready: {self._rule_count} active rule(s). "
                "Automated executions will evaluate all enabled checks."
            )
        else:
            self.sheet_status_frame.setStyleSheet(
                "QFrame { background-color: #FEE2E2; border: 1px solid #FECACA; border-radius: 6px; padding: 4px 10px; }"
            )
            self.lbl_sheet_msg.setText("0 rules configured")
            self.lbl_sheet_msg.setStyleSheet("font-size: 11px; font-weight: 600; color: #B91C1C;")
            self.lbl_sheet_icon.setText("⚠")
            self.lbl_sheet_icon.setStyleSheet("font-size: 12px; font-weight: 700; color: #B91C1C;")
            self.sheet_status_frame.setToolTip(
                "Validation Sheet Empty: 0 rules configured. "
                "You must add at least one validation rule in the 'Validation Sheet' tab before enabling scheduled runs."
            )

    def _apply_initial_state(self) -> None:
        """Load stored config into the UI widgets."""
        self.chk_enabled.setChecked(self._config.enabled)
        if self._config.mode == "interval":
            self.combo_frequency.setCurrentIndex(1)
        else:
            self.combo_frequency.setCurrentIndex(0)

        idx = self.combo_interval.findData(self._config.interval_minutes)
        if idx >= 0:
            self.combo_interval.setCurrentIndex(idx)

        self._render_times_list()
        self._on_enabled_toggled(self.chk_enabled.isChecked())
        self._on_frequency_changed(self.combo_frequency.currentIndex())

        if self._rule_count == 0:
            self.chk_enabled.setChecked(False)
            self.chk_enabled.setEnabled(False)
            self.btn_save.setEnabled(False)
            self.btn_save.setToolTip("Cannot activate scheduler: Validation Sheet is empty.")

    def _on_enabled_toggled(self, enabled: bool) -> None:
        """Enable or disable scheduling configuration widgets and style them in gray when OFF."""
        self.settings_card.setEnabled(enabled)

        if enabled:
            # Active enterprise styling (Crisp white card, slate labels, blue preview accent)
            self.settings_card.setStyleSheet(
                "QFrame#SettingsCard { background-color: #FFFFFF; border: 1px solid #E2E8F0; border-radius: 8px; } "
                "QLabel { color: #334155; font-size: 12px; font-weight: 600; }"
            )
            self.chips_card.setStyleSheet(
                "QFrame { background-color: #F8FAFC; border: 1px solid #E2E8F0; border-radius: 6px; padding: 6px 10px; }"
            )
            self.preview_frame.setStyleSheet(
                "QFrame { background-color: #F8FAFC; border: 1px solid #E2E8F0; "
                "border-left: 4px solid #1668DC; border-radius: 6px; padding: 10px 14px; } "
                "QLabel { background: transparent; border: none; }"
            )
            self.lbl_preview_summary.setStyleSheet("font-size: 12px; color: #1E293B;")
            self.lbl_preview_next.setStyleSheet("font-size: 12px; font-weight: 700; color: #1668DC;")
        else:
            # Disabled / Inactive grayed-out styling
            self.settings_card.setStyleSheet(
                "QFrame#SettingsCard { background-color: #F1F5F9; border: 1px solid #CBD5E1; border-radius: 8px; } "
                "QLabel { color: #94A3B8; font-size: 12px; font-weight: 600; } "
                "QComboBox { background-color: #E2E8F0; color: #94A3B8; border-color: #CBD5E1; } "
                "QPushButton { background-color: #E2E8F0; color: #94A3B8; border-color: #CBD5E1; }"
            )
            self.chips_card.setStyleSheet(
                "QFrame { background-color: #E2E8F0; border: 1px solid #CBD5E1; border-radius: 6px; padding: 6px 10px; }"
            )
            self.preview_frame.setStyleSheet(
                "QFrame { background-color: #F1F5F9; border: 1px solid #CBD5E1; "
                "border-left: 4px solid #94A3B8; border-radius: 6px; padding: 10px 14px; } "
                "QLabel { background: transparent; border: none; color: #94A3B8; }"
            )
            self.lbl_preview_summary.setStyleSheet("font-size: 12px; color: #94A3B8;")
            self.lbl_preview_next.setStyleSheet("font-size: 12px; font-weight: 600; color: #94A3B8;")

        self._render_times_list()
        self._update_preview()
        self.chk_enabled.update()

    def _on_frequency_changed(self, idx: int) -> None:
        """Toggle between Daily multiple times view and Interval view."""
        is_daily = (idx == 0)
        self.daily_container.setVisible(is_daily)
        self.add_time_box.setVisible(is_daily)
        self.interval_box.setVisible(not is_daily)
        self._update_preview()

    def _render_times_list(self) -> None:
        """Refresh the interactive time chips in a clean grid."""
        while self.chips_grid.count() > 0:
            item = self.chips_grid.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        enabled = self.chk_enabled.isChecked()

        if not self._times:
            lbl_empty = QLabel("No execution times specified. Pick a time above and click '+ Add Time'.")
            lbl_empty.setStyleSheet("font-size: 11px; color: #94A3B8; font-style: italic; padding: 4px;")
            self.chips_grid.addWidget(lbl_empty, 0, 0, 1, 4)
            return

        cols_per_row = 4
        for idx, t_str in enumerate(self._times):
            row_idx = idx // cols_per_row
            col_idx = idx % cols_per_row

            chip = QFrame()
            if enabled:
                chip.setStyleSheet(
                    "QFrame { background-color: #FFFFFF; border: 1px solid #CBD5E1; "
                    "border-radius: 14px; padding: 2px 8px; } "
                    "QFrame:hover { border-color: #94A3B8; } "
                    "QLabel { background: transparent; border: none; color: #1E293B; }"
                )
            else:
                chip.setStyleSheet(
                    "QFrame { background-color: #F1F5F9; border: 1px solid #CBD5E1; "
                    "border-radius: 14px; padding: 2px 8px; } "
                    "QLabel { background: transparent; border: none; color: #94A3B8; }"
                )

            ch_lay = QHBoxLayout(chip)
            ch_lay.setContentsMargins(6, 2, 4, 2)
            ch_lay.setSpacing(6)

            lbl_t = QLabel(f"⏰  {t_str}")
            lbl_t.setStyleSheet(f"font-size: 12px; font-weight: 600; color: {'#1E293B' if enabled else '#94A3B8'};")
            ch_lay.addWidget(lbl_t)

            btn_del = QPushButton("✕")
            btn_del.setFixedSize(14, 14)
            btn_del.setCursor(Qt.CursorShape.PointingHandCursor if enabled else Qt.CursorShape.ArrowCursor)
            btn_del.setEnabled(enabled)
            btn_del.setToolTip(f"Remove {t_str}")
            btn_del.setStyleSheet(
                "QPushButton { border: none; color: #94A3B8; font-size: 10px; font-weight: 700; background: transparent; } "
                f"QPushButton:hover {{ color: {'#DC2626' if enabled else '#94A3B8'}; }}"
            )
            btn_del.clicked.connect(lambda _, t=t_str: self._remove_time(t))
            ch_lay.addWidget(btn_del)

            self.chips_grid.addWidget(chip, row_idx, col_idx)

        current_cols = min(len(self._times), cols_per_row)
        for c in range(cols_per_row):
            self.chips_grid.setColumnStretch(c, 1 if c < current_cols else 0)

        self.btn_add_time.setEnabled(enabled and len(self._times) < 8)

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
            self.lbl_preview_next.setStyleSheet("font-size: 12px; font-weight: 600; color: #94A3B8;")
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
