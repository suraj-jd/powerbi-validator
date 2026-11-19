"""Dialog presenting side-by-side run comparison and regression diff (Stage 14)."""

from __future__ import annotations

from PySide6.QtCore import Qt
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

from app.services.compare_service import RunComparisonDTO
from app.ui.dialogs.result_details_dialog import make_validation_status_pill


def make_change_pill(change_type: str) -> QLabel:
    pill = QLabel(f" {change_type} ")
    pill.setAlignment(Qt.AlignmentFlag.AlignCenter)

    if change_type == "REGRESSION":
        bg = "#FEE2E2"
        color = "#991B1B"
        border = "#FECACA"
    elif change_type == "IMPROVEMENT":
        bg = "#DCFCE7"
        color = "#166534"
        border = "#BBF7D0"
    elif change_type == "NEW":
        bg = "#DBEAFE"
        color = "#1E40AF"
        border = "#BFDBFE"
    elif change_type == "REMOVED":
        bg = "#F1F5F9"
        color = "#64748B"
        border = "#CBD5E1"
    else:
        bg = "#F8FAFC"
        color = "#475569"
        border = "#E2E8F0"

    pill.setStyleSheet(
        f"background-color: {bg}; color: {color}; border: 1px solid {border}; "
        "border-radius: 4px; font-weight: 700; font-size: 10px; padding: 2px 6px;"
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
        self.setMinimumSize(850, 560)
        self.resize(920, 620)
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
        lay_reg.setContentsMargins(6, 6, 6, 6)
        lay_reg.setSpacing(2)
        lbl_r_t = QLabel("REGRESSIONS")
        lbl_r_t.setStyleSheet("font-size: 10px; font-weight: 700; color: #991B1B;")
        lay_reg.addWidget(lbl_r_t)
        lbl_r_c = QLabel(str(self._cmp.regressions_count))
        lbl_r_c.setStyleSheet("font-size: 18px; font-weight: 700; color: #991B1B;")
        lay_reg.addWidget(lbl_r_c)
        kpi_row.addWidget(c_reg, stretch=1)

        # Improvements
        c_imp = QFrame()
        c_imp.setStyleSheet("background-color: #F8FAFC; border: 1px solid #E2E8F0; border-radius: 6px; padding: 6px;")
        lay_imp = QVBoxLayout(c_imp)
        lay_imp.setContentsMargins(6, 6, 6, 6)
        lay_imp.setSpacing(2)
        lbl_i_t = QLabel("IMPROVEMENTS")
        lbl_i_t.setStyleSheet("font-size: 10px; font-weight: 700; color: #166534;")
        lay_imp.addWidget(lbl_i_t)
        lbl_i_c = QLabel(str(self._cmp.improvements_count))
        lbl_i_c.setStyleSheet("font-size: 18px; font-weight: 700; color: #166534;")
        lay_imp.addWidget(lbl_i_c)
        kpi_row.addWidget(c_imp, stretch=1)

        # Unchanged
        c_unc = QFrame()
        c_unc.setStyleSheet("background-color: #F8FAFC; border: 1px solid #E2E8F0; border-radius: 6px; padding: 6px;")
        lay_unc = QVBoxLayout(c_unc)
        lay_unc.setContentsMargins(6, 6, 6, 6)
        lay_unc.setSpacing(2)
        lbl_u_t = QLabel("UNCHANGED")
        lbl_u_t.setStyleSheet("font-size: 10px; font-weight: 700; color: #475569;")
        lay_unc.addWidget(lbl_u_t)
        lbl_u_c = QLabel(str(self._cmp.unchanged_count))
        lbl_u_c.setStyleSheet("font-size: 18px; font-weight: 700; color: #475569;")
        lay_unc.addWidget(lbl_u_c)
        kpi_row.addWidget(c_unc, stretch=1)

        # Added / Removed
        c_mod = QFrame()
        c_mod.setStyleSheet("background-color: #F8FAFC; border: 1px solid #E2E8F0; border-radius: 6px; padding: 6px;")
        lay_mod = QVBoxLayout(c_mod)
        lay_mod.setContentsMargins(6, 6, 6, 6)
        lay_mod.setSpacing(2)
        lbl_m_t = QLabel("NEW / REMOVED RULES")
        lbl_m_t.setStyleSheet("font-size: 10px; font-weight: 700; color: #1E40AF;")
        lay_mod.addWidget(lbl_m_t)
        lbl_m_c = QLabel(f"+{self._cmp.new_rules_count} / -{self._cmp.removed_rules_count}")
        lbl_m_c.setStyleSheet("font-size: 18px; font-weight: 700; color: #1E40AF;")
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
        self.diff_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.diff_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.diff_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.diff_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.diff_table.setAlternatingRowColors(True)
        self.diff_table.verticalHeader().setVisible(False)
        self.diff_table.setRowCount(len(self._cmp.rule_comparisons))

        for row_idx, item in enumerate(self._cmp.rule_comparisons):
            # Col 0: Change Pill
            pill_c = make_change_pill(item.change_type)
            w_c = QWidget()
            wl_c = QHBoxLayout(w_c)
            wl_c.setContentsMargins(4, 2, 4, 2)
            wl_c.addWidget(pill_c)
            self.diff_table.setCellWidget(row_idx, 0, w_c)

            # Col 1: Rule Name
            self.diff_table.setItem(row_idx, 1, QTableWidgetItem(item.rule_name))

            # Col 2: Target
            self.diff_table.setItem(row_idx, 2, QTableWidgetItem(item.target_display))

            # Col 3: Status A
            if item.status_a:
                pill_a = make_validation_status_pill(item.status_a)
                w_a = QWidget()
                wl_a = QHBoxLayout(w_a)
                wl_a.setContentsMargins(4, 2, 4, 2)
                wl_a.addWidget(pill_a)
                self.diff_table.setCellWidget(row_idx, 3, w_a)
            else:
                self.diff_table.setItem(row_idx, 3, QTableWidgetItem("—"))

            # Col 4: Status B
            if item.status_b:
                pill_b = make_validation_status_pill(item.status_b)
                w_b = QWidget()
                wl_b = QHBoxLayout(w_b)
                wl_b.setContentsMargins(4, 2, 4, 2)
                wl_b.addWidget(pill_b)
                self.diff_table.setCellWidget(row_idx, 4, w_b)
            else:
                self.diff_table.setItem(row_idx, 4, QTableWidgetItem("—"))

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
