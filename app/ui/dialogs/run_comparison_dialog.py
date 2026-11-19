"""Dialog presenting side-by-side run comparison and regression diff (Stage 14)."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.core.status import ValidationStatus
from app.services.compare_service import RunComparisonDTO
from app.ui.dialogs.result_details_dialog import make_validation_status_pill


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
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._cmp = comparison
        self.setWindowTitle(
            f"Run Comparison — Run #{comparison.run_a.id} vs Run #{comparison.run_b.id}"
        )
        self.setMinimumSize(960, 580)
        self.resize(1080, 640)
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(14)

        # Header Title
        title = QLabel(f"Validation Run Comparison: #{self._cmp.run_a.id} vs #{self._cmp.run_b.id}")
        title.setObjectName("SectionTitle")
        title.setStyleSheet("font-size: 16px; font-weight: 700; color: #0F172A;")
        layout.addWidget(title)

        # Subtitle comparing timestamps and status
        sub = QLabel(
            f"Baseline Run A: #{self._cmp.run_a.id} ({self._cmp.run_a.started_at_display}, {self._cmp.run_a.overall_status.value})  ➔  "
            f"Target Run B: #{self._cmp.run_b.id} ({self._cmp.run_b.started_at_display}, {self._cmp.run_b.overall_status.value})"
        )
        sub.setStyleSheet("font-size: 12px; color: #64748B;")
        layout.addWidget(sub)

        # 4 KPI Summary Cards Row
        kpi_row = QHBoxLayout()
        kpi_row.setSpacing(10)

        # Regressions
        c_reg = QFrame()
        c_reg.setStyleSheet("background-color: #F8FAFC; border: 1px solid #E2E8F0; border-radius: 6px; padding: 6px;")
        lay_reg = QVBoxLayout(c_reg)
        lay_reg.setContentsMargins(8, 8, 8, 8)
        lay_reg.setSpacing(2)
        lbl_r_t = QLabel("REGRESSIONS")
        lbl_r_t.setStyleSheet("font-size: 11px; font-weight: 700; color: #B91C1C;")
        lay_reg.addWidget(lbl_r_t)
        lbl_r_c = QLabel(str(self._cmp.regressions_count))
        lbl_r_c.setStyleSheet("font-size: 20px; font-weight: 700; color: #B91C1C;")
        lay_reg.addWidget(lbl_r_c)
        kpi_row.addWidget(c_reg, stretch=1)

        # Improvements
        c_imp = QFrame()
        c_imp.setStyleSheet("background-color: #F8FAFC; border: 1px solid #E2E8F0; border-radius: 6px; padding: 6px;")
        lay_imp = QVBoxLayout(c_imp)
        lay_imp.setContentsMargins(8, 8, 8, 8)
        lay_imp.setSpacing(2)
        lbl_i_t = QLabel("IMPROVEMENTS")
        lbl_i_t.setStyleSheet("font-size: 11px; font-weight: 700; color: #15803D;")
        lay_imp.addWidget(lbl_i_t)
        lbl_i_c = QLabel(str(self._cmp.improvements_count))
        lbl_i_c.setStyleSheet("font-size: 20px; font-weight: 700; color: #15803D;")
        lay_imp.addWidget(lbl_i_c)
        kpi_row.addWidget(c_imp, stretch=1)

        # Unchanged
        c_unc = QFrame()
        c_unc.setStyleSheet("background-color: #F8FAFC; border: 1px solid #E2E8F0; border-radius: 6px; padding: 6px;")
        lay_unc = QVBoxLayout(c_unc)
        lay_unc.setContentsMargins(8, 8, 8, 8)
        lay_unc.setSpacing(2)
        lbl_u_t = QLabel("UNCHANGED")
        lbl_u_t.setStyleSheet("font-size: 11px; font-weight: 700; color: #475569;")
        lay_unc.addWidget(lbl_u_t)
        lbl_u_c = QLabel(str(self._cmp.unchanged_count))
        lbl_u_c.setStyleSheet("font-size: 20px; font-weight: 700; color: #475569;")
        lay_unc.addWidget(lbl_u_c)
        kpi_row.addWidget(c_unc, stretch=1)

        # Added / Removed
        c_mod = QFrame()
        c_mod.setStyleSheet("background-color: #F8FAFC; border: 1px solid #E2E8F0; border-radius: 6px; padding: 6px;")
        lay_mod = QVBoxLayout(c_mod)
        lay_mod.setContentsMargins(8, 8, 8, 8)
        lay_mod.setSpacing(2)
        lbl_m_t = QLabel("NEW / REMOVED RULES")
        lbl_m_t.setStyleSheet("font-size: 11px; font-weight: 700; color: #1D4ED8;")
        lay_mod.addWidget(lbl_m_t)
        lbl_m_c = QLabel(f"+{self._cmp.new_rules_count} / -{self._cmp.removed_rules_count}")
        lbl_m_c.setStyleSheet("font-size: 20px; font-weight: 700; color: #1D4ED8;")
        lay_mod.addWidget(lbl_m_c)
        kpi_row.addWidget(c_mod, stretch=1)

        layout.addLayout(kpi_row)

        # Diff Table
        self.diff_table = QTableWidget()
        self.diff_table.setObjectName("DataTable")
        self.diff_table.setColumnCount(8)
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

        header = self.diff_table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        header.setMinimumSectionSize(75)

        self.diff_table.setColumnWidth(0, 110)  # Change (NEW, REGRESSION, etc.)
        self.diff_table.setColumnWidth(1, 230)  # Rule Name
        self.diff_table.setColumnWidth(2, 160)  # Target
        self.diff_table.setColumnWidth(3, 110)  # Run #A Status
        self.diff_table.setColumnWidth(4, 110)  # Run #B Status
        self.diff_table.setColumnWidth(5, 120)  # Run #A Actual
        self.diff_table.setColumnWidth(6, 120)  # Run #B Actual
        self.diff_table.setColumnWidth(7, 130)  # Run #B Deviation

        self.diff_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.diff_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.diff_table.setAlternatingRowColors(True)
        self.diff_table.verticalHeader().setVisible(False)
        self.diff_table.verticalHeader().setDefaultSectionSize(34)
        self.diff_table.setRowCount(len(self._cmp.rule_comparisons))

        for row_idx, item in enumerate(self._cmp.rule_comparisons):
            # Col 0: Change
            self.diff_table.setItem(row_idx, 0, make_change_table_item(item.change_type))

            # Col 1: Rule Name
            self.diff_table.setItem(row_idx, 1, QTableWidgetItem(item.rule_name))

            # Col 2: Target
            self.diff_table.setItem(row_idx, 2, QTableWidgetItem(item.target_display))

            # Col 3: Status A
            self.diff_table.setItem(row_idx, 3, make_status_table_item(item.status_a))

            # Col 4: Status B
            self.diff_table.setItem(row_idx, 4, make_status_table_item(item.status_b))

            # Col 5: Actual A
            self.diff_table.setItem(row_idx, 5, QTableWidgetItem(item.actual_a or "—"))

            # Col 6: Actual B
            self.diff_table.setItem(row_idx, 6, QTableWidgetItem(item.actual_b or "—"))

            # Col 7: Deviation B
            self.diff_table.setItem(row_idx, 7, QTableWidgetItem(item.deviation_b or "None"))

        layout.addWidget(self.diff_table, stretch=1)

        # Footer Close Button
        btn_row = QHBoxLayout()
        btn_row.addStretch(1)
        btn_close = QPushButton("Close")
        btn_close.setObjectName("PrimaryButton")
        btn_close.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_close.clicked.connect(self.accept)
        btn_row.addWidget(btn_close)
        layout.addLayout(btn_row)
