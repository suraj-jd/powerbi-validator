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
    """Create a styled status pill widget for validation results."""
    st_val = status.value if isinstance(status, ValidationStatus) else str(status).upper()
    pill = QLabel(st_val)
    pill.setAlignment(Qt.AlignmentFlag.AlignCenter)
    pill.setFixedHeight(22)
    pill.setMinimumWidth(80)
    pill.setMaximumWidth(105)

    if st_val == "PASS":
        bg = "#DCFCE7"
        text_color = "#15803D"
        border = "#86EFAC"
    elif st_val == "FAIL":
        bg = "#FEE2E2"
        text_color = "#B91C1C"
        border = "#FCA5A5"
    elif st_val == "WARNING":
        bg = "#FEF3C7"
        text_color = "#B45309"
        border = "#FCD34D"
    elif st_val == "ERROR":
        bg = "#F3E8FF"
        text_color = "#7E22CE"
        border = "#D8B4FE"
    else:
        bg = "#F1F5F9"
        text_color = "#475569"
        border = "#CBD5E1"

    pill.setStyleSheet(
        f"background-color: {bg}; color: {text_color}; border: 1.5px solid {border}; "
        "border-radius: 4px; font-weight: 700; font-size: 11px; padding: 2px 6px;"
    )
    return pill


def update_validation_status_pill(pill: QLabel, status: ValidationStatus | str) -> None:
    """Update text and styling on an existing validation status pill in place."""
    st_val = status.value if isinstance(status, ValidationStatus) else str(status).upper()
    pill.setText(st_val)

    if st_val == "PASS":
        bg = "#DCFCE7"
        text_color = "#15803D"
        border = "#86EFAC"
    elif st_val == "FAIL":
        bg = "#FEE2E2"
        text_color = "#B91C1C"
        border = "#FCA5A5"
    elif st_val == "WARNING":
        bg = "#FEF3C7"
        text_color = "#B45309"
        border = "#FCD34D"
    elif st_val == "ERROR":
        bg = "#F3E8FF"
        text_color = "#7E22CE"
        border = "#D8B4FE"
    else:
        bg = "#F1F5F9"
        text_color = "#475569"
        border = "#CBD5E1"

    pill.setStyleSheet(
        f"background-color: {bg}; color: {text_color}; border: 1.5px solid {border}; "
        "border-radius: 4px; font-weight: 700; font-size: 11px; padding: 2px 6px;"
    )


def make_status_table_item(status: ValidationStatus | str | None) -> QTableWidgetItem:
    """Create a crisp, bold, colorful QTableWidgetItem for validation status without widget shrink."""
    if not status:
        item = QTableWidgetItem("—")
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


