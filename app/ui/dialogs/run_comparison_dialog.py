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
        item = QTableWidgetItem("-")
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
    """Side-by-side comparison across 2 to 4 validation runs highlighting regressions and improvements."""

    def __init__(
        self,
        comparison: RunComparisonDTO,
        all_runs: list[ValidationRunSummaryDTO] | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._cmp = comparison
        self._all_runs: list[ValidationRunSummaryDTO] = (
            list(all_runs) if all_runs else list(comparison.active_runs)
        )
        self._current_filter_change = "ALL"
        self._current_search_query = ""

        run_ids_str = " vs ".join(f"Run #{r.id}" for r in comparison.active_runs)
        self.setWindowTitle(f"Run Comparison: {run_ids_str}")
        self.setMinimumSize(1000, 620)
        self.resize(1180, 700)
        self._build_ui()
        self._populate_comparison(self._cmp)

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(14)

        # Header Title and Subtitle Block
        header_block = QVBoxLayout()
        header_block.setSpacing(4)
        run_titles = " vs ".join(f"#{r.id}" for r in self._cmp.active_runs)
        self.title_label = QLabel(f"Validation Run Comparison: {run_titles}")
        self.title_label.setObjectName("SectionTitle")
        self.title_label.setStyleSheet("font-size: 17px; font-weight: 700; color: #0F172A;")
        header_block.addWidget(self.title_label)

        sub_parts = [
            f"Run #{r.id} ({r.started_at_display}, {r.overall_status.value})"
            for r in self._cmp.active_runs
        ]
        self.sub_label = QLabel("  ➔  ".join(sub_parts))
        self.sub_label.setStyleSheet("font-size: 12px; color: #64748B;")
        header_block.addWidget(self.sub_label)
        layout.addLayout(header_block)

        # Notification Banner (for export notifications)
        self.banner = NotificationBanner(self)
        layout.addWidget(self.banner)

        # Run Selector Toolbar Card (supporting 2 compulsory runs and 2 optional runs)
        sel_card = QFrame()
        sel_card.setObjectName("ComparisonSelectorCard")
        sel_card.setStyleSheet(
            "QFrame#ComparisonSelectorCard { background-color: #FFFFFF; border: 1px solid #E2E8F0; border-radius: 8px; } "
            "QLabel { border: none; background: transparent; }"
        )
        sel_layout = QVBoxLayout(sel_card)
        sel_layout.setContentsMargins(14, 10, 14, 10)
        sel_layout.setSpacing(8)

        # Row 1: Compulsory Run 1 and Run 2
        row1 = QHBoxLayout()
        row1.setSpacing(10)

        lbl_a = QLabel("Run 1 (Baseline)*:")
        lbl_a.setStyleSheet("font-size: 12px; font-weight: 600; color: #1E293B;")
        row1.addWidget(lbl_a)

        self.combo_run_a = QComboBox()
        self.combo_run_a.setMinimumWidth(220)
        self.combo_run_a.setToolTip("Select the baseline validation run to compare from.")
        self.combo_run_a.setStyleSheet("padding: 4px 8px; font-size: 12px;")
        row1.addWidget(self.combo_run_a)

        self.btn_swap = QPushButton("⇄ Swap 1 & 2")
        self.btn_swap.setObjectName("SecondaryButton")
        self.btn_swap.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_swap.setToolTip("Swap Run 1 (Baseline) and Run 2 (Target).")
        self.btn_swap.clicked.connect(self._handle_swap_runs)
        row1.addWidget(self.btn_swap)

        lbl_b = QLabel("Run 2 (Target)*:")
        lbl_b.setStyleSheet("font-size: 12px; font-weight: 600; color: #1E293B;")
        row1.addWidget(lbl_b)

        self.combo_run_b = QComboBox()
        self.combo_run_b.setMinimumWidth(220)
        self.combo_run_b.setToolTip("Select the target validation run to compare against.")
        self.combo_run_b.setStyleSheet("padding: 4px 8px; font-size: 12px;")
        row1.addWidget(self.combo_run_b)

        row1.addStretch(1)
        sel_layout.addLayout(row1)

        # Row 2: Optional Run 3 and Run 4
        row2 = QHBoxLayout()
        row2.setSpacing(10)

        lbl_c = QLabel("Run 3 (Optional):")
        lbl_c.setStyleSheet("font-size: 12px; font-weight: 500; color: #64748B;")
        row2.addWidget(lbl_c)

        self.combo_run_c = QComboBox()
        self.combo_run_c.setMinimumWidth(220)
        self.combo_run_c.setToolTip("Optional third validation run to track changes across 3 runs.")
        self.combo_run_c.setStyleSheet("padding: 4px 8px; font-size: 12px;")
        row2.addWidget(self.combo_run_c)

        lbl_d = QLabel("Run 4 (Optional):")
        lbl_d.setStyleSheet("font-size: 12px; font-weight: 500; color: #64748B;")
        row2.addWidget(lbl_d)

        self.combo_run_d = QComboBox()
        self.combo_run_d.setMinimumWidth(220)
        self.combo_run_d.setToolTip("Optional fourth validation run to track changes across 4 runs.")
        self.combo_run_d.setStyleSheet("padding: 4px 8px; font-size: 12px;")
        row2.addWidget(self.combo_run_d)

        self.btn_clear_optional = QPushButton("✕ Reset (3 & 4)")
        self.btn_clear_optional.setObjectName("SecondaryButton")
        self.btn_clear_optional.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_clear_optional.setToolTip("Reset optional Run 3 and Run 4 to None.")
        self.btn_clear_optional.clicked.connect(self._handle_clear_optional)
        row2.addWidget(self.btn_clear_optional)

        row2.addStretch(1)
        sel_layout.addLayout(row2)

        layout.addWidget(sel_card)

        # Populate run dropdowns
        self._populate_run_combos()
        self.combo_run_a.currentIndexChanged.connect(self._on_run_selection_changed)
        self.combo_run_b.currentIndexChanged.connect(self._on_run_selection_changed)
        self.combo_run_c.currentIndexChanged.connect(self._on_run_selection_changed)
        self.combo_run_d.currentIndexChanged.connect(self._on_run_selection_changed)

        # 4 Interactive KPI Summary Cards
        kpi_row = QHBoxLayout()
        kpi_row.setSpacing(10)

        # 1. Worsened Card (formerly Regressions)
        self.c_reg = QFrame()
        self.c_reg.setObjectName("CardReg")
        self.c_reg.setCursor(Qt.CursorShape.PointingHandCursor)
        self.c_reg.setStyleSheet(
            "QFrame#CardReg { background-color: #FEF2F2; border: 1px solid #FECACA; border-radius: 8px; } "
            "QFrame#CardReg:hover { background-color: #FEE2E2; border-color: #F87171; } "
            "QLabel { border: none; background: transparent; }"
        )
        lay_reg = QVBoxLayout(self.c_reg)
        lay_reg.setContentsMargins(14, 12, 14, 12)
        lay_reg.setSpacing(4)

        head_reg = QHBoxLayout()
        head_reg.setContentsMargins(0, 0, 0, 0)
        head_reg.setSpacing(6)
        lbl_r_t = QLabel("WORSENED")
        lbl_r_t.setStyleSheet("font-size: 11px; font-weight: 700; color: #B91C1C; letter-spacing: 0.5px;")
        head_reg.addWidget(lbl_r_t)

        tip_worsened = "Checks that previously passed or had no issues, but failed or degraded in recent runs."
        btn_r_info = QPushButton("i")
        btn_r_info.setFixedSize(16, 16)
        btn_r_info.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_r_info.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        btn_r_info.setToolTip(tip_worsened)
        btn_r_info.setStyleSheet(
            "QPushButton { border: 1px solid #FCA5A5; border-radius: 8px; "
            "font-size: 10px; font-weight: 700; font-family: Segoe UI, sans-serif; "
            "color: #B91C1C; background: #FFFFFF; padding: 0; margin: 0; } "
            "QPushButton:hover { background: #FEE2E2; border-color: #EF4444; }"
        )
        btn_r_info.clicked.connect(lambda: self._filter_by_card("REGRESSION"))
        head_reg.addWidget(btn_r_info)
        head_reg.addStretch()
        lay_reg.addLayout(head_reg)

        self.lbl_r_c = QLabel(str(self._cmp.regressions_count))
        self.lbl_r_c.setStyleSheet("font-size: 24px; font-weight: 700; color: #B91C1C;")
        lay_reg.addWidget(self.lbl_r_c)
        lbl_r_sub = QLabel("Worsened checks (Click to filter)")
        lbl_r_sub.setStyleSheet("font-size: 11px; color: #991B1B;")
        lay_reg.addWidget(lbl_r_sub)
        self.c_reg.mousePressEvent = lambda _e: self._filter_by_card("REGRESSION")
        self.c_reg.setToolTip(tip_worsened)
        kpi_row.addWidget(self.c_reg, stretch=1)

        # 2. Improvements Card
        self.c_imp = QFrame()
        self.c_imp.setObjectName("CardImp")
        self.c_imp.setCursor(Qt.CursorShape.PointingHandCursor)
        self.c_imp.setStyleSheet(
            "QFrame#CardImp { background-color: #F0FDF4; border: 1px solid #BBF7D0; border-radius: 8px; } "
            "QFrame#CardImp:hover { background-color: #DCFCE7; border-color: #4ADE80; } "
            "QLabel { border: none; background: transparent; }"
        )
        lay_imp = QVBoxLayout(self.c_imp)
        lay_imp.setContentsMargins(14, 12, 14, 12)
        lay_imp.setSpacing(4)

        head_imp = QHBoxLayout()
        head_imp.setContentsMargins(0, 0, 0, 0)
        head_imp.setSpacing(6)
        lbl_i_t = QLabel("IMPROVEMENTS")
        lbl_i_t.setStyleSheet("font-size: 11px; font-weight: 700; color: #15803D; letter-spacing: 0.5px;")
        head_imp.addWidget(lbl_i_t)

        tip_improvements = "Checks that previously failed or had errors, but are now passing in recent runs."
        btn_i_info = QPushButton("i")
        btn_i_info.setFixedSize(16, 16)
        btn_i_info.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_i_info.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        btn_i_info.setToolTip(tip_improvements)
        btn_i_info.setStyleSheet(
            "QPushButton { border: 1px solid #86EFAC; border-radius: 8px; "
            "font-size: 10px; font-weight: 700; font-family: Segoe UI, sans-serif; "
            "color: #15803D; background: #FFFFFF; padding: 0; margin: 0; } "
            "QPushButton:hover { background: #DCFCE7; border-color: #22C55E; }"
        )
        btn_i_info.clicked.connect(lambda: self._filter_by_card("IMPROVEMENT"))
        head_imp.addWidget(btn_i_info)
        head_imp.addStretch()
        lay_imp.addLayout(head_imp)

        self.lbl_i_c = QLabel(str(self._cmp.improvements_count))
        self.lbl_i_c.setStyleSheet("font-size: 24px; font-weight: 700; color: #15803D;")
        lay_imp.addWidget(self.lbl_i_c)
        lbl_i_sub = QLabel("Resolved checks (Click to filter)")
        lbl_i_sub.setStyleSheet("font-size: 11px; color: #166534;")
        lay_imp.addWidget(lbl_i_sub)
        self.c_imp.mousePressEvent = lambda _e: self._filter_by_card("IMPROVEMENT")
        self.c_imp.setToolTip(tip_improvements)
        kpi_row.addWidget(self.c_imp, stretch=1)

        # 3. Unchanged Card
        self.c_unc = QFrame()
        self.c_unc.setObjectName("CardUnc")
        self.c_unc.setCursor(Qt.CursorShape.PointingHandCursor)
        self.c_unc.setStyleSheet(
            "QFrame#CardUnc { background-color: #FFFFFF; border: 1px solid #E2E8F0; border-radius: 8px; } "
            "QFrame#CardUnc:hover { background-color: #F8FAFC; border-color: #CBD5E1; } "
            "QLabel { border: none; background: transparent; }"
        )
        lay_unc = QVBoxLayout(self.c_unc)
        lay_unc.setContentsMargins(14, 12, 14, 12)
        lay_unc.setSpacing(4)

        head_unc = QHBoxLayout()
        head_unc.setContentsMargins(0, 0, 0, 0)
        head_unc.setSpacing(6)
        lbl_u_t = QLabel("UNCHANGED")
        lbl_u_t.setStyleSheet("font-size: 11px; font-weight: 700; color: #475569; letter-spacing: 0.5px;")
        head_unc.addWidget(lbl_u_t)

        tip_unchanged = "Checks whose validation status remained identical across all compared runs."
        btn_u_info = QPushButton("i")
        btn_u_info.setFixedSize(16, 16)
        btn_u_info.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_u_info.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        btn_u_info.setToolTip(tip_unchanged)
        btn_u_info.setStyleSheet(
            "QPushButton { border: 1px solid #CBD5E1; border-radius: 8px; "
            "font-size: 10px; font-weight: 700; font-family: Segoe UI, sans-serif; "
            "color: #475569; background: #FFFFFF; padding: 0; margin: 0; } "
            "QPushButton:hover { background: #F1F5F9; border-color: #94A3B8; }"
        )
        btn_u_info.clicked.connect(lambda: self._filter_by_card("UNCHANGED"))
        head_unc.addWidget(btn_u_info)
        head_unc.addStretch()
        lay_unc.addLayout(head_unc)

        self.lbl_u_c = QLabel(str(self._cmp.unchanged_count))
        self.lbl_u_c.setStyleSheet("font-size: 24px; font-weight: 700; color: #334155;")
        lay_unc.addWidget(self.lbl_u_c)
        lbl_u_sub = QLabel("Identical status (Click to filter)")
        lbl_u_sub.setStyleSheet("font-size: 11px; color: #94A3B8;")
        lay_unc.addWidget(lbl_u_sub)
        self.c_unc.mousePressEvent = lambda _e: self._filter_by_card("UNCHANGED")
        self.c_unc.setToolTip(tip_unchanged)
        kpi_row.addWidget(self.c_unc, stretch=1)

        # 4. New / Removed Card
        self.c_mod = QFrame()
        self.c_mod.setObjectName("CardMod")
        self.c_mod.setCursor(Qt.CursorShape.PointingHandCursor)
        self.c_mod.setStyleSheet(
            "QFrame#CardMod { background-color: #EFF6FF; border: 1px solid #BFDBFE; border-radius: 8px; } "
            "QFrame#CardMod:hover { background-color: #DBEAFE; border-color: #60A5FA; } "
            "QLabel { border: none; background: transparent; }"
        )
        lay_mod = QVBoxLayout(self.c_mod)
        lay_mod.setContentsMargins(14, 12, 14, 12)
        lay_mod.setSpacing(4)

        head_mod = QHBoxLayout()
        head_mod.setContentsMargins(0, 0, 0, 0)
        head_mod.setSpacing(6)
        lbl_m_t = QLabel("NEW / REMOVED RULES")
        lbl_m_t.setStyleSheet("font-size: 11px; font-weight: 700; color: #1D4ED8; letter-spacing: 0.5px;")
        head_mod.addWidget(lbl_m_t)

        tip_modified = "Validation rules that were newly added (+) or removed (-) between the compared runs."
        btn_m_info = QPushButton("i")
        btn_m_info.setFixedSize(16, 16)
        btn_m_info.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_m_info.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        btn_m_info.setToolTip(tip_modified)
        btn_m_info.setStyleSheet(
            "QPushButton { border: 1px solid #93C5FD; border-radius: 8px; "
            "font-size: 10px; font-weight: 700; font-family: Segoe UI, sans-serif; "
            "color: #1D4ED8; background: #FFFFFF; padding: 0; margin: 0; } "
            "QPushButton:hover { background: #DBEAFE; border-color: #3B82F6; }"
        )
        btn_m_info.clicked.connect(lambda: self._filter_by_card("MODIFIED"))
        head_mod.addWidget(btn_m_info)
        head_mod.addStretch()
        lay_mod.addLayout(head_mod)

        self.lbl_m_c = QLabel(f"+{self._cmp.new_rules_count} / -{self._cmp.removed_rules_count}")
        self.lbl_m_c.setStyleSheet("font-size: 24px; font-weight: 700; color: #1D4ED8;")
        lay_mod.addWidget(self.lbl_m_c)
        lbl_m_sub = QLabel("Added or removed (Click to filter)")
        lbl_m_sub.setStyleSheet("font-size: 11px; color: #1E40AF;")
        lay_mod.addWidget(lbl_m_sub)
        self.c_mod.mousePressEvent = lambda _e: self._filter_by_card("MODIFIED")
        self.c_mod.setToolTip(tip_modified)
        kpi_row.addWidget(self.c_mod, stretch=1)
        kpi_row.addWidget(self.c_mod, stretch=1)

        layout.addLayout(kpi_row)

        # Universal Search & Filter Bar
        filter_bar = QHBoxLayout()
        filter_bar.setSpacing(10)

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("🔍  Search rules, tables, or measures...")
        self.search_input.setToolTip("Filter comparison table by rule name, table, column, or measure.")
        self.search_input.setClearButtonEnabled(True)
        self.search_input.setStyleSheet("padding: 6px 10px; font-size: 12px; border-radius: 6px; border: 1px solid #CBD5E1;")
        self.search_input.textChanged.connect(self._on_search_text_changed)
        filter_bar.addWidget(self.search_input, stretch=2)

        lbl_f = QLabel("Filter:")
        lbl_f.setStyleSheet("font-size: 12px; font-weight: 600; color: #475569;")
        filter_bar.addWidget(lbl_f)

        self.combo_filter = QComboBox()
        self.combo_filter.setStyleSheet("padding: 5px 8px; font-size: 12px;")
        filter_options = [
            ("All Changes", "ALL", "Show all comparison rows across the selected runs."),
            ("Worsened Only", "REGRESSION", "Show only checks that degraded (passed previously, now failed/errored)."),
            ("Improvements Only", "IMPROVEMENT", "Show only checks that improved (failed previously, now passed)."),
            ("New Rules Only", "NEW", "Show only validation rules that were newly added."),
            ("Removed Rules Only", "REMOVED", "Show only validation rules that were deleted."),
            ("Unchanged Only", "UNCHANGED", "Show only checks whose status did not change."),
        ]
        for label, val, tip in filter_options:
            self.combo_filter.addItem(label, val)
            self.combo_filter.setItemData(self.combo_filter.count() - 1, tip, Qt.ItemDataRole.ToolTipRole)
        self.combo_filter.setToolTip("Filter comparison rows by change type.")
        self.combo_filter.currentIndexChanged.connect(self._on_filter_changed)
        filter_bar.addWidget(self.combo_filter, stretch=1)

        self.btn_clear_filters = QPushButton("Reset Filter")
        self.btn_clear_filters.setObjectName("SecondaryButton")
        self.btn_clear_filters.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_clear_filters.setToolTip("Reset search text and status filters to show all rules.")
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
        for combo in (self.combo_run_a, self.combo_run_b, self.combo_run_c, self.combo_run_d):
            combo.blockSignals(True)
            combo.clear()

        # Optional combos start with a (None - Skip) entry
        self.combo_run_c.addItem("(None - Skip)", None)
        self.combo_run_d.addItem("(None - Skip)", None)

        idx_a = 0
        idx_b = 0
        idx_c = 0
        idx_d = 0

        for idx, r in enumerate(self._all_runs):
            label = f"Run #{r.id}  •  {r.started_at_display}  ({r.overall_status.value})"
            self.combo_run_a.addItem(label, r.id)
            self.combo_run_b.addItem(label, r.id)
            self.combo_run_c.addItem(label, r.id)
            self.combo_run_d.addItem(label, r.id)

            if r.id == self._cmp.run_a.id:
                idx_a = idx
            if r.id == self._cmp.run_b.id:
                idx_b = idx
            if self._cmp.run_c and r.id == self._cmp.run_c.id:
                idx_c = idx + 1
            if self._cmp.run_d and r.id == self._cmp.run_d.id:
                idx_d = idx + 1

        self.combo_run_a.setCurrentIndex(idx_a)
        self.combo_run_b.setCurrentIndex(idx_b)
        self.combo_run_c.setCurrentIndex(idx_c)
        self.combo_run_d.setCurrentIndex(idx_d)

        for combo in (self.combo_run_a, self.combo_run_b, self.combo_run_c, self.combo_run_d):
            combo.blockSignals(False)

    def _handle_swap_runs(self) -> None:
        idx_a = self.combo_run_a.currentIndex()
        idx_b = self.combo_run_b.currentIndex()
        self.combo_run_a.setCurrentIndex(idx_b)
        self.combo_run_b.setCurrentIndex(idx_a)

    def _handle_clear_optional(self) -> None:
        self.combo_run_c.setCurrentIndex(0)
        self.combo_run_d.setCurrentIndex(0)

    def _on_run_selection_changed(self) -> None:
        id_a = self.combo_run_a.currentData()
        id_b = self.combo_run_b.currentData()
        id_c = self.combo_run_c.currentData()
        id_d = self.combo_run_d.currentData()

        if id_a is None or id_b is None:
            return

        run_a = next((r for r in self._all_runs if r.id == id_a), None)
        run_b = next((r for r in self._all_runs if r.id == id_b), None)
        run_c = next((r for r in self._all_runs if r.id == id_c), None) if id_c is not None else None
        run_d = next((r for r in self._all_runs if r.id == id_d), None) if id_d is not None else None

        if not run_a or not run_b:
            return

        new_cmp = compare_validation_runs(run_a, run_b, run_c, run_d)
        self._cmp = new_cmp

        run_ids_str = " vs ".join(f"Run #{r.id}" for r in new_cmp.active_runs)
        self.setWindowTitle(f"Run Comparison: {run_ids_str}")
        self.title_label.setText(
            f"Validation Run Comparison: {' vs '.join(f'#{r.id}' for r in new_cmp.active_runs)}"
        )
        sub_parts = [
            f"Run #{r.id} ({r.started_at_display}, {r.overall_status.value})"
            for r in new_cmp.active_runs
        ]
        self.sub_label.setText("  ➔  ".join(sub_parts))
        self._update_table_headers()
        self._populate_comparison(new_cmp)

    def _update_table_headers(self) -> None:
        active = self._cmp.active_runs
        headers = ["Change", "Rule Name", "Target"]
        for r in active:
            headers.append(f"Run #{r.id}")
        for r in active:
            headers.append(f"Run #{r.id} Actual")
        headers.append(f"Run #{self._cmp.run_b.id} Dev")

        self.diff_table.setColumnCount(len(headers))
        self.diff_table.setHorizontalHeaderLabels(headers)

        self.diff_table.setColumnWidth(0, 115)  # Change
        self.diff_table.setColumnWidth(1, 210)  # Rule Name
        self.diff_table.setColumnWidth(2, 160)  # Target
        col_idx = 3
        for _ in active:
            self.diff_table.setColumnWidth(col_idx, 100)
            col_idx += 1
        for _ in active:
            self.diff_table.setColumnWidth(col_idx, 125)
            col_idx += 1
        self.diff_table.setColumnWidth(col_idx, 125)

    def _populate_comparison(self, cmp: RunComparisonDTO) -> None:
        # Update KPI labels
        self.lbl_r_c.setText(str(cmp.regressions_count))
        self.lbl_i_c.setText(str(cmp.improvements_count))
        self.lbl_u_c.setText(str(cmp.unchanged_count))
        self.lbl_m_c.setText(f"+{cmp.new_rules_count} / -{cmp.removed_rules_count}")

        # Update table rows
        self.diff_table.setSortingEnabled(False)
        self.diff_table.setRowCount(len(cmp.rule_comparisons))

        active = cmp.active_runs
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

            # Statuses for active runs
            col_curr = 3
            for r in active:
                if r.id == cmp.run_a.id:
                    st = item.status_a
                elif r.id == cmp.run_b.id:
                    st = item.status_b
                elif cmp.run_c and r.id == cmp.run_c.id:
                    st = item.status_c
                elif cmp.run_d and r.id == cmp.run_d.id:
                    st = item.status_d
                else:
                    st = None
                self.diff_table.setItem(row_idx, col_curr, make_status_table_item(st))
                col_curr += 1

            # Actuals for active runs
            for r in active:
                if r.id == cmp.run_a.id:
                    act = item.actual_a
                elif r.id == cmp.run_b.id:
                    act = item.actual_b
                elif cmp.run_c and r.id == cmp.run_c.id:
                    act = item.actual_c
                elif cmp.run_d and r.id == cmp.run_d.id:
                    act = item.actual_d
                else:
                    act = None
                self.diff_table.setItem(row_idx, col_curr, QTableWidgetItem(act or "-"))
                col_curr += 1

            # Deviation for Target Run B
            dev_str = item.deviation_b
            if not dev_str or dev_str == "None":
                dev_str = "-"
            it_dev = QTableWidgetItem(dev_str)
            it_dev.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.diff_table.setItem(row_idx, col_curr, it_dev)

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
        active_ids = "_".join(str(r.id) for r in self._cmp.active_runs)
        default_name = f"comparison_runs_{active_ids}.csv"
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
