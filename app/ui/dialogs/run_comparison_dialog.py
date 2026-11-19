"""Dialog presenting side-by-side run comparison and regression diff (Stage 14)."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QDialog,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.core.status import NotificationLevel, ValidationStatus
from app.services.compare_service import (
    RuleComparisonDTO,
    RunComparisonDTO,
    compare_validation_runs,
    export_comparison_to_csv,
)
from app.services.orchestrator_service import ValidationRunSummaryDTO
from app.ui.widgets.notification_banner import NotificationBanner


def make_change_table_item(change_type: str) -> QTableWidgetItem:
    """Create a crisp, bold, colorful table item for change classification (no widget shrink)."""
    item = QTableWidgetItem(change_type)
    item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
    font = item.font()
    font.setBold(True)
    font.setPointSize(10)
    item.setFont(font)

    if change_type == "REGRESSION":
        item.setForeground(QColor("#B91C1C"))
        item.setBackground(QColor("#FEE2E2"))
    elif change_type == "IMPROVEMENT":
        item.setForeground(QColor("#15803D"))
        item.setBackground(QColor("#DCFCE7"))
    elif change_type == "NEW":
        item.setForeground(QColor("#1D4ED8"))
        item.setBackground(QColor("#DBEAFE"))
    elif change_type == "REMOVED":
        item.setForeground(QColor("#475569"))
        item.setBackground(QColor("#F1F5F9"))
    else:
        item.setForeground(QColor("#64748B"))
        item.setBackground(QColor("#F8FAFC"))
    return item


def make_status_table_item(status: ValidationStatus | str | None) -> QTableWidgetItem:
    """Create a crisp, bold, colorful table item for validation status (no widget shrink)."""
    if not status:
        item = QTableWidgetItem("—")
        item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        item.setForeground(QColor("#94A3B8"))
        return item

    st_val = status.value if isinstance(status, ValidationStatus) else str(status).upper()
    item = QTableWidgetItem(st_val)
    item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
    font = item.font()
    font.setBold(True)
    font.setPointSize(10)
    item.setFont(font)

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
    return item


def make_change_pill(change_type: str) -> QLabel:
    """Backwards-compatible change pill widget."""
    pill = QLabel(f" {change_type} ")
    pill.setAlignment(Qt.AlignmentFlag.AlignCenter)
    pill.setFixedHeight(22)
    pill.setMinimumWidth(80)

    if change_type == "REGRESSION":
        bg = "#FEE2E2"
        color = "#B91C1C"
        border = "#FCA5A5"
    elif change_type == "IMPROVEMENT":
        bg = "#DCFCE7"
        color = "#15803D"
        border = "#86EFAC"
    elif change_type == "NEW":
        bg = "#DBEAFE"
        color = "#1D4ED8"
        border = "#93C5FD"
    elif change_type == "REMOVED":
        bg = "#F1F5F9"
        color = "#475569"
        border = "#CBD5E1"
    else:
        bg = "#F8FAFC"
        color = "#64748B"
        border = "#E2E8F0"

    pill.setStyleSheet(
        f"background-color: {bg}; color: {color}; border: 1.5px solid {border}; "
        "border-radius: 4px; font-weight: 700; font-size: 11px; padding: 2px 6px;"
    )
    return pill


class RunComparisonDialog(QDialog):
    """Side-by-side comparison of two validation runs highlighting regressions and improvements."""

    def __init__(
        self,
        comparison: RunComparisonDTO,
        all_runs: list[ValidationRunSummaryDTO] | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._cmp = comparison
        self._all_runs: list[ValidationRunSummaryDTO] = (
            list(all_runs) if all_runs else [comparison.run_a, comparison.run_b]
        )
        self._current_filter_change = "ALL"
        self._current_search_query = ""

        self.setWindowTitle(
            f"Run Comparison — Run #{comparison.run_a.id} vs Run #{comparison.run_b.id}"
        )
        self.setMinimumSize(1000, 620)
        self.resize(1120, 680)
        self._build_ui()
        self._populate_comparison(self._cmp)

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(14)

        # Header Title and Subtitle Block
        header_block = QVBoxLayout()
        header_block.setSpacing(4)
        self.title_label = QLabel(
            f"Validation Run Comparison: #{self._cmp.run_a.id} vs #{self._cmp.run_b.id}"
        )
        self.title_label.setObjectName("SectionTitle")
        self.title_label.setStyleSheet("font-size: 17px; font-weight: 700; color: #0F172A;")
        header_block.addWidget(self.title_label)

        self.sub_label = QLabel(
            f"Baseline Run A: #{self._cmp.run_a.id} ({self._cmp.run_a.started_at_display}, {self._cmp.run_a.overall_status.value})  ➔  "
            f"Target Run B: #{self._cmp.run_b.id} ({self._cmp.run_b.started_at_display}, {self._cmp.run_b.overall_status.value})"
        )
        self.sub_label.setStyleSheet("font-size: 12px; color: #64748B;")
        header_block.addWidget(self.sub_label)
        layout.addLayout(header_block)

        # Notification Banner (for export notifications)
        self.banner = NotificationBanner(self)
        layout.addWidget(self.banner)

        # Run Selector Toolbar Card (if multiple runs are available)
        sel_card = QFrame()
        sel_card.setObjectName("Card")
        sel_card.setStyleSheet(
            "background-color: #FFFFFF; border: 1px solid #E2E8F0; border-radius: 8px; padding: 10px;"
        )
        sel_layout = QHBoxLayout(sel_card)
        sel_layout.setContentsMargins(12, 10, 12, 10)
        sel_layout.setSpacing(12)

        lbl_a = QLabel("Baseline (Run A):")
        lbl_a.setStyleSheet("font-size: 12px; font-weight: 600; color: #334155;")
        sel_layout.addWidget(lbl_a)

        self.combo_run_a = QComboBox()
        self.combo_run_a.setMinimumWidth(220)
        self.combo_run_a.setStyleSheet("padding: 4px 8px; font-size: 12px;")
        sel_layout.addWidget(self.combo_run_a)

        self.btn_swap = QPushButton("⇄ Swap Runs")
        self.btn_swap.setObjectName("SecondaryButton")
        self.btn_swap.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_swap.setToolTip("Swap Baseline Run A and Target Run B")
        self.btn_swap.clicked.connect(self._handle_swap_runs)
        sel_layout.addWidget(self.btn_swap)

        lbl_b = QLabel("Target (Run B):")
        lbl_b.setStyleSheet("font-size: 12px; font-weight: 600; color: #334155;")
        sel_layout.addWidget(lbl_b)

        self.combo_run_b = QComboBox()
        self.combo_run_b.setMinimumWidth(220)
        self.combo_run_b.setStyleSheet("padding: 4px 8px; font-size: 12px;")
        sel_layout.addWidget(self.combo_run_b)

        sel_layout.addStretch(1)
        layout.addWidget(sel_card)

        # Populate run dropdowns
        self._populate_run_combos()
        self.combo_run_a.currentIndexChanged.connect(self._on_run_selection_changed)
        self.combo_run_b.currentIndexChanged.connect(self._on_run_selection_changed)

        # 4 Interactive KPI Summary Cards
        kpi_row = QHBoxLayout()
        kpi_row.setSpacing(10)

        # Regressions Card
        self.c_reg = QFrame()
        self.c_reg.setCursor(Qt.CursorShape.PointingHandCursor)
        self.c_reg.setStyleSheet("background-color: #FEF2F2; border: 1.5px solid #FCA5A5; border-radius: 8px; padding: 6px;")
        lay_reg = QVBoxLayout(self.c_reg)
        lay_reg.setContentsMargins(10, 8, 10, 8)
        lay_reg.setSpacing(2)
        lbl_r_t = QLabel("REGRESSIONS")
        lbl_r_t.setStyleSheet("font-size: 11px; font-weight: 700; color: #B91C1C;")
        lay_reg.addWidget(lbl_r_t)
        self.lbl_r_c = QLabel(str(self._cmp.regressions_count))
        self.lbl_r_c.setStyleSheet("font-size: 20px; font-weight: 700; color: #B91C1C;")
        lay_reg.addWidget(self.lbl_r_c)
        lbl_r_sub = QLabel("Worsened checks (Click to filter)")
        lbl_r_sub.setStyleSheet("font-size: 10px; color: #991B1B;")
        lay_reg.addWidget(lbl_r_sub)
        self.c_reg.mousePressEvent = lambda _e: self._filter_by_card("REGRESSION")
        kpi_row.addWidget(self.c_reg, stretch=1)

        # Improvements Card
        self.c_imp = QFrame()
        self.c_imp.setCursor(Qt.CursorShape.PointingHandCursor)
        self.c_imp.setStyleSheet("background-color: #F0FDF4; border: 1.5px solid #86EFAC; border-radius: 8px; padding: 6px;")
        lay_imp = QVBoxLayout(self.c_imp)
        lay_imp.setContentsMargins(10, 8, 10, 8)
        lay_imp.setSpacing(2)
        lbl_i_t = QLabel("IMPROVEMENTS")
        lbl_i_t.setStyleSheet("font-size: 11px; font-weight: 700; color: #15803D;")
        lay_imp.addWidget(lbl_i_t)
        self.lbl_i_c = QLabel(str(self._cmp.improvements_count))
        self.lbl_i_c.setStyleSheet("font-size: 20px; font-weight: 700; color: #15803D;")
        lay_imp.addWidget(self.lbl_i_c)
        lbl_i_sub = QLabel("Resolved checks (Click to filter)")
        lbl_i_sub.setStyleSheet("font-size: 10px; color: #166534;")
        lay_imp.addWidget(lbl_i_sub)
        self.c_imp.mousePressEvent = lambda _e: self._filter_by_card("IMPROVEMENT")
        kpi_row.addWidget(self.c_imp, stretch=1)

        # Unchanged Card
        self.c_unc = QFrame()
        self.c_unc.setCursor(Qt.CursorShape.PointingHandCursor)
        self.c_unc.setStyleSheet("background-color: #F8FAFC; border: 1px solid #CBD5E1; border-radius: 8px; padding: 6px;")
        lay_unc = QVBoxLayout(self.c_unc)
        lay_unc.setContentsMargins(10, 8, 10, 8)
        lay_unc.setSpacing(2)
        lbl_u_t = QLabel("UNCHANGED")
        lbl_u_t.setStyleSheet("font-size: 11px; font-weight: 700; color: #475569;")
        lay_unc.addWidget(lbl_u_t)
        self.lbl_u_c = QLabel(str(self._cmp.unchanged_count))
        self.lbl_u_c.setStyleSheet("font-size: 20px; font-weight: 700; color: #475569;")
        lay_unc.addWidget(self.lbl_u_c)
        lbl_u_sub = QLabel("Identical status (Click to filter)")
        lbl_u_sub.setStyleSheet("font-size: 10px; color: #64748B;")
        lay_unc.addWidget(lbl_u_sub)
        self.c_unc.mousePressEvent = lambda _e: self._filter_by_card("UNCHANGED")
        kpi_row.addWidget(self.c_unc, stretch=1)

        # New / Removed Card
        self.c_mod = QFrame()
        self.c_mod.setCursor(Qt.CursorShape.PointingHandCursor)
        self.c_mod.setStyleSheet("background-color: #EFF6FF; border: 1px solid #93C5FD; border-radius: 8px; padding: 6px;")
        lay_mod = QVBoxLayout(self.c_mod)
        lay_mod.setContentsMargins(10, 8, 10, 8)
        lay_mod.setSpacing(2)
        lbl_m_t = QLabel("NEW / REMOVED RULES")
        lbl_m_t.setStyleSheet("font-size: 11px; font-weight: 700; color: #1D4ED8;")
        lay_mod.addWidget(lbl_m_t)
        self.lbl_m_c = QLabel(f"+{self._cmp.new_rules_count} / -{self._cmp.removed_rules_count}")
        self.lbl_m_c.setStyleSheet("font-size: 20px; font-weight: 700; color: #1D4ED8;")
        lay_mod.addWidget(self.lbl_m_c)
        lbl_m_sub = QLabel("Added or removed (Click to filter)")
        lbl_m_sub.setStyleSheet("font-size: 10px; color: #1E40AF;")
        lay_mod.addWidget(lbl_m_sub)
        self.c_mod.mousePressEvent = lambda _e: self._filter_by_card("MODIFIED")
        kpi_row.addWidget(self.c_mod, stretch=1)

        layout.addLayout(kpi_row)

        # Universal Search & Filter Bar
        filter_bar = QHBoxLayout()
        filter_bar.setSpacing(10)

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("🔍  Search rules, tables, or measures...")
        self.search_input.setClearButtonEnabled(True)
        self.search_input.setStyleSheet("padding: 6px 10px; font-size: 12px; border-radius: 6px; border: 1px solid #CBD5E1;")
        self.search_input.textChanged.connect(self._on_search_text_changed)
        filter_bar.addWidget(self.search_input, stretch=2)

        lbl_f = QLabel("Filter:")
        lbl_f.setStyleSheet("font-size: 12px; font-weight: 600; color: #475569;")
        filter_bar.addWidget(lbl_f)

        self.combo_filter = QComboBox()
        self.combo_filter.setStyleSheet("padding: 5px 8px; font-size: 12px;")
        self.combo_filter.addItem("All Changes", "ALL")
        self.combo_filter.addItem("Regressions Only", "REGRESSION")
        self.combo_filter.addItem("Improvements Only", "IMPROVEMENT")
        self.combo_filter.addItem("New Rules Only", "NEW")
        self.combo_filter.addItem("Removed Rules Only", "REMOVED")
        self.combo_filter.addItem("Unchanged Only", "UNCHANGED")
        self.combo_filter.currentIndexChanged.connect(self._on_filter_changed)
        filter_bar.addWidget(self.combo_filter, stretch=1)

        self.btn_clear_filters = QPushButton("Reset Filter")
        self.btn_clear_filters.setObjectName("SecondaryButton")
        self.btn_clear_filters.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_clear_filters.clicked.connect(self._handle_reset_filters)
        filter_bar.addWidget(self.btn_clear_filters)

        layout.addLayout(filter_bar)

        # Diff Table
        self.diff_table = QTableWidget()
        self.diff_table.setObjectName("DataTable")
        self.diff_table.setColumnCount(8)
        self._update_table_headers()

        header = self.diff_table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        header.setMinimumSectionSize(75)

        self.diff_table.setColumnWidth(0, 120)  # Change (NEW, REGRESSION, etc.)
        self.diff_table.setColumnWidth(1, 240)  # Rule Name
        self.diff_table.setColumnWidth(2, 180)  # Target
        self.diff_table.setColumnWidth(3, 110)  # Run #A Status
        self.diff_table.setColumnWidth(4, 110)  # Run #B Status
        self.diff_table.setColumnWidth(5, 140)  # Run #A Actual
        self.diff_table.setColumnWidth(6, 140)  # Run #B Actual
        self.diff_table.setColumnWidth(7, 140)  # Run #B Deviation

        self.diff_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.diff_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.diff_table.setAlternatingRowColors(True)
        self.diff_table.verticalHeader().setVisible(False)
        self.diff_table.verticalHeader().setDefaultSectionSize(34)
        self.diff_table.setSortingEnabled(True)

        layout.addWidget(self.diff_table, stretch=1)

        # Footer Actions Bar
        footer = QHBoxLayout()
        self.lbl_stats = QLabel()
        self.lbl_stats.setStyleSheet("font-size: 12px; color: #64748B;")
        footer.addWidget(self.lbl_stats)

        footer.addStretch(1)

        self.btn_export = QPushButton("📥  Export Diff to CSV...")
        self.btn_export.setObjectName("SecondaryButton")
        self.btn_export.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_export.clicked.connect(self._handle_export_csv)
        footer.addWidget(self.btn_export)

        btn_close = QPushButton("Close")
        btn_close.setObjectName("PrimaryButton")
        btn_close.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_close.clicked.connect(self.accept)
        footer.addWidget(btn_close)

        layout.addLayout(footer)

    def _populate_run_combos(self) -> None:
        self.combo_run_a.blockSignals(True)
        self.combo_run_b.blockSignals(True)
        self.combo_run_a.clear()
        self.combo_run_b.clear()

        idx_a = 0
        idx_b = 0
        for idx, r in enumerate(self._all_runs):
            label = f"Run #{r.id}  •  {r.started_at_display}  ({r.overall_status.value})"
            self.combo_run_a.addItem(label, r.id)
            self.combo_run_b.addItem(label, r.id)
            if r.id == self._cmp.run_a.id:
                idx_a = idx
            if r.id == self._cmp.run_b.id:
                idx_b = idx

        self.combo_run_a.setCurrentIndex(idx_a)
        self.combo_run_b.setCurrentIndex(idx_b)
        self.combo_run_a.blockSignals(False)
        self.combo_run_b.blockSignals(False)

    def _handle_swap_runs(self) -> None:
        idx_a = self.combo_run_a.currentIndex()
        idx_b = self.combo_run_b.currentIndex()
        self.combo_run_a.setCurrentIndex(idx_b)
        self.combo_run_b.setCurrentIndex(idx_a)

    def _on_run_selection_changed(self) -> None:
        id_a = self.combo_run_a.currentData()
        id_b = self.combo_run_b.currentData()
        if id_a is None or id_b is None:
            return

        run_a = next((r for r in self._all_runs if r.id == id_a), None)
        run_b = next((r for r in self._all_runs if r.id == id_b), None)
        if not run_a or not run_b:
            return

        new_cmp = compare_validation_runs(run_a, run_b)
        self._cmp = new_cmp
        self.setWindowTitle(f"Run Comparison — Run #{run_a.id} vs Run #{run_b.id}")
        self.title_label.setText(f"Validation Run Comparison: #{run_a.id} vs #{run_b.id}")
        self.sub_label.setText(
            f"Baseline Run A: #{run_a.id} ({run_a.started_at_display}, {run_a.overall_status.value})  ➔  "
            f"Target Run B: #{run_b.id} ({run_b.started_at_display}, {run_b.overall_status.value})"
        )
        self._update_table_headers()
        self._populate_comparison(new_cmp)

    def _update_table_headers(self) -> None:
        self.diff_table.setHorizontalHeaderLabels([
            "Change",
            "Rule Name",
            "Target",
            f"Run #{self._cmp.run_a.id}",
            f"Run #{self._cmp.run_b.id}",
            f"Run #{self._cmp.run_a.id} Actual",
            f"Run #{self._cmp.run_b.id} Actual",
            f"Run #{self._cmp.run_b.id} Deviation",
        ])

    def _populate_comparison(self, cmp: RunComparisonDTO) -> None:
        # Update KPI labels
        self.lbl_r_c.setText(str(cmp.regressions_count))
        self.lbl_i_c.setText(str(cmp.improvements_count))
        self.lbl_u_c.setText(str(cmp.unchanged_count))
        self.lbl_m_c.setText(f"+{cmp.new_rules_count} / -{cmp.removed_rules_count}")

        # Update table rows
        self.diff_table.setSortingEnabled(False)
        self.diff_table.setRowCount(len(cmp.rule_comparisons))

        for row_idx, item in enumerate(cmp.rule_comparisons):
            # Col 0: Change
            it_change = make_change_table_item(item.change_type)
            self.diff_table.setItem(row_idx, 0, it_change)

            # Col 1: Rule Name
            it_name = QTableWidgetItem(item.rule_name)
            self.diff_table.setItem(row_idx, 1, it_name)

            # Col 2: Target
            it_target = QTableWidgetItem(item.target_display)
            self.diff_table.setItem(row_idx, 2, it_target)

            # Col 3: Status A
            self.diff_table.setItem(row_idx, 3, make_status_table_item(item.status_a))

            # Col 4: Status B
            self.diff_table.setItem(row_idx, 4, make_status_table_item(item.status_b))

            # Col 5: Actual A
            self.diff_table.setItem(row_idx, 5, QTableWidgetItem(item.actual_a or "—"))

            # Col 6: Actual B
            self.diff_table.setItem(row_idx, 6, QTableWidgetItem(item.actual_b or "—"))

            # Col 7: Deviation B
            dev_str = item.deviation_b
            if not dev_str or dev_str == "None":
                dev_str = "—"
            it_dev = QTableWidgetItem(dev_str)
            it_dev.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.diff_table.setItem(row_idx, 7, it_dev)

        self.diff_table.setSortingEnabled(True)
        self._apply_filters()

    def _filter_by_card(self, change_type: str) -> None:
        if change_type == "MODIFIED":
            # Match either NEW or REMOVED
            self._current_filter_change = "MODIFIED"
        else:
            self._current_filter_change = change_type

        # Sync combo index
        idx = self.combo_filter.findData(change_type)
        if idx >= 0:
            self.combo_filter.blockSignals(True)
            self.combo_filter.setCurrentIndex(idx)
            self.combo_filter.blockSignals(False)

        self._apply_filters()

    def _on_filter_changed(self) -> None:
        self._current_filter_change = str(self.combo_filter.currentData() or "ALL")
        self._apply_filters()

    def _on_search_text_changed(self, text: str) -> None:
        self._current_search_query = text.strip().lower()
        self._apply_filters()

    def _handle_reset_filters(self) -> None:
        self.search_input.clear()
        self.combo_filter.setCurrentIndex(0)
        self._current_filter_change = "ALL"
        self._current_search_query = ""
        self._apply_filters()

    def _apply_filters(self) -> None:
        total_rows = self.diff_table.rowCount()
        visible_rows = 0

        for row in range(total_rows):
            ch_item = self.diff_table.item(row, 0)
            name_item = self.diff_table.item(row, 1)
            target_item = self.diff_table.item(row, 2)

            ch_text = (ch_item.text() if ch_item else "").upper()
            name_text = (name_item.text() if name_item else "").lower()
            target_text = (target_item.text() if target_item else "").lower()

            # 1. Change type filter
            match_change = True
            if self._current_filter_change == "MODIFIED":
                match_change = ch_text in ("NEW", "REMOVED")
            elif self._current_filter_change != "ALL":
                match_change = ch_text == self._current_filter_change

            # 2. Search query filter
            match_search = True
            if self._current_search_query:
                match_search = (
                    self._current_search_query in name_text
                    or self._current_search_query in target_text
                )

            should_show = match_change and match_search
            self.diff_table.setRowHidden(row, not should_show)
            if should_show:
                visible_rows += 1

        self.lbl_stats.setText(f"Showing {visible_rows} of {total_rows} rule comparison(s)")

    def _handle_export_csv(self) -> None:
        default_name = f"comparison_run_{self._cmp.run_a.id}_vs_{self._cmp.run_b.id}.csv"
        filename, _ = QFileDialog.getSaveFileName(
            self,
            "Export Run Comparison to CSV",
            str(Path.home() / default_name),
            "CSV Files (*.csv);;All Files (*.*)",
        )
        if not filename:
            return

        try:
            dest = export_comparison_to_csv(self._cmp, filename)
            self.banner.show_message(
                f"Comparison report exported successfully to '{dest.name}'.",
                level=NotificationLevel.SUCCESS,
                title="Export Complete",
            )
        except Exception as exc:
            self.banner.show_message(
                f"Failed to export comparison: {exc}",
                level=NotificationLevel.ERROR,
                title="Export Error",
            )
