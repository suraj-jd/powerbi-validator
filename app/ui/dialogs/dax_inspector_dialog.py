"""Dialog for testing and inspecting DAX measure queries in Power BI semantic models (Stage 9)."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from app.core.status import NotificationLevel
from app.integrations.powerbi.dax_client import DaxQueryResult, build_measure_query, build_test_query
from app.integrations.powerbi.models import DatasetMetadata
from app.ui.widgets.notification_banner import NotificationBanner

if TYPE_CHECKING:
    from app.services.dax_service import DaxQueryService

logger = logging.getLogger(__name__)


class DaxInspectorDialog(QDialog):
    """Interactive modal allowing users to execute DAX measure queries and inspect results."""

    def __init__(
        self,
        *,
        workspace_id: str,
        dataset_id: str,
        display_name: str,
        dax_service: DaxQueryService,
        metadata: DatasetMetadata | None = None,
        preselected_measure: str | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._workspace_id = workspace_id
        self._dataset_id = dataset_id
        self._display_name = display_name
        self._service = dax_service
        self._metadata = metadata
        self._preselected = preselected_measure

        self.setWindowTitle("DAX Measure Query Inspector")
        self.setModal(True)
        self.resize(780, 580)
        self.setMinimumSize(680, 500)
        self.setObjectName("ConfirmDialog")

        self._init_ui()
        self._connect_signals()

    def _init_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(14)

        # Header
        header_row = QHBoxLayout()
        header_row.setSpacing(10)

        title_block = QVBoxLayout()
        title_block.setSpacing(3)
        title_lbl = QLabel("DAX Measure Query Inspector")
        title_lbl.setObjectName("DialogTitle")
        title_block.addWidget(title_lbl)

        sub_lbl = QLabel(f"Semantic Model: {self._display_name}  •  Model ID: {self._dataset_id}")
        sub_lbl.setObjectName("PageSubtitle")
        title_block.addWidget(sub_lbl)
        header_row.addLayout(title_block, stretch=1)

        self.btn_test_probe = QPushButton("Test API Eligibility")
        self.btn_test_probe.setObjectName("SecondaryButton")
        self.btn_test_probe.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_test_probe.clicked.connect(self._handle_test_probe)
        header_row.addWidget(self.btn_test_probe, alignment=Qt.AlignmentFlag.AlignTop)

        layout.addLayout(header_row)

        self.banner = NotificationBanner(self)
        layout.addWidget(self.banner)

        # Query Config Card
        cfg_card = QFrame()
        cfg_card.setObjectName("Card")
        cfg_layout = QVBoxLayout(cfg_card)
        cfg_layout.setContentsMargins(16, 14, 16, 14)
        cfg_layout.setSpacing(10)

        form = QFormLayout()
        form.setSpacing(10)

        # Measure selector or manual entry
        measures = [m.name for m in self._metadata.measures] if self._metadata and self._metadata.measures else []
        if measures:
            self.combo_measure = QComboBox()
            self.combo_measure.setEditable(True)
            self.combo_measure.addItem("-- Select or type measure --", "")
            for m in sorted(measures):
                self.combo_measure.addItem(m, m)
            if self._preselected:
                idx = self.combo_measure.findText(self._preselected)
                if idx >= 0:
                    self.combo_measure.setCurrentIndex(idx)
                else:
                    self.combo_measure.setEditText(self._preselected)
            self.combo_measure.currentTextChanged.connect(self._update_query_preview)
            form.addRow(self._make_label("DAX Measure:"), self.combo_measure)
        else:
            self.edit_measure = QLineEdit(self._preselected or "")
            self.edit_measure.setPlaceholderText("e.g. Total Sales or [Total Sales]")
            self.edit_measure.textChanged.connect(self._update_query_preview)
            form.addRow(self._make_label("DAX Measure:"), self.edit_measure)

        self.edit_filter = QLineEdit()
        self.edit_filter.setPlaceholderText("Optional filter context, e.g. Dates[Year] = 2024")
        self.edit_filter.textChanged.connect(self._update_query_preview)
        form.addRow(self._make_label("Filter Context:"), self.edit_filter)

        cfg_layout.addLayout(form)

        btn_row = QHBoxLayout()
        btn_row.addStretch(1)
        self.btn_run = QPushButton("▶  Execute DAX Measure")
        self.btn_run.setObjectName("PrimaryButton")
        self.btn_run.setStyleSheet(
            "background-color: #1668DC; color: #FFFFFF; font-weight: 600; padding: 8px 18px; border-radius: 6px;"
        )
        self.btn_run.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_run.clicked.connect(self._handle_run_query)
        btn_row.addWidget(self.btn_run)
        cfg_layout.addLayout(btn_row)

        layout.addWidget(cfg_card)

        # Output Results Card
        res_card = QFrame()
        res_card.setObjectName("Card")
        res_layout = QVBoxLayout(res_card)
        res_layout.setContentsMargins(16, 14, 16, 14)
        res_layout.setSpacing(10)

        res_header = QHBoxLayout()
        res_title = QLabel("Query Evaluation Output")
        res_title.setStyleSheet("color: #0F172A; font-size: 13px; font-weight: 600;")
        res_header.addWidget(res_title)
        res_header.addStretch(1)

        self.lbl_duration = QLabel("Duration: -")
        self.lbl_duration.setStyleSheet("color: #64748B; font-size: 11px;")
        res_header.addWidget(self.lbl_duration)
        res_layout.addLayout(res_header)

        # Value display
        val_box = QHBoxLayout()
        val_box.setSpacing(12)

        self.lbl_value_result = QLabel("-")
        self.lbl_value_result.setStyleSheet("color: #0F172A; font-size: 22px; font-weight: 700;")
        val_box.addWidget(self.lbl_value_result)

        self.lbl_type_pill = QLabel(" Ready ")
        self.lbl_type_pill.setStyleSheet(
            "background-color: #F1F5F9; color: #475569; border: 1px solid #CBD5E1; "
            "border-radius: 10px; font-size: 11px; font-weight: 700; padding: 2px 8px;"
        )
        val_box.addWidget(self.lbl_type_pill)
        val_box.addStretch(1)
        res_layout.addLayout(val_box)

        # Query syntax box
        query_title = QLabel("Constructed DAX Query:")
        query_title.setStyleSheet("color: #475569; font-size: 11px; font-weight: 600;")
        res_layout.addWidget(query_title)

        self.text_query = QTextEdit()
        self.text_query.setReadOnly(True)
        self.text_query.setMaximumHeight(65)
        self.text_query.setStyleSheet(
            "background-color: #F8FAFC; border: 1px solid #E2E8F0; border-radius: 4px; "
            "font-family: Consolas, monospace; font-size: 11px; color: #334155;"
        )
        res_layout.addWidget(self.text_query)

        layout.addWidget(res_card, stretch=1)

        # Bottom row
        bottom_row = QHBoxLayout()
        bottom_row.addStretch(1)
        self.btn_close = QPushButton("Close")
        self.btn_close.setObjectName("SecondaryButton")
        self.btn_close.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_close.clicked.connect(self.accept)
        bottom_row.addWidget(self.btn_close)
        layout.addLayout(bottom_row)

        self._update_query_preview()

    def _make_label(self, text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setStyleSheet("color: #334155; font-weight: 600; font-size: 12px;")
        return lbl

    def _get_measure_name(self) -> str:
        if hasattr(self, "combo_measure"):
            return self.combo_measure.currentText().strip()
        return self.edit_measure.text().strip()

    def _update_query_preview(self) -> None:
        meas = self._get_measure_name()
        filt = self.edit_filter.text().strip()
        if meas and not meas.startswith("--"):
            try:
                q = build_measure_query(meas, filt or None)
                self.text_query.setPlainText(q)
            except Exception:
                self.text_query.setPlainText("")
        else:
            self.text_query.setPlainText("EVALUATE ROW(...)")

    def _connect_signals(self) -> None:
        self._service.busy_changed.connect(self._on_busy_changed)

    def _disconnect_signals(self) -> None:
        try:
            self._service.busy_changed.disconnect(self._on_busy_changed)
        except Exception:
            pass

    def closeEvent(self, event) -> None:
        self._disconnect_signals()
        super().closeEvent(event)

    def _on_busy_changed(self, busy: bool) -> None:
        self.btn_run.setEnabled(not busy)
        self.btn_test_probe.setEnabled(not busy)
        self.btn_run.setText("Executing..." if busy else "▶  Execute DAX Measure")

    def _handle_test_probe(self) -> None:
        self.banner.hide()
        self.lbl_value_result.setText("Probing...")
        self.lbl_type_pill.setText(" Probing ")
        self.lbl_type_pill.setStyleSheet("background-color: #EFF6FF; color: #1D4ED8; border: 1px solid #BFDBFE;")
        self.text_query.setPlainText(build_test_query())

        def _on_probe_done(res: DaxQueryResult) -> None:
            self.lbl_duration.setText(f"Duration: {res.duration_ms} ms")
            if res.is_success:
                self.banner.show_message(
                    "Execute Queries API is active and supported on this semantic model.",
                    level=NotificationLevel.SUCCESS,
                    title="Eligibility Confirmed",
                )
                self.lbl_value_result.setText(res.display_value)
                self.lbl_type_pill.setText(" Active ")
                self.lbl_type_pill.setStyleSheet(
                    "background-color: #ECFDF5; color: #065F46; border: 1px solid #A7F3D0; font-weight: 700; border-radius: 10px; padding: 2px 8px;"
                )
            else:
                self.banner.show_message(
                    f"Execute Queries error: {res.error_message}",
                    level=NotificationLevel.ERROR,
                    title="API Ineligible",
                )
                self.lbl_value_result.setText("Probe Failed")
                self.lbl_type_pill.setText(" Error ")
                self.lbl_type_pill.setStyleSheet(
                    "background-color: #FEF2F2; color: #991B1B; border: 1px solid #FECACA; font-weight: 700; border-radius: 10px; padding: 2px 8px;"
                )

        self._service.test_connection_async(
            workspace_id=self._workspace_id,
            dataset_id=self._dataset_id,
            on_complete=_on_probe_done,
        )

    def _handle_run_query(self) -> None:
        meas = self._get_measure_name()
        if not meas or meas.startswith("--"):
            self.banner.show_message("Please select or enter a valid measure name.", level=NotificationLevel.WARNING)
            return

        filt = self.edit_filter.text().strip()
        self.banner.hide()
        self.lbl_value_result.setText("Executing...")

        def _on_run_done(res: DaxQueryResult) -> None:
            self.lbl_duration.setText(f"Duration: {res.duration_ms} ms")
            self.text_query.setPlainText(res.query)

            if res.is_success:
                val_str = res.display_value
                self.lbl_value_result.setText(val_str)
                if res.is_blank:
                    pill_text = " BLANK() "
                    pill_style = "background-color: #FFFBEB; color: #92400E; border: 1px solid #FDE68A;"
                else:
                    pill_text = f" {res.value_type.capitalize()} "
                    pill_style = "background-color: #ECFDF5; color: #065F46; border: 1px solid #A7F3D0;"

                self.lbl_type_pill.setText(pill_text)
                self.lbl_type_pill.setStyleSheet(f"{pill_style} font-weight: 700; border-radius: 10px; padding: 2px 8px;")
                self.banner.show_message(f"Query returned {val_str}", level=NotificationLevel.SUCCESS)
            else:
                self.lbl_value_result.setText("Error")
                self.lbl_type_pill.setText(" Failed ")
                self.lbl_type_pill.setStyleSheet(
                    "background-color: #FEF2F2; color: #991B1B; border: 1px solid #FECACA; font-weight: 700; border-radius: 10px; padding: 2px 8px;"
                )
                self.banner.show_message(f"DAX Error: {res.error_message}", level=NotificationLevel.ERROR)

        self._service.execute_measure_async(
            workspace_id=self._workspace_id,
            dataset_id=self._dataset_id,
            measure_name=meas,
            filter_context=filt or None,
            on_complete=_on_run_done,
        )
