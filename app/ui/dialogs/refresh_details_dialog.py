"""Dialog displaying Power BI dataset refresh execution history, diagnostics, and KPIs (Stage 8)."""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import (
    QDialog,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QScrollArea,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from app.core.status import NotificationLevel, RefreshStatus
from app.services.refresh_service import RefreshRecordDTO, RefreshService, RefreshSummaryDTO
from app.ui.widgets.notification_banner import NotificationBanner

logger = logging.getLogger(__name__)


def make_status_pill(status: RefreshStatus | str) -> QLabel:
    """Create a styled visual pill label for refresh status."""
    val = status.value if isinstance(status, RefreshStatus) else str(status)
    val_lower = val.lower()

    if val_lower in ("completed", "success"):
        bg = "#ECFDF5"
        text_color = "#065F46"
        border = "#A7F3D0"
        label_text = "Completed"
    elif val_lower in ("failed", "failure", "error"):
        bg = "#FEF2F2"
        text_color = "#991B1B"
        border = "#FECACA"
        label_text = "Failed"
    elif val_lower in ("inprogress", "in progress", "running"):
        bg = "#EFF6FF"
        text_color = "#1D4ED8"
        border = "#BFDBFE"
        label_text = "In Progress"
    elif val_lower in ("disabled",):
        bg = "#FFFBEB"
        text_color = "#92400E"
        border = "#FDE68A"
        label_text = "Disabled"
    else:
        bg = "#F1F5F9"
        text_color = "#475569"
        border = "#CBD5E1"
        label_text = val.capitalize()

    lbl = QLabel(f" {label_text} ")
    lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
    lbl.setStyleSheet(
        f"background-color: {bg}; color: {text_color}; border: 1px solid {border}; "
        f"border-radius: 10px; font-size: 11px; font-weight: 700; padding: 2px 8px;"
    )
    return lbl


def update_refresh_status_pill(pill: QLabel, status: RefreshStatus | str) -> None:
    """Update text and styling on an existing refresh status pill in place."""
    val = status.value if isinstance(status, RefreshStatus) else str(status)
    val_lower = val.lower()

    if val_lower in ("completed", "success"):
        bg = "#ECFDF5"
        text_color = "#065F46"
        border = "#A7F3D0"
        label_text = "Completed"
    elif val_lower in ("failed", "failure", "error"):
        bg = "#FEF2F2"
        text_color = "#991B1B"
        border = "#FECACA"
        label_text = "Failed"
    elif val_lower in ("inprogress", "in progress", "running"):
        bg = "#EFF6FF"
        text_color = "#1D4ED8"
        border = "#BFDBFE"
        label_text = "In Progress"
    elif val_lower in ("disabled",):
        bg = "#FFFBEB"
        text_color = "#92400E"
        border = "#FDE68A"
        label_text = "Disabled"
    else:
        bg = "#F1F5F9"
        text_color = "#475569"
        border = "#CBD5E1"
        label_text = val.capitalize()

    pill.setText(f" {label_text} ")
    pill.setStyleSheet(
        f"background-color: {bg}; color: {text_color}; border: 1px solid {border}; "
        f"border-radius: 10px; font-size: 11px; font-weight: 700; padding: 2px 8px;"
    )


def make_refresh_status_table_item(status: RefreshStatus | str) -> QTableWidgetItem:
    """Create a crisp, bold, colorful table item for refresh status without widget shrink."""
    val = status.value if isinstance(status, RefreshStatus) else str(status)
    val_lower = val.lower()

    if val_lower in ("completed", "success"):
        label_text = "Completed"
        fg = "#15803D"
        bg = "#DCFCE7"
    elif val_lower in ("failed", "failure", "error"):
        label_text = "Failed"
        fg = "#B91C1C"
        bg = "#FEE2E2"
    elif val_lower in ("inprogress", "in progress", "running"):
        label_text = "In Progress"
        fg = "#1D4ED8"
        bg = "#DBEAFE"
    elif val_lower in ("disabled",):
        label_text = "Disabled"
        fg = "#B45309"
        bg = "#FEF3C7"
    else:
        label_text = val.capitalize()
        fg = "#475569"
        bg = "#F1F5F9"

    item = QTableWidgetItem(label_text)
    item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
    font = item.font()
    font.setBold(True)
    font.setPointSize(10)
    item.setFont(font)
    item.setForeground(QColor(fg))
    item.setBackground(QColor(bg))
    return item


class RefreshDetailsDialog(QDialog):
    """Interactive modal showing full dataset refresh history, KPI summaries, and diagnostics."""

    def __init__(
        self,
        *,
        workspace_registration_id: int,
        workspace_id: str,
        dataset_id: str,
        registration_display_name: str,
        refresh_service: RefreshService,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._reg_id = workspace_registration_id
        self._workspace_id = workspace_id
        self._dataset_id = dataset_id
        self._display_name = registration_display_name
        self._service = refresh_service
        self._records: list[RefreshRecordDTO] = []

        self.setWindowTitle("Power BI Dataset Refresh History & Diagnostics")
        self.setModal(True)
        self.resize(920, 680)
        self.setMinimumSize(800, 560)
        self.setObjectName("ConfirmDialog")

        self._init_ui()
        self._connect_signals()
        self._load_data()

    def _init_ui(self) -> None:
        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(24, 20, 24, 20)
        root_layout.setSpacing(14)

        # 1. Header with title and Live Fetch button
        header_row = QHBoxLayout()
        header_row.setSpacing(12)

        title_block = QVBoxLayout()
        title_block.setSpacing(3)
        title_lbl = QLabel("Dataset Refresh History & Diagnostics")
        title_lbl.setObjectName("DialogTitle")
        title_block.addWidget(title_lbl)

        sub_text = (
            f"Dataset: {self._display_name}  •  Reg #{self._reg_id}  •  "
            f"Workspace: {self._workspace_id}  •  Model ID: {self._dataset_id}"
        )
        sub_lbl = QLabel(sub_text)
        sub_lbl.setObjectName("PageSubtitle")
        sub_lbl.setWordWrap(True)
        title_block.addWidget(sub_lbl)
        header_row.addLayout(title_block, stretch=1)

        self.fetch_button = QPushButton("↻  Fetch Live Power BI History")
        self.fetch_button.setObjectName("PrimaryButton")
        self.fetch_button.setStyleSheet(
            "background-color: #1668DC; color: #FFFFFF; font-weight: 600; padding: 8px 16px; border-radius: 6px;"
        )
        self.fetch_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.fetch_button.clicked.connect(self._handle_fetch_live)
        header_row.addWidget(self.fetch_button, alignment=Qt.AlignmentFlag.AlignTop)

        root_layout.addLayout(header_row)

        # Notification banner for fetch feedback
        self.banner = NotificationBanner(self)
        root_layout.addWidget(self.banner)

        # 2. KPI Summary Cards Row
        kpi_row = QHBoxLayout()
        kpi_row.setSpacing(12)

        # Card 1: Latest Attempt
        self.card_latest_attempt = self._create_kpi_card("LATEST ATTEMPT")
        self.lbl_attempt_status_container = QWidget()
        lbl_attempt_layout = QHBoxLayout(self.lbl_attempt_status_container)
        lbl_attempt_layout.setContentsMargins(0, 0, 0, 0)
        self.lbl_attempt_pill = make_status_pill(RefreshStatus.UNKNOWN)
        lbl_attempt_layout.addWidget(self.lbl_attempt_pill)
        lbl_attempt_layout.addStretch(1)

        self.card_latest_attempt.layout().addWidget(self.lbl_attempt_status_container)
        self.lbl_attempt_start = QLabel("Start: -")
        self.lbl_attempt_start.setStyleSheet("color: #475569; font-size: 11px;")
        self.card_latest_attempt.layout().addWidget(self.lbl_attempt_start)
        self.lbl_attempt_duration = QLabel("Duration: -")
        self.lbl_attempt_duration.setStyleSheet("color: #0F172A; font-size: 12px; font-weight: 600;")
        self.card_latest_attempt.layout().addWidget(self.lbl_attempt_duration)
        kpi_row.addWidget(self.card_latest_attempt)

        # Card 2: Latest Success
        self.card_latest_success = self._create_kpi_card("LATEST SUCCESSFUL REFRESH")
        self.lbl_success_time = QLabel("-")
        self.lbl_success_time.setStyleSheet("color: #065F46; font-size: 15px; font-weight: 700;")
        self.card_latest_success.layout().addWidget(self.lbl_success_time)
        self.lbl_success_age = QLabel("Age: -")
        self.lbl_success_age.setStyleSheet("color: #475569; font-size: 11px;")
        self.card_latest_success.layout().addWidget(self.lbl_success_age)
        self.lbl_success_duration = QLabel("Duration: -")
        self.lbl_success_duration.setStyleSheet("color: #0F172A; font-size: 12px; font-weight: 600;")
        self.card_latest_success.layout().addWidget(self.lbl_success_duration)
        kpi_row.addWidget(self.card_latest_success)

        # Card 3: Reliability
        self.card_reliability = self._create_kpi_card("REFRESH RELIABILITY")
        self.lbl_rate = QLabel("-")
        self.lbl_rate.setStyleSheet("color: #1668DC; font-size: 15px; font-weight: 700;")
        self.card_reliability.layout().addWidget(self.lbl_rate)
        self.lbl_rate_detail = QLabel("Recorded Runs: 0")
        self.lbl_rate_detail.setStyleSheet("color: #475569; font-size: 11px;")
        self.card_reliability.layout().addWidget(self.lbl_rate_detail)
        self.lbl_in_progress_detail = QLabel("In-Progress: 0")
        self.lbl_in_progress_detail.setStyleSheet("color: #64748B; font-size: 11px;")
        self.card_reliability.layout().addWidget(self.lbl_in_progress_detail)
        kpi_row.addWidget(self.card_reliability)

        root_layout.addLayout(kpi_row)

        # 3. Refresh History Table
        table_frame = QFrame()
        table_frame.setObjectName("Card")
        table_layout = QVBoxLayout(table_frame)
        table_layout.setContentsMargins(12, 12, 12, 12)
        table_layout.setSpacing(8)

        tbl_header = QHBoxLayout()
        tbl_title = QLabel("Execution History (Persisted Locally)")
        tbl_title.setStyleSheet("color: #0F172A; font-size: 13px; font-weight: 600;")
        tbl_header.addWidget(tbl_title)
        tbl_header.addStretch(1)

        self.lbl_table_count = QLabel("0 records")
        self.lbl_table_count.setStyleSheet("color: #64748B; font-size: 11px;")
        tbl_header.addWidget(self.lbl_table_count)
        table_layout.addLayout(tbl_header)

        self.table = QTableWidget(0, 6)
        self.table.setObjectName("EnterpriseTable")
        self.table.setHorizontalHeaderLabels([
            "Status",
            "Start Time (UTC)",
            "End Time (UTC)",
            "Duration",
            "Type",
            "Refresh ID",
        ])
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(34)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        self.table.itemSelectionChanged.connect(self._on_table_row_selected)
        table_layout.addWidget(self.table)

        # 4. Diagnostics / Error Drawer
        self.drawer_frame = QFrame()
        self.drawer_frame.setStyleSheet(
            "background-color: #F8FAFC; border: 1px solid #E2E8F0; border-radius: 6px; padding: 6px;"
        )
        drawer_layout = QVBoxLayout(self.drawer_frame)
        drawer_layout.setContentsMargins(10, 8, 10, 8)
        drawer_layout.setSpacing(4)

        drawer_title = QLabel("Selected Run Details & Diagnostics:")
        drawer_title.setStyleSheet("color: #334155; font-size: 11px; font-weight: 600;")
        drawer_layout.addWidget(drawer_title)

        self.error_text = QTextEdit()
        self.error_text.setReadOnly(True)
        self.error_text.setMaximumHeight(85)
        self.error_text.setStyleSheet(
            "background-color: #FFFFFF; border: 1px solid #CBD5E1; border-radius: 4px; "
            "font-family: Consolas, monospace; font-size: 11px; color: #1E293B;"
        )
        self.error_text.setPlaceholderText("Select any run above to inspect error or execution diagnostics.")
        drawer_layout.addWidget(self.error_text)
        table_layout.addWidget(self.drawer_frame)

        root_layout.addWidget(table_frame, stretch=1)

        # 5. Bottom action bar
        bottom_row = QHBoxLayout()
        bottom_row.addStretch(1)

        self.close_button = QPushButton("Close")
        self.close_button.setObjectName("SecondaryButton")
        self.close_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.close_button.clicked.connect(self.accept)
        bottom_row.addWidget(self.close_button)

        root_layout.addLayout(bottom_row)

    def _create_kpi_card(self, title: str) -> QFrame:
        card = QFrame()
        card.setObjectName("Card")
        card.setStyleSheet(
            "QFrame#Card { background-color: #FFFFFF; border: 1px solid #E2E8F0; border-radius: 8px; } "
            "QLabel { border: none; background: transparent; }"
        )
        layout = QVBoxLayout(card)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(6)

        header = QLabel(title)
        header.setStyleSheet("color: #64748B; font-size: 11px; font-weight: 700; letter-spacing: 0.5px;")
        layout.addWidget(header)
        return card

    def _connect_signals(self) -> None:
        self._service.refresh_loaded.connect(self._on_refresh_loaded)
        self._service.refresh_failed.connect(self._on_refresh_failed)
        self._service.busy_changed.connect(self._on_busy_changed)

    def _disconnect_signals(self) -> None:
        try:
            self._service.refresh_loaded.disconnect(self._on_refresh_loaded)
            self._service.refresh_failed.disconnect(self._on_refresh_failed)
            self._service.busy_changed.disconnect(self._on_busy_changed)
        except Exception:
            pass

    def closeEvent(self, event) -> None:
        self._disconnect_signals()
        super().closeEvent(event)

    def _load_data(self) -> None:
        self._records = self._service.list_history(self._reg_id, limit=50)
        self._update_kpi_cards()
        self._populate_table()

    def _update_kpi_cards(self) -> None:
        summary = self._service.get_refresh_summary(self._reg_id)

        # Latest Attempt
        latest = summary.latest_attempt
        if latest is not None:
            # Replace pill
            lbl_layout = self.lbl_attempt_status_container.layout()
            if self.lbl_attempt_pill is not None:
                lbl_layout.removeWidget(self.lbl_attempt_pill)
                self.lbl_attempt_pill.deleteLater()
            self.lbl_attempt_pill = make_status_pill(latest.status)
            lbl_layout.addWidget(self.lbl_attempt_pill)
            lbl_layout.addStretch(1)

            self.lbl_attempt_start.setText(f"Start: {latest.start_time_display}")
            self.lbl_attempt_duration.setText(f"Duration: {latest.duration_display}")
        else:
            self.lbl_attempt_start.setText("Start: -")
            self.lbl_attempt_duration.setText("Duration: -")

        # Latest Success
        latest_success = summary.latest_successful
        if latest_success is not None:
            self.lbl_success_time.setText(latest_success.end_time_display)
            age_str = f"Age: {latest_success.age_hours}h ago" if latest_success.age_hours is not None else "Age: -"
            self.lbl_success_age.setText(age_str)
            self.lbl_success_duration.setText(f"Duration: {latest_success.duration_display}")
        else:
            self.lbl_success_time.setText("None Recorded")
            self.lbl_success_age.setText("Age: -")
            self.lbl_success_duration.setText("Duration: -")

        # Reliability
        self.lbl_rate.setText(summary.success_rate_display)
        self.lbl_rate_detail.setText(
            f"Total: {summary.total_runs}  |  Passed: {summary.success_count}  |  Failed: {summary.failure_count}"
        )
        self.lbl_in_progress_detail.setText(f"Currently In-Progress: {summary.in_progress_count}")

    def _populate_table(self) -> None:
        self.table.setRowCount(len(self._records))
        self.lbl_table_count.setText(f"{len(self._records)} records persisted")

        for row, rec in enumerate(self._records):
            # Column 0: Status (Bold colorful text, no widget shrink)
            self.table.setItem(row, 0, make_refresh_status_table_item(rec.status))

            # Column 1: Start Time
            item_start = QTableWidgetItem(rec.start_time_display)
            item_start.setTextAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)
            self.table.setItem(row, 1, item_start)

            # Column 2: End Time
            item_end = QTableWidgetItem(rec.end_time_display)
            item_end.setTextAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)
            self.table.setItem(row, 2, item_end)

            # Column 3: Duration (In-progress is explicitly formatted as '- (In Progress)')
            item_dur = QTableWidgetItem(rec.duration_display)
            item_dur.setTextAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)
            self.table.setItem(row, 3, item_dur)

            # Column 4: Type
            item_type = QTableWidgetItem(rec.refresh_type or "-")
            item_type.setTextAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)
            self.table.setItem(row, 4, item_type)

            # Column 5: Refresh ID
            item_id = QTableWidgetItem(rec.refresh_id or "-")
            item_id.setTextAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)
            self.table.setItem(row, 5, item_id)

        if self._records:
            self.table.selectRow(0)

    def _on_table_row_selected(self) -> None:
        selected_indexes = self.table.selectedIndexes()
        if not selected_indexes:
            self.error_text.clear()
            return
        row = selected_indexes[0].row()
        if 0 <= row < len(self._records):
            rec = self._records[row]
            lines = [
                f"Refresh ID: {rec.refresh_id or '-'}",
                f"Status: {rec.status.value}  |  Type: {rec.refresh_type or '-'}",
                f"Start: {rec.start_time_display}  |  End: {rec.end_time_display}  |  Duration: {rec.duration_display}",
            ]
            if rec.error_details:
                lines.append("\n--- Error Diagnostics ---")
                try:
                    formatted_json = json.dumps(json.loads(rec.error_details), indent=2)
                    lines.append(formatted_json)
                except Exception:
                    lines.append(rec.error_details)
            else:
                lines.append("\nStatus note: No error details reported for this execution.")
            self.error_text.setPlainText("\n".join(lines))

    def _handle_fetch_live(self) -> None:
        self.banner.hide()
        self.fetch_button.setEnabled(False)
        self.fetch_button.setText("Fetching Power BI Refreshes...")
        self._service.fetch_refreshes_async(
            workspace_registration_id=self._reg_id,
            workspace_id=self._workspace_id,
            dataset_id=self._dataset_id,
            top=20,
        )

    def _on_refresh_loaded(self, reg_id: int, records: list) -> None:
        if reg_id != self._reg_id:
            return
        self.fetch_button.setEnabled(True)
        self.fetch_button.setText("↻  Fetch Live Power BI History")
        self.banner.show_message(
            f"Successfully retrieved and persisted {len(records)} refresh record(s) from Power BI Service.",
            level=NotificationLevel.SUCCESS,
            title="Refreshes Synchronized",
        )
        self._load_data()

    def _on_refresh_failed(self, reg_id: int, error_message: str) -> None:
        if reg_id != self._reg_id:
            return
        self.fetch_button.setEnabled(True)
        self.fetch_button.setText("↻  Fetch Live Power BI History")
        self.banner.show_message(
            f"Could not retrieve refresh history: {error_message}",
            level=NotificationLevel.ERROR,
            title="Refresh Fetch Error",
        )

    def _on_busy_changed(self, busy: bool) -> None:
        self.fetch_button.setEnabled(not busy)
        if not busy:
            self.fetch_button.setText("↻  Fetch Live Power BI History")
