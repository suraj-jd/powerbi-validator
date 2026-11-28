"""Validation History and Audit page with filtering, comparisons, exports, and backup (Stage 14)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QGridLayout,
    QMenu,
    QSizePolicy,
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
from app.ui.widgets.enterprise import PageHeader, ResultsTable, action_button, status_presentation
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
        return False


def make_status_table_item(status: ValidationStatus | str | None) -> NumericTableWidgetItem:
    """Create a crisp, bold, colorful table item for validation status (no widget shrink)."""
    if not status:
        item = NumericTableWidgetItem("-")
        item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        item.setForeground(QColor("#94A3B8"))
        item.setData(Qt.ItemDataRole.UserRole, "")
        return item

    st_val = status.value if isinstance(status, ValidationStatus) else str(status).upper()
    item = NumericTableWidgetItem(st_val)
    item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
    font = item.font()
    font.setBold(True)
    font.setPointSize(10)
    item.setFont(font)
    item.setData(Qt.ItemDataRole.UserRole, st_val)

    if st_val == "PASS":
        item.setForeground(QColor("#15803D"))
        item.setBackground(QColor("#DCFCE7"))
    elif st_val == "FAIL":
        item.setForeground(QColor("#B91C1C"))
        item.setBackground(QColor("#FEE2E2"))
    elif st_val == "WARNING":
        item.setForeground(QColor("#B45309"))
        item.setBackground(QColor("#FEF3C7"))
    elif st_val == "ERROR":
        item.setForeground(QColor("#7E22CE"))
        item.setBackground(QColor("#F3E8FF"))
    else:
        item.setForeground(QColor("#475569"))
        item.setBackground(QColor("#F1F5F9"))
    _, icon, color, _, explanation = status_presentation(status)
    from app.ui.theme import make_nav_icon
    item.setIcon(make_nav_icon(icon, color, 16))
    item.setToolTip(explanation)
    return item


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
        self._registration_labels = {}
        self._build_ui()
        self.refresh_history()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 16, 24, 16)
        layout.setSpacing(8)
        layout.addWidget(PageHeader("Run History", "Review saved results and compare changes. All timestamps are UTC."))
        self.banner = NotificationBanner(self)
        layout.addWidget(self.banner)

        self.toolbar = QFrame()
        self.toolbar.setObjectName("Card")
        self._toolbar_grid = QGridLayout(self.toolbar)
        self._toolbar_grid.setContentsMargins(10, 8, 10, 8)
        self._toolbar_grid.setSpacing(6)
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Search saved runs…")
        self.search_input.setClearButtonEnabled(True)
        self.search_input.setMinimumWidth(100)
        self.search_input.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
        self.search_input.textChanged.connect(self._apply_filters)
        self.date_filter_combo = QComboBox()
        self.date_filter_combo.addItems(["All time", "Last 24 hours", "Last 7 days", "Last 30 days"])
        self.date_filter_combo.setAccessibleName("Date range")
        self.date_filter_combo.currentIndexChanged.connect(self._apply_filters)
        self.status_filter_combo = QComboBox()
        self.status_filter_combo.addItems(["All outcomes", "Failed", "Passed", "Warnings", "Execution errors"])
        self.status_filter_combo.setAccessibleName("Run outcome")
        self.status_filter_combo.currentIndexChanged.connect(self._apply_filters)
        self.btn_refresh = action_button("", "refresh")
        self.btn_refresh.setAccessibleName("Refresh history")
        self.btn_refresh.setToolTip("Refresh saved history")
        self.btn_refresh.clicked.connect(self.refresh_history)
        self.btn_compare = action_button("Compare runs", "history")
        self.btn_compare.setToolTip("Compare up to four selected runs")
        self.btn_compare.clicked.connect(self._handle_compare_runs)
        export = action_button("Export", "export")
        export_menu = QMenu(export)
        export_menu.addAction("Selected run as CSV", self._handle_export_csv)
        export_menu.addAction("Selected run as Excel", self._handle_export_xlsx)
        export.setMenu(export_menu)
        self.btn_export_csv = action_button("Export selected run CSV")
        self.btn_export_csv.clicked.connect(self._handle_export_csv)
        self.btn_export_csv.hide()
        self.btn_export_xlsx = action_button("Export selected run Excel")
        self.btn_export_xlsx.clicked.connect(self._handle_export_xlsx)
        self.btn_export_xlsx.hide()
        self.more_filters_button = action_button("Filters", "settings")
        self.more_filters_button.setCheckable(True)
        more = action_button("More")
        more_menu = QMenu(more)
        more_menu.addAction("Export diagnostic logs", self._handle_export_logs)
        self.btn_export_logs = action_button("Export diagnostic logs")
        self.btn_export_logs.clicked.connect(self._handle_export_logs)
        self.btn_export_logs.hide()
        if self._db is not None:
            more_menu.addAction("Backup & maintenance", self._handle_backup_maintenance)
            self.btn_backup = action_button("Backup & maintenance")
            self.btn_backup.clicked.connect(self._handle_backup_maintenance)
            self.btn_backup.hide()
        more.setMenu(more_menu)
        self._toolbar_widgets = [self.search_input, self.date_filter_combo, self.status_filter_combo,
                                 self.btn_refresh, self.btn_compare, export, self.more_filters_button, more]
        self._toolbar_wide = None
        self._reflow_history_tools()
        layout.addWidget(self.toolbar)

        self.advanced_filters = QFrame()
        advanced = QHBoxLayout(self.advanced_filters)
        advanced.setContentsMargins(0, 0, 0, 0)
        advanced.addWidget(QLabel("Report / model:"))
        self.report_filter_combo = QComboBox()
        self.report_filter_combo.addItem("All reports", None)
        self.report_filter_combo.setMinimumContentsLength(6)
        self.report_filter_combo.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        self.report_filter_combo.currentIndexChanged.connect(self._apply_filters)
        advanced.addWidget(self.report_filter_combo, 1)
        self.btn_clear_filters = action_button("Clear filters", "close")
        self.btn_clear_filters.clicked.connect(self._handle_clear_filters)
        advanced.addWidget(self.btn_clear_filters)
        self.advanced_filters.hide()
        self.more_filters_button.toggled.connect(self.advanced_filters.setVisible)
        layout.addWidget(self.advanced_filters)
        self.lbl_filtered_count = QLabel("")
        self.lbl_filtered_count.setObjectName("MutedText")
        layout.addWidget(self.lbl_filtered_count)

        self.tables_splitter = QSplitter(Qt.Orientation.Vertical)
        self.tables_splitter.setChildrenCollapsible(False)
        runs_card = QFrame()
        runs_card.setObjectName("Card")
        runs_layout = QVBoxLayout(runs_card)
        runs_layout.setContentsMargins(10, 8, 10, 8)
        self.runs_table = QTableWidget()
        self.runs_table.setObjectName("DataTable")
        self.runs_table.setColumnCount(10)
        self.runs_table.setHorizontalHeaderLabels(["Run", "Started at (UTC)", "Duration", "Outcome", "Passed", "Failed", "Warnings", "Errors", "Checks", "Report / model"])
        self.runs_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.runs_table.horizontalHeader().setMinimumSectionSize(65)
        for col, width in enumerate([70, 210, 85, 130, 70, 70, 85, 70, 75, 220]):
            self.runs_table.setColumnWidth(col, width)
        self.runs_table.verticalHeader().hide()
        self.runs_table.verticalHeader().setDefaultSectionSize(36)
        self.runs_table.setMinimumHeight(100)
        self.runs_table.setShowGrid(False)
        self.runs_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.runs_table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.runs_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.runs_table.setSortingEnabled(True)
        self.runs_table.itemSelectionChanged.connect(self._on_run_selection_changed)
        apply_smooth_scrolling(self.runs_table)
        runs_layout.addWidget(self.runs_table)
        self.empty_runs_label = QLabel("No saved runs yet. Run validation from Overview to record results.")
        self.empty_runs_label.setWordWrap(True)
        runs_layout.addWidget(self.empty_runs_label)
        self.tables_splitter.addWidget(runs_card)

        results_card = QFrame()
        results_card.setObjectName("Card")
        results_layout = QVBoxLayout(results_card)
        results_layout.setContentsMargins(10, 8, 10, 8)
        results_layout.setSpacing(6)
        self.drawer_title = QLabel("Select a saved run")
        self.drawer_title.setObjectName("SectionTitle")
        self.drawer_title.setWordWrap(True)
        results_layout.addWidget(self.drawer_title)
        result_tools = QHBoxLayout()
        self.results_search_input = QLineEdit()
        self.results_search_input.setPlaceholderText("Search selected run's checks…")
        self.results_search_input.setClearButtonEnabled(True)
        self.results_search_input.textChanged.connect(self._apply_results_filters)
        result_tools.addWidget(self.results_search_input, 1)
        self.results_status_combo = QComboBox()
        self.results_status_combo.addItems(["All outcomes", "Failed", "Warnings", "Passed", "Execution errors"])
        self.results_status_combo.currentIndexChanged.connect(self._apply_results_filters)
        result_tools.addWidget(self.results_status_combo)
        self.lbl_results_count = QLabel("")
        self.lbl_results_count.setObjectName("MutedText")
        result_tools.addWidget(self.lbl_results_count)
        results_layout.addLayout(result_tools)
        self.results_table = ResultsTable()
        self.results_table.setMinimumHeight(100)
        self.results_table.cellClicked.connect(self._handle_result_clicked)
        self.results_table.cellDoubleClicked.connect(self._handle_result_double_clicked)
        self.results_table.model().layoutChanged.connect(self._apply_results_filters)
        results_layout.addWidget(self.results_table)
        self.empty_results_label = QLabel("Select a saved run above to inspect its recorded checks.")
        self.empty_results_label.setWordWrap(True)
        results_layout.addWidget(self.empty_results_label)
        self.tables_splitter.addWidget(results_card)
        self.tables_splitter.setSizes([280, 360])
        self.tables_splitter.setStretchFactor(0, 1)
        self.tables_splitter.setStretchFactor(1, 1)
        layout.addWidget(self.tables_splitter, 1)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        if hasattr(self, "_toolbar_widgets"):
            self._reflow_history_tools()

    def _reflow_history_tools(self) -> None:
        wide = self.width() >= 1050
        if wide == self._toolbar_wide:
            return
        self._toolbar_wide = wide
        for widget in self._toolbar_widgets:
            self._toolbar_grid.removeWidget(widget)
        for column in range(8):
            self._toolbar_grid.setColumnStretch(column, 0)
        if wide:
            for column, widget in enumerate(self._toolbar_widgets):
                self._toolbar_grid.addWidget(widget, 0, column)
        else:
            self._toolbar_grid.addWidget(self.search_input, 0, 0, 1, 3)
            self._toolbar_grid.addWidget(self.date_filter_combo, 0, 3, 1, 2)
            self._toolbar_grid.addWidget(self.status_filter_combo, 0, 5, 1, 3)
            for column, widget in enumerate(self._toolbar_widgets[3:]):
                self._toolbar_grid.addWidget(widget, 1, column)
        self._toolbar_grid.setColumnStretch(0, 1)

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
        registrations = self._registry.list_registrations(active_only=False) if self._registry else []
        self._registration_labels = {r.id: f"{r.workspace_name} / {r.report_name}" for r in registrations}
        selected_report = self.report_filter_combo.currentData()
        self.report_filter_combo.blockSignals(True)
        self.report_filter_combo.clear()
        self.report_filter_combo.addItem("All reports", None)
        for registration_id in sorted({r.workspace_registration_id for r in self._runs}):
            self.report_filter_combo.addItem(self._registration_labels.get(registration_id, f"Saved model #{registration_id}"), registration_id)
        index = self.report_filter_combo.findData(selected_report)
        self.report_filter_combo.setCurrentIndex(max(0, index))
        self.report_filter_combo.blockSignals(False)
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
                self.runs_table.setItem(row_idx, 9, QTableWidgetItem(self._registration_labels.get(run.workspace_registration_id, f"Saved model #{run.workspace_registration_id}")))

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

                # Col 3: Overall Status
                item_st = make_status_table_item(run.overall_status)
                self.runs_table.setItem(row_idx, 3, item_st)

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
        self.drawer_title.setText(f"Run #{run.id} · {self._registration_labels.get(run.workspace_registration_id, 'Saved model')} · Started {run.started_at_display} · {run.duration_display}")
        self.results_table.set_results(run.results)
        self.results_table.setVisible(bool(run.results))
        self.empty_results_label.setVisible(not run.results)
        self._apply_results_filters()

    def _handle_result_clicked(self, row: int, col: int) -> None:
        if col == 9:  # Clicked on Details column
            self._handle_result_double_clicked(row, col)

    def _clear_drawer(self) -> None:
        self._active_run = None
        self.drawer_title.setText("Select a saved run")
        self.results_table.setRowCount(0)
        self.results_table.hide()
        self.empty_results_label.show()
        self.lbl_results_count.setText("")

    def _apply_filters(self) -> None:
        if not hasattr(self, "runs_table"):
            return
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

            report_id = self.report_filter_combo.currentData()
            report_match = report_id is None or run.workspace_registration_id == report_id
            show = status_match and date_match and query_match and report_match
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
        if not hasattr(self, "lbl_results_count"):
            return
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
        self.report_filter_combo.setCurrentIndex(0)

        self.search_input.blockSignals(False)
        self.status_filter_combo.blockSignals(False)
        self.date_filter_combo.blockSignals(False)

        self._apply_filters()

    def _handle_result_double_clicked(self, row: int, _col: int) -> None:
        if not self._active_run:
            return
        target_res = self.results_table.result_at(row)
        if target_res is not None:
            self._open_result_details(target_res)

    def _open_result_details(self, result: ValidationResultDTO) -> None:
        dialog = ResultDetailsDialog(result, parent=self)
        dialog.exec()

    def _handle_compare_runs(self) -> None:
        if len(self._runs) < 2:
            self.banner.show_message(
                "At least 2 validation runs are required to perform a comparison.",
                level=NotificationLevel.WARNING,
                title="Comparison Requirement",
            )
            return

        selected_rows = self.runs_table.selectionModel().selectedRows()

        def _get_run_for_row(row_i: int) -> ValidationRunSummaryDTO | None:
            it = self.runs_table.item(row_i, 0)
            if it is not None:
                rid = it.data(Qt.ItemDataRole.UserRole)
                found = next((r for r in self._runs if r.id == rid), None)
                if found is not None:
                    return found
            return self._runs[row_i] if 0 <= row_i < len(self._runs) else None

        run_a: ValidationRunSummaryDTO | None = None
        run_b: ValidationRunSummaryDTO | None = None
        run_c: ValidationRunSummaryDTO | None = None
        run_d: ValidationRunSummaryDTO | None = None

        if len(selected_rows) >= 2:
            chosen_runs: list[ValidationRunSummaryDTO] = []
            for sel in selected_rows[:4]:
                r = _get_run_for_row(sel.row())
                if r and r not in chosen_runs:
                    chosen_runs.append(r)

            # Sort chronological / ID ascending so Run 1 is baseline, Run 2 is target, etc.
            chosen_runs.sort(key=lambda x: x.id)
            if len(chosen_runs) >= 2:
                run_a = chosen_runs[0]
                run_b = chosen_runs[1]
                if len(chosen_runs) > 2:
                    run_c = chosen_runs[2]
                if len(chosen_runs) > 3:
                    run_d = chosen_runs[3]
        elif len(selected_rows) == 1:
            sel_run = _get_run_for_row(selected_rows[0].row())
            if sel_run:
                # Find the previous run chronologically (id immediately lower than sel_run.id)
                older_runs = [r for r in self._runs if r.id < sel_run.id]
                if older_runs:
                    run_a = max(older_runs, key=lambda x: x.id)
                    run_b = sel_run
                else:
                    newer_runs = [r for r in self._runs if r.id > sel_run.id]
                    if newer_runs:
                        run_a = sel_run
                        run_b = min(newer_runs, key=lambda x: x.id)
                    else:
                        run_a = self._runs[1] if len(self._runs) > 1 else sel_run
                        run_b = sel_run
            else:
                run_a = self._runs[1]
                run_b = self._runs[0]
        else:
            # Default: compare previous run (baseline) with newest run (target)
            run_a = self._runs[1]
            run_b = self._runs[0]

        if not run_a or not run_b:
            run_a = self._runs[1]
            run_b = self._runs[0]

        # Chronological guarantee: Baseline (run_a) is earlier than Target (run_b)
        if run_a.id > run_b.id:
            run_a, run_b = run_b, run_a

        comparison = compare_validation_runs(run_a, run_b, run_c, run_d)
        dialog = RunComparisonDialog(comparison, all_runs=self._runs, parent=self)
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
            self.banner.show_export_success(
                f"Exported run #{self._active_run.id} to CSV: '{dest.name}'.",
                dest,
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
            self.banner.show_export_success(
                f"Exported run #{self._active_run.id} to Excel: '{dest.name}'.",
                dest,
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
            self.banner.show_export_success(
                f"Exported sanitized diagnostic report to '{dest.name}'. No credentials or tokens were included.",
                dest,
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