class ResultDetailsDialog(QDialog):
    """Detailed result inspector displaying rule target, status, actual vs expected, and DAX diagnostics."""

    def __init__(
        self,
        result: ValidationResultDTO,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._result = result
        self.setWindowTitle(f"Validation Diagnostics — {result.rule_name}")
        self.setMinimumSize(680, 520)
        self.resize(740, 580)
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(16)

        # Header with rule name and status pill
        header_row = QHBoxLayout()
        header_row.setSpacing(12)

        title_col = QVBoxLayout()
        title_col.setSpacing(4)
        lbl_title = QLabel(self._result.rule_name)
        lbl_title.setObjectName("SectionTitle")
        lbl_title.setStyleSheet("font-size: 16px; font-weight: 700; color: #0F172A;")
        title_col.addWidget(lbl_title)

        lbl_target = QLabel(f"Target: {self._result.target_display}  •  Check: {self._result.validation_type}")
        lbl_target.setStyleSheet("font-size: 12px; color: #64748B;")
        title_col.addWidget(lbl_target)
        header_row.addLayout(title_col, stretch=1)

        pill = make_validation_status_pill(self._result.status)
        header_row.addWidget(pill, alignment=Qt.AlignmentFlag.AlignTop)
        layout.addLayout(header_row)

        # Summary box
        summary_frame = QFrame()
        summary_frame.setStyleSheet(
            "background-color: #F8FAFC; border: 1px solid #E2E8F0; border-radius: 6px; padding: 10px;"
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
        c_exp.setStyleSheet("background-color: #F8FAFC; border: 1px solid #E2E8F0; border-radius: 6px; padding: 8px;")
        lay_exp = QVBoxLayout(c_exp)
        lay_exp.setContentsMargins(6, 6, 6, 6)
        lay_exp.setSpacing(2)
        lbl_e_title = QLabel("EXPECTED")
        lbl_e_title.setStyleSheet("font-size: 10px; font-weight: 700; color: #64748B;")
        lay_exp.addWidget(lbl_e_title)
        lbl_e_val = QLabel(self._result.expected_value or "—")
        lbl_e_val.setStyleSheet("font-size: 12px; font-weight: 600; color: #0F172A;")
        lbl_e_val.setWordWrap(True)
        lay_exp.addWidget(lbl_e_val)
        kpi_row.addWidget(c_exp, stretch=1)

        # Actual
        c_act = QFrame()
        c_act.setStyleSheet("background-color: #F8FAFC; border: 1px solid #E2E8F0; border-radius: 6px; padding: 8px;")
        lay_act = QVBoxLayout(c_act)
        lay_act.setContentsMargins(6, 6, 6, 6)
        lay_act.setSpacing(2)
        lbl_a_title = QLabel("ACTUAL OBSERVED")
        lbl_a_title.setStyleSheet("font-size: 10px; font-weight: 700; color: #64748B;")
        lay_act.addWidget(lbl_a_title)
        lbl_a_val = QLabel(self._result.actual_value or "—")
        lbl_a_val.setStyleSheet("font-size: 12px; font-weight: 600; color: #0F172A;")
        lbl_a_val.setWordWrap(True)
        lay_act.addWidget(lbl_a_val)
        kpi_row.addWidget(c_act, stretch=1)

        # Deviation
        c_dev = QFrame()
        c_dev.setStyleSheet("background-color: #F8FAFC; border: 1px solid #E2E8F0; border-radius: 6px; padding: 8px;")
        lay_dev = QVBoxLayout(c_dev)
        lay_dev.setContentsMargins(6, 6, 6, 6)
        lay_dev.setSpacing(2)
        lbl_d_title = QLabel("DEVIATION")
        lbl_d_title.setStyleSheet("font-size: 10px; font-weight: 700; color: #64748B;")
        lay_dev.addWidget(lbl_d_title)
        lbl_d_val = QLabel(self._result.deviation or "None")
        lbl_d_val.setStyleSheet("font-size: 12px; font-weight: 600; color: #0F172A;")
        lbl_d_val.setWordWrap(True)
        lay_dev.addWidget(lbl_d_val)
        kpi_row.addWidget(c_dev, stretch=1)

        layout.addLayout(kpi_row)

        # Timings & Duration
        timings_label = QLabel(
            f"Evaluated in {self._result.duration_ms} ms  •  Started: {self._result.started_at.strftime('%Y-%m-%d %H:%M:%S UTC')}"
        )
        timings_label.setStyleSheet("font-size: 11px; color: #64748B;")
        layout.addWidget(timings_label)

        # Detailed Diagnostics Section
        lbl_diag = QLabel("Detailed Execution Log & Diagnostics:")
        lbl_diag.setStyleSheet("font-size: 12px; font-weight: 600; color: #334155;")
        layout.addWidget(lbl_diag)

        self.details_box = QTextEdit()
        self.details_box.setReadOnly(True)
        self.details_box.setStyleSheet(
            "font-family: Consolas, 'Courier New', monospace; font-size: 11px; "
            "background-color: #0F172A; color: #F1F5F9; border-radius: 6px; padding: 10px;"
        )
        details_text = self._result.detailed_message or self._result.result_summary
        self.details_box.setPlainText(redact_secrets(details_text))
        layout.addWidget(self.details_box, stretch=1)

        # Footer Buttons
        btn_row = QHBoxLayout()
        btn_copy = QPushButton("Copy Diagnostics")
        btn_copy.setObjectName("SecondaryButton")
        btn_copy.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_copy.clicked.connect(self._copy_diagnostics)
        btn_row.addWidget(btn_copy)

        btn_row.addStretch(1)

        btn_close = QPushButton("Close")
        btn_close.setObjectName("PrimaryButton")
        btn_close.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_close.clicked.connect(self.accept)
        btn_row.addWidget(btn_close)

        layout.addLayout(btn_row)

    def _copy_diagnostics(self) -> None:
        text = (
            f"Rule: {self._result.rule_name}\n"
            f"Status: {self._result.status.value}\n"
            f"Target: {self._result.target_display}\n"
            f"Check Type: {self._result.validation_type}\n"
            f"Summary: {self._result.result_summary}\n"
            f"Expected: {self._result.expected_value}\n"
            f"Actual: {self._result.actual_value}\n"
            f"Deviation: {self._result.deviation}\n"
            f"Duration: {self._result.duration_ms} ms\n\n"
            f"Details:\n{self._result.detailed_message or 'N/A'}"
        )
        clipboard = QApplication.clipboard()
        if clipboard:
            clipboard.setText(redact_secrets(text))
