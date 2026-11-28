"""Power BI-style recurring validation schedule dialog with a accessible toggle switch and grayed-out inactive state."""

from __future__ import annotations

from datetime import datetime
import logging
from typing import Any

from PySide6.QtCore import Qt, QTime
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QSpinBox,
    QTimeEdit,
    QVBoxLayout,
    QWidget,
)

from app.services.scheduler_service import (
    ScheduleConfig,
    ValidationSchedulerService,
    compute_next_run,
    format_next_run_display,
)

from app.ui.widgets.enterprise import EnterpriseDialog, ToggleSwitch

logger = logging.getLogger(__name__)

class ScheduleValidationDialog(EnterpriseDialog):
    """Refined dialog configuring recurring validation runs inspired by Power BI Scheduled Refresh."""

    def __init__(
        self,
        scheduler_service: ValidationSchedulerService,
        rule_count: int = 0,
        teams_service: Any | None = None,
        account: Any | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._scheduler_service = scheduler_service
        self._rule_count = rule_count
        self._teams_service = teams_service
        self._account = account
        self._config = scheduler_service.config

        # Working list of times (sorted)
        self._times: list[str] = list(self._config.times)
        self._times.sort()

        self.setWindowTitle("Schedule Automated Validations")
        self.setMinimumWidth(720)
        self.resize(740, 500)

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
        lbl_title = QLabel("Schedule validations")
        lbl_title.setStyleSheet("font-size: 17px; font-weight: 700; color: #16243A;")
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
        self.toggle_card.setCursor(Qt.CursorShape.PointingHandCursor)
        self.toggle_card.setStyleSheet(
            "QFrame { background-color: #FFFFFF; border: 1px solid #DDE4ED; border-radius: 7px; padding: 6px 12px; } "
            "QFrame:hover { border-color: #CBD5E1; }"
        )
        t_lay = QHBoxLayout(self.toggle_card)
        t_lay.setContentsMargins(2, 2, 2, 2)
        t_lay.setSpacing(12)

        self.chk_enabled = ToggleSwitch()
        self.chk_enabled.toggled.connect(self._on_enabled_toggled)
        t_lay.addWidget(self.chk_enabled)

        lbl_toggle_title = QLabel("Run enabled checks automatically")
        lbl_toggle_title.setStyleSheet("font-size: 13px; font-weight: 700; color: #16243A;")
        lbl_toggle_title.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        t_lay.addWidget(lbl_toggle_title)

        lbl_toggle_sub = QLabel("(Executes in the background without requiring manual clicks)")
        lbl_toggle_sub.setStyleSheet("font-size: 11px; color: #64748B;")
        lbl_toggle_sub.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        lbl_toggle_sub.hide()
        t_lay.addStretch(1)

        self.toggle_card.mousePressEvent = self._on_toggle_card_clicked
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
        self.combo_frequency.addItems(["Daily times", "Repeat interval"])
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

        self.time_input = QTimeEdit(QTime.currentTime().addSecs(300))
        self.time_input.setDisplayFormat("HH:mm")
        self.time_input.setMinimumWidth(90)
        self.time_input.setToolTip("Enter any local time from 00:00 to 23:59, to the minute.")
        a_lay.addWidget(self.time_input)

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

        self.spin_interval = QSpinBox()
        self.spin_interval.setRange(1, 10080)
        self.spin_interval.setSuffix(" minutes")
        self.spin_interval.setValue(240)
        self.spin_interval.setToolTip("Repeat every 1 to 10,080 minutes (up to 7 days).")
        self.spin_interval.valueChanged.connect(lambda _: self._update_preview())
        i_lay.addWidget(self.spin_interval)

        ctrl_row.addWidget(self.interval_box)

        s_lay.addLayout(ctrl_row)

        # Time Chips Area (Daily Mode)
        self.daily_container = QWidget()
        d_lay = QVBoxLayout(self.daily_container)
        d_lay.setContentsMargins(0, 0, 0, 0)
        d_lay.setSpacing(6)

        self.chips_card = QFrame()
        self.chips_card.setObjectName("ChipsCard")
        self.chips_grid = QGridLayout(self.chips_card)
        self.chips_grid.setContentsMargins(10, 8, 10, 8)
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
        self.lbl_preview_next.setWordWrap(True)
        self.lbl_preview_reason = QLabel()
        self.lbl_preview_reason.setWordWrap(True)
        self.lbl_preview_reason.setStyleSheet("font-size: 12px; color: #526278;")
        p_lay.addWidget(self.lbl_preview_reason)

        layout.addWidget(self.preview_frame)

        local_now = datetime.now().astimezone()
        offset = local_now.strftime("%z")
        zone_label = f"{local_now.tzname()} (UTC{offset[:3]}:{offset[3:]})"
        self.lbl_timezone = QLabel(f"Schedule time zone: {zone_label}. Keep the app open for scheduled runs.")
        self.lbl_timezone.setWordWrap(True)
        self.lbl_timezone.setStyleSheet("font-size: 11px; color: #64748B;")
        layout.addWidget(self.lbl_timezone)

        # 6. Footer Buttons
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
            "background-color: #2563EB; color: #FFFFFF; font-weight: 700; font-size: 13px; "
            "padding: 7px 20px; border-radius: 6px;"
        )
        self.btn_save.clicked.connect(self._save_schedule)
        btn_row.addWidget(self.btn_save)

        layout.addLayout(btn_row)

    def _open_teams_config(self) -> None:
        """Open the Teams alert configuration dialog from within the scheduler."""
        if self._teams_service is None:
            return
        from app.ui.dialogs.teams_alert_dialog import TeamsAlertConfigDialog

        dlg = TeamsAlertConfigDialog(
            teams_service=self._teams_service,
            account=self._account,
            parent=self,
        )
        if dlg.exec():
            if hasattr(self, "lbl_teams_info"):
                self.lbl_teams_info.setText(f"🔔  Microsoft Teams Alerts: {self._teams_service.get_status_text()}")

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

        self.spin_interval.setValue(self._config.interval_minutes)

        self._render_times_list()
        self._on_enabled_toggled(self.chk_enabled.isChecked())
        self._on_frequency_changed(self.combo_frequency.currentIndex())

        if self._rule_count == 0:
            self.chk_enabled.setChecked(False)
            self.chk_enabled.setEnabled(False)
            self.toggle_card.setCursor(Qt.CursorShape.ArrowCursor)
            self.btn_save.setEnabled(False)
            self.btn_save.setToolTip("Cannot activate scheduler: Validation Sheet is empty.")

    def _on_toggle_card_clicked(self, event) -> None:
        """Handle clicks on the master toggle card rectangle."""
        if event.button() == Qt.MouseButton.LeftButton and self.chk_enabled.isEnabled():
            self.chk_enabled.toggle()
        event.accept()

    def _on_enabled_toggled(self, enabled: bool) -> None:
        """Enable or disable scheduling configuration widgets and style them in gray when OFF."""
        self.settings_card.setEnabled(enabled)

        if enabled:
            # Active enterprise styling (Crisp white card, slate labels, blue preview accent)
            self.settings_card.setStyleSheet(
                "QFrame#SettingsCard { background-color: #FFFFFF; border: 1px solid #DDE4ED; border-radius: 8px; } "
                "QLabel { color: #334155; font-size: 12px; font-weight: 600; }"
            )
            self.chips_card.setStyleSheet(
                "QFrame#ChipsCard { background-color: #F8FAFC; border: 1px solid #DDE4ED; border-radius: 6px; }"
            )
            self.preview_frame.setStyleSheet(
                "QFrame { background-color: #F8FAFC; border: 1px solid #DDE4ED; "
                "border-left: 4px solid #2563EB; border-radius: 6px; padding: 10px 14px; } "
                "QLabel { background: transparent; border: none; }"
            )
            self.lbl_preview_summary.setStyleSheet("font-size: 12px; color: #1E293B;")
            self.lbl_preview_next.setStyleSheet("font-size: 12px; font-weight: 700; color: #2563EB;")
        else:
            # Disabled / Inactive grayed-out styling
            self.settings_card.setStyleSheet(
                "QFrame#SettingsCard { background-color: #F1F5F9; border: 1px solid #CBD5E1; border-radius: 8px; } "
                "QLabel { color: #94A3B8; font-size: 12px; font-weight: 600; } "
                "QComboBox, QTimeEdit, QSpinBox { background-color: #E2E8F0; color: #94A3B8; border-color: #CBD5E1; } "
                "QPushButton { background-color: #DDE4ED; color: #94A3B8; border-color: #CBD5E1; }"
            )
            self.chips_card.setStyleSheet(
                "QFrame#ChipsCard { background-color: #E2E8F0; border: 1px solid #CBD5E1; border-radius: 6px; }"
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
            w = item.widget()
            if w is not None:
                w.hide()
                w.setParent(None)
                w.deleteLater()

        enabled = self.chk_enabled.isChecked()

        if not self._times:
            lbl_empty = QLabel("No execution times specified. Pick a time above and click '+ Add Time'.")
            lbl_empty.setStyleSheet("font-size: 11px; color: #94A3B8; font-style: italic; padding: 4px;")
            self.chips_grid.addWidget(lbl_empty, 0, 0, 1, 6)
            return

        cols_per_row = 6
        for idx, t_str in enumerate(self._times):
            row_idx = idx // cols_per_row
            col_idx = idx % cols_per_row

            chip = QFrame()
            chip.setObjectName("TimeChip")
            chip.setFixedHeight(28)
            chip.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
            if enabled:
                chip.setStyleSheet(
                    "QFrame#TimeChip { background-color: #FFFFFF; border: 1px solid #CBD5E1; "
                    "border-radius: 14px; } "
                    "QFrame#TimeChip:hover { border-color: #94A3B8; } "
                    "QLabel { background: transparent; border: none; color: #1E293B; }"
                )
            else:
                chip.setStyleSheet(
                    "QFrame#TimeChip { background-color: #F1F5F9; border: 1px solid #CBD5E1; "
                    "border-radius: 14px; } "
                    "QLabel { background: transparent; border: none; color: #94A3B8; }"
                )

            ch_lay = QHBoxLayout(chip)
            ch_lay.setContentsMargins(10, 2, 8, 2)
            ch_lay.setSpacing(6)

            lbl_t = QLabel(t_str)
            lbl_t.setStyleSheet(f"font-size: 12px; font-weight: 600; color: {'#1E293B' if enabled else '#94A3B8'};")
            ch_lay.addWidget(lbl_t)

            btn_del = QPushButton("✕")
            btn_del.setFixedSize(16, 16)
            btn_del.setCursor(Qt.CursorShape.PointingHandCursor if enabled else Qt.CursorShape.ArrowCursor)
            btn_del.setEnabled(enabled)
            btn_del.setToolTip(f"Remove {t_str}")
            btn_del.setStyleSheet(
                "QPushButton { border: none; color: #94A3B8; font-size: 10px; font-weight: 700; background: transparent; padding: 0px; } "
                f"QPushButton:hover {{ color: {'#DC2626' if enabled else '#94A3B8'}; }}"
            )
            btn_del.clicked.connect(lambda _, t=t_str: self._remove_time(t))
            ch_lay.addWidget(btn_del)

            self.chips_grid.addWidget(chip, row_idx, col_idx, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)

        for c in range(cols_per_row):
            self.chips_grid.setColumnStretch(c, 0)
        self.chips_grid.setColumnStretch(cols_per_row, 1)

        self.btn_add_time.setEnabled(enabled and len(self._times) < 8)

    def _add_selected_time(self) -> None:
        """Add an exact local time, without restricting minutes to preset slots."""
        self.time_input.interpretText()
        t_str = self.time_input.time().toString("HH:mm")
        if t_str in self._times:
            self.lbl_preview_reason.setText(f"{t_str} is already in your daily schedule. Choose a different time to add another run.")
            return
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
        interval_mins = self.spin_interval.value()

        return ScheduleConfig(
            enabled=self.chk_enabled.isChecked() and self._rule_count > 0,
            mode=mode,
            times=list(self._times),
            interval_minutes=interval_mins,
            last_run_at=self._config.last_run_at,
        )

    def _update_preview(self, current_dt: datetime | None = None) -> None:
        """Recalculate and update the live schedule preview."""
        cfg = self._get_current_dialog_config()
        now = current_dt or datetime.now()
        self.lbl_preview_reason.clear()
        self.btn_save.setEnabled(
            self._rule_count > 0 and (not cfg.enabled or cfg.mode != "daily" or bool(cfg.times))
        )

        if not cfg.enabled:
            self.lbl_preview_summary.setText("Automated scheduling is currently turned off.")
            self.lbl_preview_next.setText("Next execution: None (Schedule Disabled)")
            self.lbl_preview_reason.setText("Turn on scheduling, choose when to run, then save. You can still run checks manually from Overview.")
            self.lbl_preview_next.setStyleSheet("font-size: 12px; font-weight: 600; color: #94A3B8;")
            return

        if cfg.mode == "daily":
            if not cfg.times:
                self.lbl_preview_summary.setText("Daily schedule enabled, but no execution times are added.")
                self.lbl_preview_next.setText("Next execution: None")
                self.lbl_preview_reason.setText("Choose a time above and click Add Time. Saving is unavailable until a daily time is added.")
                return
            times_str = ", ".join(cfg.times)
            self.lbl_preview_summary.setText(
                f"Daily at {times_str}, using this computer's local time. All enabled checks will run."
            )
        else:
            hours, minutes = divmod(cfg.interval_minutes, 60)
            interval_str = f"{hours}h {minutes}m" if hours else f"{minutes}m"
            self.lbl_preview_summary.setText(
                f"Validations will execute automatically every {interval_str} in the background."
            )

        nxt = compute_next_run(cfg, now)
        if nxt:
            day = "Today" if nxt.date() == now.date() else "Tomorrow" if (nxt.date() - now.date()).days == 1 else nxt.strftime("%A")
            self.lbl_preview_next.setText(f"Next run: {day}, {nxt.strftime('%d %b %Y at %H:%M')} · Local time")
            if cfg.mode == "daily" and nxt.date() > now.date():
                self.lbl_preview_reason.setText(
                    f"Today's selected times have already passed. The daily schedule continues tomorrow. "
                    f"To run today, add a time later than {now:%H:%M}, or use Run all enabled checks in Overview."
                )
            elif cfg.mode == "daily":
                self.lbl_preview_reason.setText("This time is still ahead today. The same selected times repeat every day while the app is open.")
            else:
                self.lbl_preview_reason.setText("The interval repeats from the last recorded run. Keep the app open for scheduled checks.")
            self.lbl_preview_next.setStyleSheet("font-size: 12px; font-weight: 700; color: #2563EB;")
        else:
            self.lbl_preview_next.setText("Next execution: Calculating...")

    def _save_schedule(self) -> None:
        """Persist config to scheduler service and close dialog."""
        cfg = self._get_current_dialog_config()
        if cfg.enabled and cfg.mode == "daily" and not cfg.times:
            return
        self._scheduler_service.save_config(cfg)
        self.accept()
