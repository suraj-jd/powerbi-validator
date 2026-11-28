"""Dialog presenting detailed diagnostics and calculation breakdown for a validation result (Stage 13)."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from app.core.logging_config import redact_secrets
from app.core.status import ValidationStatus
from app.services.orchestrator_service import ValidationResultDTO


def make_validation_status_pill(status: ValidationStatus | str) -> QLabel:
    pill = QLabel()
    style_status_label(pill, status)
    return pill


def update_validation_status_pill(pill: QLabel, status: ValidationStatus | str) -> None:
    style_status_label(pill, status)


def make_status_table_item(status: ValidationStatus | str | None) -> QTableWidgetItem:
    """Create a crisp, bold, colorful QTableWidgetItem for validation status without widget shrink."""
    if not status:
        item = QTableWidgetItem("-")
        item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        item.setForeground(QColor("#94A3B8"))
        item.setData(Qt.ItemDataRole.UserRole, "")
        return item

    st_val = status.value if isinstance(status, ValidationStatus) else str(status).upper()
    item = QTableWidgetItem(st_val)
    item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
    font = item.font()
    font.setBold(True)
    font.setPointSize(10)
    item.setFont(font)
    item.setData(Qt.ItemDataRole.UserRole, st_val)

    _, icon, color, background, description = status_presentation(status)
    item.setForeground(QColor(color))
    item.setIcon(make_nav_icon(icon, color, 16))
    item.setToolTip(description)
    return item


from app.ui.widgets.enterprise import EnterpriseDialog, style_status_label, status_presentation
from app.ui.theme import make_nav_icon

class ResultDetailsDialog(EnterpriseDialog):
    """Detailed result inspector displaying rule target, status, actual vs expected, and DAX diagnostics."""

    def __init__(
        self,
        result: ValidationResultDTO,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._result = result
        self.setWindowTitle(f"Validation Diagnostics: {result.rule_name}")
        self.setMinimumSize(680, 460)
        self.resize(740, 580)
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(12)

        # Header with rule name and status pill
        header_row = QHBoxLayout()
        header_row.setSpacing(12)

        title_col = QVBoxLayout()
        title_col.setSpacing(4)
        lbl_title = QLabel(self._result.rule_name)
        lbl_title.setObjectName("SectionTitle")
        lbl_title.setStyleSheet("font-size: 16px; font-weight: 700; color: #16243A;")
        title_col.addWidget(lbl_title)

        lbl_target = QLabel(f"Target: {self._result.target_display}  •  Check: {self._result.validation_type}")
        lbl_target.setWordWrap(True)
        lbl_target.setStyleSheet("font-size: 12px; color: #64748B;")
        title_col.addWidget(lbl_target)
        header_row.addLayout(title_col, stretch=1)

        pill = make_validation_status_pill(self._result.status)
        pill.setToolTip(f"Validation outcome: {self._result.status.value if hasattr(self._result.status, 'value') else str(self._result.status)}")
        header_row.addWidget(pill, alignment=Qt.AlignmentFlag.AlignTop)
        layout.addLayout(header_row)

        # Summary box
        summary_frame = QFrame()
        summary_frame.setStyleSheet(
            "QFrame { background-color: #F8FAFC; border: 1px solid #DDE4ED; border-radius: 6px; padding: 10px; }"
        )
        summary_lay = QVBoxLayout(summary_frame)
        summary_lay.setContentsMargins(8, 6, 8, 6)
        summary_lay.setSpacing(4)

        lbl_sum_title = QLabel("RESULT SUMMARY")
        lbl_sum_title.setStyleSheet("font-size: 10px; font-weight: 700; color: #64748B; letter-spacing: 0.5px;")
        summary_lay.addWidget(lbl_sum_title)

        lbl_sum_text = QLabel(self._result.result_summary)
        lbl_sum_text.setStyleSheet("font-size: 13px; font-weight: 600; color: #1E293B;")
        lbl_sum_text.setWordWrap(True)
        summary_lay.addWidget(lbl_sum_text)
        layout.addWidget(summary_frame)

        # 3 KPI Cards: Expected, Actual, Deviation
        kpi_row = QHBoxLayout()
        kpi_row.setSpacing(10)

        # Expected
        c_exp = QFrame()
        c_exp.setStyleSheet(
            "QFrame { background-color: #F8FAFC; border: 1px solid #DDE4ED; border-radius: 6px; padding: 8px; }"
        )
        lay_exp = QVBoxLayout(c_exp)
        lay_exp.setContentsMargins(6, 6, 6, 6)
        lay_exp.setSpacing(2)
        lbl_e_title = QLabel("EXPECTED")
        lbl_e_title.setStyleSheet("font-size: 10px; font-weight: 700; color: #64748B;")
        lay_exp.addWidget(lbl_e_title)
        lbl_e_val = QLabel(self._result.expected_value or "-")
        lbl_e_val.setStyleSheet("font-size: 12px; font-weight: 600; color: #16243A;")
        lbl_e_val.setWordWrap(True)
        lay_exp.addWidget(lbl_e_val)
        kpi_row.addWidget(c_exp, stretch=1)

        # Actual
        c_act = QFrame()
        c_act.setStyleSheet(
            "QFrame { background-color: #F8FAFC; border: 1px solid #DDE4ED; border-radius: 6px; padding: 8px; }"
        )
        lay_act = QVBoxLayout(c_act)
        lay_act.setContentsMargins(6, 6, 6, 6)
        lay_act.setSpacing(2)
        lbl_a_title = QLabel("ACTUAL OBSERVED")
        lbl_a_title.setStyleSheet("font-size: 10px; font-weight: 700; color: #64748B;")
        lay_act.addWidget(lbl_a_title)
        lbl_a_val = QLabel(self._result.actual_value or "-")
        lbl_a_val.setStyleSheet("font-size: 12px; font-weight: 600; color: #16243A;")
        lbl_a_val.setWordWrap(True)
        lay_act.addWidget(lbl_a_val)
        kpi_row.addWidget(c_act, stretch=1)

        # Deviation
        c_dev = QFrame()
        c_dev.setStyleSheet(
            "QFrame { background-color: #F8FAFC; border: 1px solid #DDE4ED; border-radius: 6px; padding: 8px; }"
        )
        lay_dev = QVBoxLayout(c_dev)
        lay_dev.setContentsMargins(6, 6, 6, 6)
        lay_dev.setSpacing(2)
        lbl_d_title = QLabel("DEVIATION")
        lbl_d_title.setStyleSheet("font-size: 10px; font-weight: 700; color: #64748B;")
        lay_dev.addWidget(lbl_d_title)
        lbl_d_val = QLabel(self._result.deviation or "None")
        lbl_d_val.setStyleSheet("font-size: 12px; font-weight: 600; color: #16243A;")
        lbl_d_val.setWordWrap(True)
        lay_dev.addWidget(lbl_d_val)
        kpi_row.addWidget(c_dev, stretch=1)

        layout.addLayout(kpi_row)

        # Timings & Duration
        timings_label = QLabel(
            f"Run #{self._result.validation_run_id}  •  Validated at: {self._result.validated_at_display}  •  Duration: {self._result.duration_ms} ms"
        )
        timings_label.setStyleSheet("font-size: 11px; color: #64748B;")
        timings_label.setWordWrap(True)
        layout.addWidget(timings_label)

        # Detailed Diagnostics Section
        self.diagnostics_toggle = QPushButton("Technical diagnostics")
        self.diagnostics_toggle.setObjectName("SecondaryButton")
        self.diagnostics_toggle.setCheckable(True)
        self.diagnostics_toggle.setToolTip("Expand the recorded execution details and query diagnostics.")
        layout.addWidget(self.diagnostics_toggle)

        self.details_box = QTextEdit()
        self.details_box.setReadOnly(True)
        self.details_box.setStyleSheet(
            "QTextEdit { font-family: Consolas, 'Courier New', monospace; font-size: 11px; "
            "background-color: #16243A; color: #F1F5F9; border-radius: 6px; padding: 10px; }"
        )
        details_text = self._result.detailed_message or self._result.result_summary
        self.details_box.setPlainText(redact_secrets(details_text))
        self.details_box.setMinimumHeight(160)
        self.details_box.hide()
        self.diagnostics_toggle.toggled.connect(self.details_box.setVisible)
        layout.addWidget(self.details_box, stretch=1)

        # Footer Buttons
        btn_row = QHBoxLayout()
        btn_copy = QPushButton("Copy Diagnostics")
        btn_copy.setObjectName("SecondaryButton")
        btn_copy.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_copy.setToolTip("Copy test details and results to your clipboard.")
        btn_copy.clicked.connect(self._copy_diagnostics)
        btn_row.addWidget(btn_copy)

        btn_row.addStretch(1)

        btn_close = QPushButton("Close")
        btn_close.setObjectName("PrimaryButton")
        btn_close.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_close.setToolTip("Close this diagnostics window.")
        btn_close.clicked.connect(self.accept)
        btn_row.addWidget(btn_close)

        layout.addLayout(btn_row)

    def _copy_diagnostics(self) -> None:
        text = (
            f"Run: #{self._result.validation_run_id}\n"
            f"Rule: {self._result.rule_name}\n"
            f"Status: {self._result.status.value}\n"
            f"Target: {self._result.target_display}\n"
            f"Check Type: {self._result.validation_type}\n"
            f"Summary: {self._result.result_summary}\n"
            f"Expected: {self._result.expected_value}\n"
            f"Actual: {self._result.actual_value}\n"
            f"Deviation: {self._result.deviation}\n"
            f"Validated At: {self._result.validated_at_display}\n"
            f"Duration: {self._result.duration_ms} ms\n\n"
            f"Details:\n{self._result.detailed_message or 'N/A'}"
        )
        clipboard = QApplication.clipboard()
        if clipboard:
            clipboard.setText(redact_secrets(text))
