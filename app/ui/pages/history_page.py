"""Validation History and Audit page with filtering, comparisons, exports, and backup (Stage 14)."""

from __future__ import annotations

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
from app.ui.dialogs.run_comparison_dialog import RunComparisonDialog
from app.ui.widgets.notification_banner import NotificationBanner

if TYPE_CHECKING:
    from app.database.db import DatabaseManager
    from app.services.registry_service import RegistryService


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

        subtitle_label = QLabel("Review past execution runs, compare changes over time, export reports, and maintain backups.")
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

        # Filters toolbar
        filter_row = QHBoxLayout()
        filter_row.setSpacing(10)

        self.search_input = QLineEdit()
        self.search_input.setObjectName("SearchInput")
        self.search_input.setPlaceholderText("Search runs by status, date, or ID...")
        self.search_input.textChanged.connect(lambda _: self._apply_filters())
        filter_row.addWidget(self.search_input, stretch=1)

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
        filter_row.addWidget(self.status_filter_combo)
        layout.addLayout(filter_row)

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
        self.runs_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.runs_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.runs_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.runs_table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.runs_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.runs_table.setAlternatingRowColors(True)
        self.runs_table.verticalHeader().setVisible(False)
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

        self.drawer_title = QLabel("Selected Run Details: (None Selected)")
        self.drawer_title.setStyleSheet("font-size: 13px; font-weight: 700; color: #0F172A;")
        drawer_lay.addWidget(self.drawer_title)

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
        self.results_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.results_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.results_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.results_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.results_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.results_table.setAlternatingRowColors(True)
        self.results_table.verticalHeader().setVisible(False)
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
        self.runs_table.setRowCount(len(self._runs))
        if not self._runs:
            self.runs_table.hide()
            self.empty_runs_label.show()
            self._clear_drawer()
            return

        self.empty_runs_label.hide()
        self.runs_table.show()

        for row_idx, run in enumerate(self._runs):
            # Col 0: Run ID
            self.runs_table.setItem(row_idx, 0, QTableWidgetItem(f"#{run.id}"))

            # Col 1: Started At
            self.runs_table.setItem(row_idx, 1, QTableWidgetItem(run.started_at_display))

            # Col 2: Duration
            self.runs_table.setItem(row_idx, 2, QTableWidgetItem(run.duration_display))

            # Col 3: Overall Status Pill
            pill = make_validation_status_pill(run.overall_status)
            w = QWidget()
            wl = QHBoxLayout(w)
            wl.setContentsMargins(4, 2, 4, 2)
            wl.addWidget(pill)
            self.runs_table.setCellWidget(row_idx, 3, w)

            # Col 4: Passed
            item_p = QTableWidgetItem(str(run.passed_count))
            item_p.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.runs_table.setItem(row_idx, 4, item_p)

            # Col 5: Failed
            item_f = QTableWidgetItem(str(run.failed_count))
            item_f.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.runs_table.setItem(row_idx, 5, item_f)

            # Col 6: Warnings
            item_w = QTableWidgetItem(str(run.warning_count))
            item_w.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.runs_table.setItem(row_idx, 6, item_w)

            # Col 7: Errors
            item_e = QTableWidgetItem(str(run.error_count))
            item_e.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.runs_table.setItem(row_idx, 7, item_e)

            # Col 8: Total
            item_t = QTableWidgetItem(str(run.total_rules))
            item_t.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.runs_table.setItem(row_idx, 8, item_t)

            # Col 9: Version
            self.runs_table.setItem(row_idx, 9, QTableWidgetItem(run.app_version))

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
        if 0 <= row_idx < len(self._runs):
            run = self._runs[row_idx]
            self._active_run = run
            self._display_drawer_results(run)

    def _display_drawer_results(self, run: ValidationRunSummaryDTO) -> None:
        self.drawer_title.setText(
            f"Run #{run.id} Results — {run.overall_status.value} ({run.started_at_display}, duration: {run.duration_display})"
        )
        self.results_table.setRowCount(len(run.results))

        if not run.results:
            self.results_table.hide()
            self.empty_results_label.show()
            return

        self.empty_results_label.hide()
        self.results_table.show()

        for r_idx, res in enumerate(run.results):
            # Col 0: Status Pill
            pill = make_validation_status_pill(res.status)
            w = QWidget()
            wl = QHBoxLayout(w)
            wl.setContentsMargins(4, 2, 4, 2)
            wl.addWidget(pill)
            self.results_table.setCellWidget(r_idx, 0, w)

            # Col 1: Rule Name
            self.results_table.setItem(r_idx, 1, QTableWidgetItem(res.rule_name))

            # Col 2: Target
            self.results_table.setItem(r_idx, 2, QTableWidgetItem(res.target_display))

            # Col 3: Check Type
            self.results_table.setItem(r_idx, 3, QTableWidgetItem(res.validation_type))

            # Col 4: Actual
            self.results_table.setItem(r_idx, 4, QTableWidgetItem(res.actual_value or "—"))

            # Col 5: Expected
            self.results_table.setItem(r_idx, 5, QTableWidgetItem(res.expected_value or "—"))

            # Col 6: Deviation
            self.results_table.setItem(r_idx, 6, QTableWidgetItem(res.deviation or "None"))

            # Col 7: Duration
            self.results_table.setItem(r_idx, 7, QTableWidgetItem(f"{res.duration_ms} ms"))

            # Col 8: Action button
            btn = QPushButton("Details...")
            btn.setObjectName("SecondaryButton")
            btn.setStyleSheet("padding: 2px 8px; font-size: 11px;")
            btn.clicked.connect(lambda _, r=res: self._open_result_details(r))
            self.results_table.setCellWidget(r_idx, 8, btn)

    def _clear_drawer(self) -> None:
        self._active_run = None
        self.drawer_title.setText("Selected Run Details: (None Selected)")
        self.results_table.setRowCount(0)
        self.results_table.hide()
        self.empty_results_label.show()

    def _apply_filters(self) -> None:
        query = self.search_input.text().strip().lower()
        filter_mode = self.status_filter_combo.currentIndex()

        for row_idx in range(self.runs_table.rowCount()):
            if row_idx >= len(self._runs):
                continue
            run = self._runs[row_idx]

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

            # Search query filter
            query_match = True
            if query:
                blob = f"#{run.id} {run.started_at_display} {st_val} {run.duration_display}".lower()
                query_match = query in blob

            self.runs_table.setRowHidden(row_idx, not (status_match and query_match))

    def _handle_result_double_clicked(self, row: int, _col: int) -> None:
        if self._active_run and 0 <= row < len(self._active_run.results):
            self._open_result_details(self._active_run.results[row])

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
            idx_b = selected_rows[0].row()
            idx_a = selected_rows[1].row()
            run_b = self._runs[idx_b]
            run_a = self._runs[idx_a]

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
