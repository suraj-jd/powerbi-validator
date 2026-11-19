"""Validation History and Audit page with filtering, comparisons, exports, and backup (Stage 14)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.core.status import NotificationLevel, ValidationStatus
from app.services.compare_service import compare_validation_runs
from app.services.export_service import (
    export_diagnostic_logs,
    export_run_to_csv,
    export_run_to_xlsx,
)
from app.services.orchestrator_service import (
    OrchestratorService,
    ValidationResultDTO,
    ValidationRunSummaryDTO,
)
from app.ui.dialogs.backup_maintenance_dialog import BackupMaintenanceDialog
from app.ui.dialogs.result_details_dialog import (
    ResultDetailsDialog,
    make_validation_status_pill,
)
from app.ui.widgets.smooth_scroller import apply_smooth_scrolling
from app.ui.dialogs.run_comparison_dialog import RunComparisonDialog
from app.ui.widgets.notification_banner import NotificationBanner

if TYPE_CHECKING:
    from app.database.db import DatabaseManager
    from app.services.registry_service import RegistryService


class NumericTableWidgetItem(QTableWidgetItem):
    """QTableWidgetItem that sorts numerically or chronologically using UserRole value."""

    def __lt__(self, other: object) -> bool:
        if isinstance(other, QTableWidgetItem):
            v1 = self.data(Qt.ItemDataRole.UserRole)
            v2 = other.data(Qt.ItemDataRole.UserRole)
            if v1 is not None and v2 is not None:
                try:
                    return float(v1) < float(v2)
                except (ValueError, TypeError):
                    return str(v1) < str(v2)
        return super().__lt__(other)


class HistoryPage(QWidget):
    """Validation history page displaying past execution runs, per-rule results, comparisons, and exports."""

    def __init__(
        self,
        parent: QWidget | None = None,
        *,
        orchestrator_service: OrchestratorService | None = None,
        registry_service: RegistryService | None = None,
        db_manager: DatabaseManager | None = None,
        logs_dir: Path | None = None,
    ) -> None:
        super().__init__(parent)
        self._orchestrator = orchestrator_service
        self._registry = registry_service
        self._db = db_manager
        self._logs_dir = logs_dir
        self._runs: list[ValidationRunSummaryDTO] = []
        self._active_run: ValidationRunSummaryDTO | None = None
        self._build_ui()
        self.refresh_history()

    def _build_ui(self) -> None:
        outer_layout = QVBoxLayout(self)
        outer_layout.setContentsMargins(0, 0, 0, 0)

        scroll_area = QScrollArea(self)
        scroll_area.setObjectName("PageScrollArea")
        scroll_area.setWidgetResizable(True)
        scroll_area.setFrameShape(QFrame.Shape.NoFrame)

        container = QWidget()
        container.setObjectName("PageContainer")
        layout = QVBoxLayout(container)
        layout.setContentsMargins(28, 20, 28, 24)
        layout.setSpacing(16)

        # Header row
        header_row = QHBoxLayout()
        header_row.setSpacing(12)

        title_block = QVBoxLayout()
        title_block.setSpacing(4)
        title_label = QLabel("Validation History & Audit Log")
        title_label.setObjectName("PageTitle")
        title_block.addWidget(title_label)

        subtitle_label = QLabel(
            "Review past execution runs, compare changes over time, export reports, and maintain backups."
        )
        subtitle_label.setObjectName("PageSubtitle")
        title_block.addWidget(subtitle_label)
        header_row.addLayout(title_block, stretch=1)

        badge = QLabel("Stage 14 — History & Export Active")
        badge.setObjectName("StageBadge")
        badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        header_row.addWidget(badge, alignment=Qt.AlignmentFlag.AlignTop)
        layout.addLayout(header_row)

        self.banner = NotificationBanner(container)
        layout.addWidget(self.banner)

        # Actions Toolbar Card
        action_card = QFrame()
        action_card.setObjectName("Card")
        action_layout = QHBoxLayout(action_card)
        action_layout.setContentsMargins(14, 10, 14, 10)
        action_layout.setSpacing(10)

        self.btn_refresh = QPushButton("↻  Refresh History")
        self.btn_refresh.setObjectName("SecondaryButton")
        self.btn_refresh.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_refresh.clicked.connect(self.refresh_history)
        action_layout.addWidget(self.btn_refresh)

        self.btn_compare = QPushButton("⚖  Compare Runs...")
        self.btn_compare.setObjectName("SecondaryButton")
        self.btn_compare.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_compare.clicked.connect(self._handle_compare_runs)
        action_layout.addWidget(self.btn_compare)

        action_layout.addStretch(1)

        self.btn_export_csv = QPushButton("Export CSV...")
        self.btn_export_csv.setObjectName("SecondaryButton")
        self.btn_export_csv.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_export_csv.clicked.connect(self._handle_export_csv)
        action_layout.addWidget(self.btn_export_csv)

        self.btn_export_xlsx = QPushButton("Export Excel...")
        self.btn_export_xlsx.setObjectName("SecondaryButton")
        self.btn_export_xlsx.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_export_xlsx.clicked.connect(self._handle_export_xlsx)
        action_layout.addWidget(self.btn_export_xlsx)

        self.btn_export_logs = QPushButton("Diagnostic Logs...")
        self.btn_export_logs.setObjectName("SecondaryButton")
        self.btn_export_logs.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_export_logs.clicked.connect(self._handle_export_logs)
        action_layout.addWidget(self.btn_export_logs)

        if self._db is not None:
            self.btn_backup = QPushButton("Database Maintenance...")
            self.btn_backup.setObjectName("PrimaryButton")
            self.btn_backup.setStyleSheet(
                "background-color: #1668DC; color: #FFFFFF; font-weight: 600; padding: 6px 12px; border-radius: 6px;"
            )
            self.btn_backup.setCursor(Qt.CursorShape.PointingHandCursor)
            self.btn_backup.clicked.connect(self._handle_backup_maintenance)
            action_layout.addWidget(self.btn_backup)

        layout.addWidget(action_card)

        # Excel-Style Filters Toolbar Card
        filter_card = QFrame()
        filter_card.setObjectName("Card")
        filter_card_layout = QVBoxLayout(filter_card)
        filter_card_layout.setContentsMargins(14, 10, 14, 10)
        filter_card_layout.setSpacing(6)

        filter_row = QHBoxLayout()
        filter_row.setSpacing(10)

        lbl_filter_icon = QLabel("🔍")
        lbl_filter_icon.setStyleSheet("font-size: 13px;")
        filter_row.addWidget(lbl_filter_icon)

        self.search_input = QLineEdit()
        self.search_input.setObjectName("SearchInput")
        self.search_input.setPlaceholderText("Search runs by ID, date, status, duration, version...")
        self.search_input.setClearButtonEnabled(True)
        self.search_input.textChanged.connect(lambda _: self._apply_filters())
        filter_row.addWidget(self.search_input, stretch=2)

        lbl_status = QLabel("Status:")
        lbl_status.setStyleSheet("font-size: 12px; font-weight: 600; color: #475569;")
        filter_row.addWidget(lbl_status)

        self.status_filter_combo = QComboBox()
        self.status_filter_combo.setObjectName("FilterCombo")
        self.status_filter_combo.addItems([
            "All Run Statuses",
            "Failed Runs Only",
            "Passed Runs Only",
            "Warning Runs Only",
            "Error Runs Only",
        ])
        self.status_filter_combo.currentIndexChanged.connect(lambda _: self._apply_filters())
        filter_row.addWidget(self.status_filter_combo, stretch=1)

        lbl_date = QLabel("Date Range:")
        lbl_date.setStyleSheet("font-size: 12px; font-weight: 600; color: #475569;")
        filter_row.addWidget(lbl_date)

        self.date_filter_combo = QComboBox()
        self.date_filter_combo.setObjectName("FilterCombo")
        self.date_filter_combo.addItems([
            "All Time",
            "Today (Last 24h)",
            "Last 7 Days",
            "Last 30 Days",
        ])
        self.date_filter_combo.currentIndexChanged.connect(lambda _: self._apply_filters())
        filter_row.addWidget(self.date_filter_combo, stretch=1)

        self.btn_clear_filters = QPushButton("✕ Clear Filters")
        self.btn_clear_filters.setObjectName("SecondaryButton")
        self.btn_clear_filters.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_clear_filters.setStyleSheet("padding: 5px 12px; font-size: 12px;")
        self.btn_clear_filters.clicked.connect(self._handle_clear_filters)
        filter_row.addWidget(self.btn_clear_filters)

        filter_card_layout.addLayout(filter_row)

        status_row = QHBoxLayout()
        self.lbl_filtered_count = QLabel("")
        self.lbl_filtered_count.setStyleSheet("font-size: 11px; color: #64748B; font-weight: 500;")
        status_row.addWidget(self.lbl_filtered_count)

        lbl_sort_tip = QLabel("💡 Tip: Click any column header to sort ascending / descending like Excel. Drag column dividers to resize.")
        lbl_sort_tip.setStyleSheet("font-size: 11px; color: #94A3B8; font-style: italic;")
        lbl_sort_tip.setAlignment(Qt.AlignmentFlag.AlignRight)
        status_row.addWidget(lbl_sort_tip)

        filter_card_layout.addLayout(status_row)
        layout.addWidget(filter_card)

        # Splitter housing Runs Table (top) and Results Drawer (bottom)
        splitter = QSplitter(Qt.Orientation.Vertical)
        splitter.setChildrenCollapsible(False)

        # Upper Card: Runs Table
        runs_card = QFrame()
        runs_card.setObjectName("Card")
        runs_lay = QVBoxLayout(runs_card)
        runs_lay.setContentsMargins(14, 12, 14, 12)
        runs_lay.setSpacing(8)

        lbl_runs = QLabel("Execution Runs Log (Select to inspect details)")
        lbl_runs.setStyleSheet("font-size: 13px; font-weight: 700; color: #0F172A;")
        runs_lay.addWidget(lbl_runs)

        self.runs_table = QTableWidget()
        self.runs_table.setObjectName("DataTable")
        self.runs_table.setColumnCount(10)
        self.runs_table.setHorizontalHeaderLabels([
            "Run ID",
            "Started At",
            "Duration",
            "Overall Health",
            "Passed",
            "Failed",
            "Warnings",
            "Errors",
            "Total Rules",
            "Version",
        ])

        header = self.runs_table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        header.setMinimumSectionSize(65)
        header.setSortIndicatorShown(True)
        self.runs_table.verticalHeader().setDefaultSectionSize(34)
        self.runs_table.verticalHeader().setVisible(False)

        # Generous default widths so columns are never squished
        self.runs_table.setColumnWidth(0, 80)    # Run ID
        self.runs_table.setColumnWidth(1, 185)   # Started At
        self.runs_table.setColumnWidth(2, 95)    # Duration
        self.runs_table.setColumnWidth(3, 130)   # Overall Health
        self.runs_table.setColumnWidth(4, 75)    # Passed
        self.runs_table.setColumnWidth(5, 75)    # Failed
        self.runs_table.setColumnWidth(6, 85)    # Warnings
        self.runs_table.setColumnWidth(7, 75)    # Errors
        self.runs_table.setColumnWidth(8, 95)    # Total Rules
        self.runs_table.setColumnWidth(9, 85)    # Version

        self.runs_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.runs_table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.runs_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.runs_table.setAlternatingRowColors(True)
        self.runs_table.setSortingEnabled(True)
        apply_smooth_scrolling(self.runs_table)
        self.runs_table.itemSelectionChanged.connect(self._on_run_selection_changed)
        runs_lay.addWidget(self.runs_table)

        self.empty_runs_label = QLabel("No historical validation runs recorded yet.")
        self.empty_runs_label.setStyleSheet("color: #64748B; font-style: italic; padding: 20px 0; qproperty-alignment: AlignCenter;")
        runs_lay.addWidget(self.empty_runs_label)

        splitter.addWidget(runs_card)

        # Lower Card: Rule Results Drawer
        drawer_card = QFrame()
        drawer_card.setObjectName("Card")
        drawer_lay = QVBoxLayout(drawer_card)
        drawer_lay.setContentsMargins(14, 12, 14, 12)
        drawer_lay.setSpacing(8)

        # Drawer Header with Search & Filter
        drawer_header = QHBoxLayout()
        drawer_header.setSpacing(10)

        self.drawer_title = QLabel("Selected Run Details: (None Selected)")
        self.drawer_title.setStyleSheet("font-size: 13px; font-weight: 700; color: #0F172A;")
        drawer_header.addWidget(self.drawer_title, stretch=1)

        self.results_search_input = QLineEdit()
        self.results_search_input.setObjectName("SearchInput")
        self.results_search_input.setPlaceholderText("Filter rules by name, target...")
        self.results_search_input.setFixedWidth(200)
        self.results_search_input.setClearButtonEnabled(True)
        self.results_search_input.textChanged.connect(lambda _: self._apply_results_filters())
        drawer_header.addWidget(self.results_search_input)

        self.results_status_combo = QComboBox()
        self.results_status_combo.setObjectName("FilterCombo")
        self.results_status_combo.addItems([
            "All Outcomes",
            "Failed Only",
            "Warning Only",
            "Passed Only",
            "Error Only",
        ])
        self.results_status_combo.currentIndexChanged.connect(lambda _: self._apply_results_filters())
        drawer_header.addWidget(self.results_status_combo)

        self.lbl_results_count = QLabel("")
        self.lbl_results_count.setStyleSheet("font-size: 12px; color: #64748B; font-weight: 500;")
        drawer_header.addWidget(self.lbl_results_count)

        drawer_lay.addLayout(drawer_header)

        self.results_table = QTableWidget()
        self.results_table.setObjectName("DataTable")
        self.results_table.setColumnCount(9)
        self.results_table.setHorizontalHeaderLabels([
            "Status",
            "Rule Name",
            "Target",
            "Check Type",
            "Actual Value",
            "Expected Value",
            "Deviation",
            "Duration",
            "Action",
        ])

        r_header = self.results_table.horizontalHeader()
        r_header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        r_header.setMinimumSectionSize(65)
        r_header.setSortIndicatorShown(True)
        self.results_table.verticalHeader().setDefaultSectionSize(32)
        self.results_table.verticalHeader().setVisible(False)

        self.results_table.setColumnWidth(0, 110)   # Status (pill)
        self.results_table.setColumnWidth(1, 230)   # Rule Name
        self.results_table.setColumnWidth(2, 180)   # Target
        self.results_table.setColumnWidth(3, 140)   # Check Type
        self.results_table.setColumnWidth(4, 120)   # Actual Value
        self.results_table.setColumnWidth(5, 120)   # Expected Value
        self.results_table.setColumnWidth(6, 100)   # Deviation
        self.results_table.setColumnWidth(7, 90)    # Duration
        self.results_table.setColumnWidth(8, 90)    # Action

        self.results_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.results_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.results_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.results_table.setAlternatingRowColors(True)
        self.results_table.setSortingEnabled(True)
        apply_smooth_scrolling(self.results_table)
        self.results_table.cellDoubleClicked.connect(self._handle_result_double_clicked)
        drawer_lay.addWidget(self.results_table)

        self.empty_results_label = QLabel("Select a run above to inspect individual rule outcomes.")
        self.empty_results_label.setStyleSheet("color: #64748B; font-style: italic; padding: 20px 0; qproperty-alignment: AlignCenter;")
        drawer_lay.addWidget(self.empty_results_label)

        splitter.addWidget(drawer_card)
        splitter.setSizes([260, 260])
        layout.addWidget(splitter)

        scroll_area.setWidget(container)
        outer_layout.addWidget(scroll_area)

    def refresh_history(self) -> None:
        """Fetch and reload past validation runs from SQLite."""
        if self._orchestrator is None:
            self._runs = []
            self._render_runs_table()
            return

        with self._orchestrator._db.session_scope() as session:
            from app.database.repositories.run_repository import ValidationRunRepository
            repo = ValidationRunRepository(session)
            raw_runs = repo.list_runs(limit=100)
            self._runs = [ValidationRunSummaryDTO.from_orm(r, repo.list_results_for_run(r.id)) for r in raw_runs]

        self._render_runs_table()

    def _render_runs_table(self) -> None:
        self.runs_table.setSortingEnabled(False)
        try:
            self.runs_table.setRowCount(len(self._runs))
            if not self._runs:
                self.runs_table.hide()
                self.empty_runs_label.show()
                self.lbl_filtered_count.setText("")
                self._clear_drawer()
                return

            self.empty_runs_label.hide()
            self.runs_table.show()

            for row_idx, run in enumerate(self._runs):
                # Col 0: Run ID
                item_id = NumericTableWidgetItem(f"#{run.id}")
                item_id.setData(Qt.ItemDataRole.UserRole, int(run.id))
                item_id.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self.runs_table.setItem(row_idx, 0, item_id)

                # Col 1: Started At
                iso_str = run.started_at.isoformat() if run.started_at else ""
                item_date = NumericTableWidgetItem(run.started_at_display)
                item_date.setData(Qt.ItemDataRole.UserRole, iso_str)
                self.runs_table.setItem(row_idx, 1, item_date)

                # Col 2: Duration
                item_dur = NumericTableWidgetItem(run.duration_display)
                item_dur.setData(Qt.ItemDataRole.UserRole, float(run.duration_ms))
                item_dur.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self.runs_table.setItem(row_idx, 2, item_dur)

                # Col 3: Overall Status Pill
                item_st = NumericTableWidgetItem(run.overall_status.value)
                item_st.setData(Qt.ItemDataRole.UserRole, run.overall_status.value)
                self.runs_table.setItem(row_idx, 3, item_st)

                pill = make_validation_status_pill(run.overall_status)
                w = QWidget()
                wl = QHBoxLayout(w)
                wl.setContentsMargins(0, 0, 0, 0)
                wl.setAlignment(Qt.AlignmentFlag.AlignCenter)
                wl.addWidget(pill)
                self.runs_table.setCellWidget(row_idx, 3, w)

                # Col 4: Passed
                item_p = NumericTableWidgetItem(str(run.passed_count))
                item_p.setData(Qt.ItemDataRole.UserRole, int(run.passed_count))
                item_p.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self.runs_table.setItem(row_idx, 4, item_p)

                # Col 5: Failed
                item_f = NumericTableWidgetItem(str(run.failed_count))
                item_f.setData(Qt.ItemDataRole.UserRole, int(run.failed_count))
                item_f.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self.runs_table.setItem(row_idx, 5, item_f)

                # Col 6: Warnings
                item_w = NumericTableWidgetItem(str(run.warning_count))
                item_w.setData(Qt.ItemDataRole.UserRole, int(run.warning_count))
                item_w.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self.runs_table.setItem(row_idx, 6, item_w)

                # Col 7: Errors
                item_e = NumericTableWidgetItem(str(run.error_count))
                item_e.setData(Qt.ItemDataRole.UserRole, int(run.error_count))
                item_e.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self.runs_table.setItem(row_idx, 7, item_e)

                # Col 8: Total
                item_t = NumericTableWidgetItem(str(run.total_rules))
                item_t.setData(Qt.ItemDataRole.UserRole, int(run.total_rules))
                item_t.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self.runs_table.setItem(row_idx, 8, item_t)

                # Col 9: Version
                item_v = QTableWidgetItem(run.app_version or "—")
                item_v.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self.runs_table.setItem(row_idx, 9, item_v)
        finally:
            self.runs_table.setSortingEnabled(True)

        # Select first row by default if available
        if self._runs:
            self.runs_table.selectRow(0)

        self._apply_filters()

    def _on_run_selection_changed(self) -> None:
        selected_indexes = self.runs_table.selectionModel().selectedRows()
        if not selected_indexes:
            self._clear_drawer()
            return

        row_idx = selected_indexes[0].row()
        item = self.runs_table.item(row_idx, 0)
        run = None
        if item is not None:
            run_id = item.data(Qt.ItemDataRole.UserRole)
            run = next((r for r in self._runs if r.id == run_id), None)
        if run is None and 0 <= row_idx < len(self._runs):
            run = self._runs[row_idx]

        if run is not None:
            self._active_run = run
            self._display_drawer_results(run)
        else:
            self._clear_drawer()

    def _display_drawer_results(self, run: ValidationRunSummaryDTO) -> None:
        self.drawer_title.setText(
            f"Run #{run.id} Results — {run.overall_status.value} ({run.started_at_display}, duration: {run.duration_display})"
        )
        self.results_table.setSortingEnabled(False)
        try:
            self.results_table.setRowCount(len(run.results))

            if not run.results:
                self.results_table.hide()
                self.empty_results_label.show()
                self.lbl_results_count.setText("0 rules")
                return

            self.empty_results_label.hide()
            self.results_table.show()

            for r_idx, res in enumerate(run.results):
                # Col 0: Status Pill
                item_st = QTableWidgetItem(res.status.value)
                item_st.setData(Qt.ItemDataRole.EditRole, res.status.value)
                item_st.setData(Qt.ItemDataRole.UserRole, res.id)
                self.results_table.setItem(r_idx, 0, item_st)

                pill = make_validation_status_pill(res.status)
                w = QWidget()
                wl = QHBoxLayout(w)
                wl.setContentsMargins(0, 0, 0, 0)
                wl.setAlignment(Qt.AlignmentFlag.AlignCenter)
                wl.addWidget(pill)
                self.results_table.setCellWidget(r_idx, 0, w)

                # Col 1: Rule Name
                item_rn = QTableWidgetItem(res.rule_name)
                item_rn.setData(Qt.ItemDataRole.EditRole, res.rule_name)
                self.results_table.setItem(r_idx, 1, item_rn)

                # Col 2: Target
                item_tg = QTableWidgetItem(res.target_display)
                item_tg.setData(Qt.ItemDataRole.EditRole, res.target_display)
                self.results_table.setItem(r_idx, 2, item_tg)

                # Col 3: Check Type
                item_ct = QTableWidgetItem(res.validation_type)
                item_ct.setData(Qt.ItemDataRole.EditRole, res.validation_type)
                self.results_table.setItem(r_idx, 3, item_ct)

                # Col 4: Actual
                item_act = QTableWidgetItem(res.actual_value or "—")
                item_act.setData(Qt.ItemDataRole.EditRole, res.actual_value or "")
                self.results_table.setItem(r_idx, 4, item_act)

                # Col 5: Expected
                item_exp = QTableWidgetItem(res.expected_value or "—")
                item_exp.setData(Qt.ItemDataRole.EditRole, res.expected_value or "")
                self.results_table.setItem(r_idx, 5, item_exp)

                # Col 6: Deviation
                item_dev = QTableWidgetItem(res.deviation or "None")
                item_dev.setData(Qt.ItemDataRole.EditRole, res.deviation or "")
                self.results_table.setItem(r_idx, 6, item_dev)

                # Col 7: Duration
                item_dur = NumericTableWidgetItem(f"{res.duration_ms} ms")
                item_dur.setData(Qt.ItemDataRole.UserRole, int(res.duration_ms))
                item_dur.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self.results_table.setItem(r_idx, 7, item_dur)

                # Col 8: Action button
                item_act_btn = QTableWidgetItem()
                self.results_table.setItem(r_idx, 8, item_act_btn)

                btn = QPushButton("Details...")
                btn.setObjectName("SecondaryButton")
                btn.setStyleSheet("padding: 2px 8px; font-size: 11px;")
                btn.setCursor(Qt.CursorShape.PointingHandCursor)
                btn.clicked.connect(lambda _, r=res: self._open_result_details(r))
                self.results_table.setCellWidget(r_idx, 8, btn)
        finally:
            self.results_table.setSortingEnabled(True)

        self._apply_results_filters()

    def _clear_drawer(self) -> None:
        self._active_run = None
        self.drawer_title.setText("Selected Run Details: (None Selected)")
        self.results_table.setRowCount(0)
        self.results_table.hide()
        self.empty_results_label.show()
        self.lbl_results_count.setText("")

    def _apply_filters(self) -> None:
        query = self.search_input.text().strip().lower()
        filter_mode = self.status_filter_combo.currentIndex()
        date_mode = self.date_filter_combo.currentIndex()

        now_utc = datetime.now(timezone.utc)
        visible_count = 0
        total_count = self.runs_table.rowCount()

        for row_idx in range(total_count):
            item = self.runs_table.item(row_idx, 0)
            run_id = item.data(Qt.ItemDataRole.UserRole) if item is not None else None
            run = next((r for r in self._runs if r.id == run_id), None)
            if run is None and row_idx < len(self._runs):
                run = self._runs[row_idx]
            if run is None:
                continue

            # Status filter
            st_val = run.overall_status.value.upper()
            status_match = True
            if filter_mode == 1 and st_val != "FAIL":
                status_match = False
            elif filter_mode == 2 and st_val != "PASS":
                status_match = False
            elif filter_mode == 3 and st_val != "WARNING":
                status_match = False
            elif filter_mode == 4 and st_val != "ERROR":
                status_match = False

            # Date range filter
            date_match = True
            if date_mode > 0 and run.started_at is not None:
                r_dt = run.started_at
                if r_dt.tzinfo is None:
                    r_dt = r_dt.replace(tzinfo=timezone.utc)
                delta = now_utc - r_dt
                if date_mode == 1:   # Today (last 24 hours)
                    date_match = delta <= timedelta(days=1)
                elif date_mode == 2: # Last 7 Days
                    date_match = delta <= timedelta(days=7)
                elif date_mode == 3: # Last 30 Days
                    date_match = delta <= timedelta(days=30)

            # Search query filter
            query_match = True
            if query:
                blob = f"#{run.id} {run.started_at_display} {st_val} {run.duration_display} {run.app_version}".lower()
                query_match = query in blob

            show = status_match and date_match and query_match
            self.runs_table.setRowHidden(row_idx, not show)
            if show:
                visible_count += 1

        if len(self._runs) > 0:
            if visible_count == len(self._runs):
                self.lbl_filtered_count.setText(f"Showing all {visible_count} runs")
            else:
                self.lbl_filtered_count.setText(f"Showing {visible_count} of {len(self._runs)} runs (filtered)")
        else:
            self.lbl_filtered_count.setText("")

    def _apply_results_filters(self) -> None:
        if not self._active_run:
            self.lbl_results_count.setText("")
            return

        query = self.results_search_input.text().strip().lower()
        mode = self.results_status_combo.currentIndex()
        visible_count = 0
        total_count = self.results_table.rowCount()

        for visual_row in range(total_count):
            item = self.results_table.item(visual_row, 0)
            res_id = item.data(Qt.ItemDataRole.UserRole) if item is not None else None
            res = next((r for r in self._active_run.results if r.id == res_id), None)
            if res is None and visual_row < len(self._active_run.results):
                res = self._active_run.results[visual_row]
            if res is None:
                continue

            status_val = res.status.value.upper()
            status_match = True
            if mode == 1 and status_val != "FAIL":
                status_match = False
            elif mode == 2 and status_val != "WARNING":
                status_match = False
            elif mode == 3 and status_val != "PASS":
                status_match = False
            elif mode == 4 and status_val != "ERROR":
                status_match = False

            query_match = True
            if query:
                blob = f"{res.rule_name} {res.target_display} {res.validation_type} {res.actual_value} {res.expected_value} {status_val}".lower()
                query_match = query in blob

            show = status_match and query_match
            self.results_table.setRowHidden(visual_row, not show)
            if show:
                visible_count += 1

        if visible_count == total_count:
            self.lbl_results_count.setText(f"{total_count} rules")
        else:
            self.lbl_results_count.setText(f"Showing {visible_count} of {total_count} rules")

    def _handle_clear_filters(self) -> None:
        self.search_input.blockSignals(True)
        self.status_filter_combo.blockSignals(True)
        self.date_filter_combo.blockSignals(True)

        self.search_input.clear()
        self.status_filter_combo.setCurrentIndex(0)
        self.date_filter_combo.setCurrentIndex(0)

        self.search_input.blockSignals(False)
        self.status_filter_combo.blockSignals(False)
        self.date_filter_combo.blockSignals(False)

        self._apply_filters()

    def _handle_result_double_clicked(self, row: int, _col: int) -> None:
        if not self._active_run:
            return
        item = self.results_table.item(row, 0)
        target_res = None
        if item is not None:
            res_id = item.data(Qt.ItemDataRole.UserRole)
            target_res = next((r for r in self._active_run.results if r.id == res_id), None)
        if target_res is None and 0 <= row < len(self._active_run.results):
            target_res = self._active_run.results[row]
        if target_res is not None:
            self._open_result_details(target_res)

    def _open_result_details(self, result: ValidationResultDTO) -> None:
        dialog = ResultDetailsDialog(result, parent=self)
        dialog.exec()

    def _handle_compare_runs(self) -> None:
        selected_rows = self.runs_table.selectionModel().selectedRows()
        if len(selected_rows) < 2:
            if len(self._runs) < 2:
                self.banner.show_message(
                    "At least 2 validation runs are required to perform a comparison.",
                    level=NotificationLevel.WARNING,
                    title="Comparison Requirement",
                )
                return
            # Default compare top 2 runs
            run_b = self._runs[0]
            run_a = self._runs[1]
        else:
            def _get_run_for_row(row_i: int) -> ValidationRunSummaryDTO | None:
                it = self.runs_table.item(row_i, 0)
                if it is not None:
                    rid = it.data(Qt.ItemDataRole.UserRole)
                    found = next((r for r in self._runs if r.id == rid), None)
                    if found is not None:
                        return found
                return self._runs[row_i] if 0 <= row_i < len(self._runs) else None

            run_b = _get_run_for_row(selected_rows[0].row())
            run_a = _get_run_for_row(selected_rows[1].row())
            if not run_a or not run_b:
                return

        comparison = compare_validation_runs(run_a, run_b)
        dialog = RunComparisonDialog(comparison, parent=self)
        dialog.exec()

    def _handle_export_csv(self) -> None:
        if not self._active_run:
            self.banner.show_message("Please select a validation run to export.", level=NotificationLevel.WARNING)
            return

        filename, _ = QFileDialog.getSaveFileName(
            self,
            "Export Validation Results to CSV",
            str(Path.home() / f"validation_run_{self._active_run.id}.csv"),
            "CSV Files (*.csv);;All Files (*.*)",
        )
        if not filename:
            return

        try:
            dest = export_run_to_csv(self._active_run, filename)
            self.banner.show_message(
                f"Exported run #{self._active_run.id} to CSV: '{dest.name}'.",
                level=NotificationLevel.SUCCESS,
                title="CSV Export Complete",
            )
        except Exception as exc:
            self.banner.show_message(f"CSV Export failed: {exc}", level=NotificationLevel.ERROR)

    def _handle_export_xlsx(self) -> None:
        if not self._active_run:
            self.banner.show_message("Please select a validation run to export.", level=NotificationLevel.WARNING)
            return

        filename, _ = QFileDialog.getSaveFileName(
            self,
            "Export Validation Results to Excel",
            str(Path.home() / f"validation_run_{self._active_run.id}.xlsx"),
            "Excel Workbooks (*.xlsx);;All Files (*.*)",
        )
        if not filename:
            return

        try:
            dest = export_run_to_xlsx(self._active_run, filename)
            self.banner.show_message(
                f"Exported run #{self._active_run.id} to Excel: '{dest.name}'.",
                level=NotificationLevel.SUCCESS,
                title="Excel Export Complete",
            )
        except Exception as exc:
            self.banner.show_message(f"Excel Export failed: {exc}", level=NotificationLevel.ERROR)

    def _handle_export_logs(self) -> None:
        log_dir = self._logs_dir or (Path.home() / ".powerbi_validation_tool" / "logs")
        filename, _ = QFileDialog.getSaveFileName(
            self,
            "Export Sanitized Diagnostic Logs",
            str(Path.home() / "powerbi_diagnostics.txt"),
            "Text Files (*.txt);;All Files (*.*)",
        )
        if not filename:
            return

        try:
            dest = export_diagnostic_logs(log_dir, filename)
            self.banner.show_message(
                f"Exported sanitized diagnostic report to '{dest.name}'. No credentials or tokens were included.",
                level=NotificationLevel.SUCCESS,
                title="Diagnostics Exported",
            )
        except Exception as exc:
            self.banner.show_message(f"Diagnostics export failed: {exc}", level=NotificationLevel.ERROR)

    def _handle_backup_maintenance(self) -> None:
        if self._db is None:
            return
        dialog = BackupMaintenanceDialog(self._db, parent=self)
        dialog.exec()
        self.refresh_history()
