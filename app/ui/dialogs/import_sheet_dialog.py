"""Dialog guiding non-technical users to import validation rules from Excel or CSV.

Shows the supported spreadsheet columns, allows downloading sample templates (.xlsx/.csv),
and lets the user choose the validation test to perform.
"""

from __future__ import annotations

import csv
import logging
from pathlib import Path
from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QButtonGroup,
    QComboBox,
    QDialog,
    QFileDialog,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPushButton,
    QRadioButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.services.rule_service import (
    VALIDATION_TYPE_ANOMALY,
    VALIDATION_TYPE_DAX_MEASURE,
    VALIDATION_TYPE_DUPLICATE,
    VALIDATION_TYPE_LATEST_DATE,
    VALIDATION_TYPE_NULL,
    VALIDATION_TYPE_REFRESH,
    VALIDATION_TYPE_ROW_COUNT,
)
from app.services.sheet_service import FRIENDLY_TEST_NAMES, SheetRowDTO, SheetService
from app.ui.widgets.animated_combo import AnimatedComboBox

logger = logging.getLogger(__name__)

SUPPORTED_COLUMNS_INFO = [
    ("SR", "Optional", "Row serial number (e.g. 1, 2, 3...)"),
    ("Workspace Name", "Recommended", "Human-readable workspace name (e.g. 'Finance Operations')"),
    ("Workspace ID", "Required *", "36-char Power BI Workspace GUID (or 'me')"),
    ("Report Name", "Recommended", "Report or semantic model name (e.g. 'Revenue Model')"),
    ("Dataset ID", "Required *", "36-char Power BI Semantic Model GUID"),
    ("Test to Do", "Optional", "Validation test type (e.g. 'Null / Blank Check') or set below"),
    ("Table Name", "Conditional", "Target table name (required for column checks like Sales)"),
    ("Column Name", "Conditional", "Target column name (e.g. TransactionID, OrderDate)"),
    ("Measure Name", "Conditional", "Target DAX measure name (e.g. Total Revenue or [Net Margin])"),
    ("Conditions Summary", "Optional", "Rule threshold summary (e.g. 'allowed blanks = 0')"),
]


class ImportSheetDialog(QDialog):
    """Modal dialog displaying supported spreadsheet format, sample downloads, and test selector."""

    def __init__(
        self,
        *,
        sheet_service: SheetService | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Import Validation Sheet (Excel / CSV)")
        self.setModal(True)
        self.setMinimumWidth(720)
        self.setMinimumHeight(540)
        self.setObjectName("ConfirmDialog")

        self._sheet_service = sheet_service
        self._selected_file: Path | None = None
        self._parsed_rows: list[SheetRowDTO] = []
        self._replace_mode: bool = False

        self._init_ui()

    @property
    def imported_rows(self) -> list[SheetRowDTO]:
        return list(self._parsed_rows)

    @property
    def replace_mode(self) -> bool:
        return self._replace_mode

    def _init_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(14)

        # Header Title
        title = QLabel("Import Validation Rules from Excel or CSV")
        title.setObjectName("DialogTitle")
        layout.addWidget(title)

        banner = QLabel(
            "Select an Excel (.xlsx) or CSV (.csv) spreadsheet to import validation tests. "
            "You can choose a default test to apply to imported rows, or have it auto-detected from the file."
        )
        banner.setObjectName("InfoBanner")
        banner.setWordWrap(True)
        layout.addWidget(banner)

        # 1. Supported Columns Table Card
        cols_card = QFrame()
        cols_card.setObjectName("DialogCard")
        cols_card.setStyleSheet(
            "#DialogCard { background-color: #FFFFFF; border: 1px solid #CBD5E1; "
            "border-radius: 8px; padding: 10px; }"
        )
        cols_layout = QVBoxLayout(cols_card)
        cols_layout.setContentsMargins(8, 8, 8, 8)
        cols_layout.setSpacing(8)

        card_title_row = QHBoxLayout()
        lbl_cols = QLabel("Supported Spreadsheet Columns & Format:")
        lbl_cols.setStyleSheet("font-size: 12px; font-weight: 700; color: #0F172A;")
        card_title_row.addWidget(lbl_cols, stretch=1)

        # Sample download buttons
        btn_sample_xlsx = QPushButton("📥 Sample Template (.xlsx)")
        btn_sample_xlsx.setObjectName("SecondaryButton")
        btn_sample_xlsx.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_sample_xlsx.clicked.connect(lambda: self._download_sample_template(is_xlsx=True))
        card_title_row.addWidget(btn_sample_xlsx)

        btn_sample_csv = QPushButton("📥 Sample Template (.csv)")
        btn_sample_csv.setObjectName("SecondaryButton")
        btn_sample_csv.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_sample_csv.clicked.connect(lambda: self._download_sample_template(is_xlsx=False))
        card_title_row.addWidget(btn_sample_csv)
        cols_layout.addLayout(card_title_row)

        # Schema Table
        table = QTableWidget()
        table.setColumnCount(3)
        table.setHorizontalHeaderLabels(["Column Name", "Requirement", "Description & Sample Values"])
        table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        table.horizontalHeader().resizeSection(0, 140)
        table.horizontalHeader().resizeSection(1, 100)
        table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        table.setRowCount(len(SUPPORTED_COLUMNS_INFO))
        table.setAlternatingRowColors(True)
        table.verticalHeader().setVisible(False)
        table.setMaximumHeight(180)
        table.setStyleSheet(
            "QTableWidget { gridline-color: #E2E8F0; font-size: 11px; background: #FFFFFF; border: 1px solid #E2E8F0; }"
            "QHeaderView::section { background: #F8FAFC; color: #334155; font-weight: 700; border: none; "
            "border-bottom: 1px solid #CBD5E1; padding: 4px; font-size: 11px; }"
        )

        for row_idx, (col_name, req, desc) in enumerate(SUPPORTED_COLUMNS_INFO):
            item_name = QTableWidgetItem(col_name)
            item_name.setTextAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)
            item_name.setFlags(item_name.flags() & ~Qt.ItemFlag.ItemIsEditable)

            item_req = QTableWidgetItem(req)
            item_req.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            item_req.setFlags(item_req.flags() & ~Qt.ItemFlag.ItemIsEditable)
            if "Required" in req:
                item_req.setForeground(Qt.GlobalColor.darkRed)

            item_desc = QTableWidgetItem(desc)
            item_desc.setFlags(item_desc.flags() & ~Qt.ItemFlag.ItemIsEditable)

            table.setItem(row_idx, 0, item_name)
            table.setItem(row_idx, 1, item_req)
            table.setItem(row_idx, 2, item_desc)

        cols_layout.addWidget(table)
        layout.addWidget(cols_card)

        # 2. Import Settings Card (Choose Test + Import Mode)
        settings_card = QFrame()
        settings_card.setObjectName("DialogCard")
        settings_card.setStyleSheet(
            "#DialogCard { background-color: #F8FAFC; border: 1px solid #E2E8F0; "
            "border-radius: 8px; padding: 12px; }"
        )
        settings_form = QFormLayout(settings_card)
        settings_form.setSpacing(10)
        settings_form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        # Test to Perform Dropdown
        self.test_selector_combo = AnimatedComboBox()
        self.test_selector_combo.setObjectName("FilterCombo")
        self.test_selector_combo.addItem("Auto-Detect from 'Test to Do' column in file", "auto")
        for key, name in FRIENDLY_TEST_NAMES.items():
            self.test_selector_combo.addItem(f"Force: {name}", key)
        settings_form.addRow("Test to Perform / Do:", self.test_selector_combo)

        # Import Mode Radio Group
        mode_box = QHBoxLayout()
        mode_box.setSpacing(16)
        self.mode_group = QButtonGroup(self)

        self.radio_append = QRadioButton("Append to existing sheet rows")
        self.radio_append.setChecked(True)
        self.radio_replace = QRadioButton("Replace current sheet with imported rows")

        for i, rb in enumerate((self.radio_append, self.radio_replace)):
            rb.setStyleSheet("color: #1E293B; font-size: 12px; font-weight: 500;")
            self.mode_group.addButton(rb, i)
            mode_box.addWidget(rb)
        mode_box.addStretch(1)
        settings_form.addRow("Import Destination:", mode_box)

        # File Chooser Row
        file_box = QHBoxLayout()
        file_box.setSpacing(8)

        self.file_path_input = QLineEdit()
        self.file_path_input.setObjectName("SearchInput")
        self.file_path_input.setPlaceholderText("Select an .xlsx or .csv file...")
        self.file_path_input.setReadOnly(True)
        file_box.addWidget(self.file_path_input, stretch=1)

        self.btn_browse = QPushButton("Browse...")
        self.btn_browse.setObjectName("SecondaryButton")
        self.btn_browse.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_browse.clicked.connect(self._handle_browse_file)
        file_box.addWidget(self.btn_browse)

        settings_form.addRow("Spreadsheet File:", file_box)
        layout.addWidget(settings_card)

        # Status / Feedback label
        self.status_label = QLabel("")
        self.status_label.setStyleSheet("color: #64748B; font-size: 12px; font-style: italic;")
        layout.addWidget(self.status_label)

        # Bottom Buttons
        btn_row = QHBoxLayout()
        btn_row.setSpacing(10)
        btn_row.addStretch(1)

        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.setObjectName("SecondaryButton")
        self.cancel_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.cancel_button.clicked.connect(self.reject)
        btn_row.addWidget(self.cancel_button)

        self.import_button = QPushButton("✔  Import & Apply to Sheet")
        self.import_button.setObjectName("PrimaryButton")
        self.import_button.setStyleSheet(
            "background-color: #1668DC; color: #FFFFFF; font-weight: 600; padding: 7px 18px; border-radius: 6px;"
        )
        self.import_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.import_button.setEnabled(False)
        self.import_button.clicked.connect(self._handle_execute_import)
        btn_row.addWidget(self.import_button)

        layout.addLayout(btn_row)

    def _handle_browse_file(self) -> None:
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Select Validation Sheet File",
            "",
            "Spreadsheets (*.xlsx *.csv);;Excel Files (*.xlsx);;CSV Files (*.csv)",
        )
        if not file_path:
            return

        p = Path(file_path)
        self._selected_file = p
        self.file_path_input.setText(str(p))
        self.import_button.setEnabled(True)
        self.status_label.setText(f"Selected: {p.name} (Ready to import)")

    def _download_sample_template(self, is_xlsx: bool, destination: Path | str | None = None) -> Path | None:
        if destination is not None:
            dest = str(destination)
        else:
            default_name = "Sample_PowerBI_Validation_Sheet.xlsx" if is_xlsx else "Sample_PowerBI_Validation_Sheet.csv"
            file_filter = "Excel Workbook (*.xlsx)" if is_xlsx else "CSV File (*.csv)"

            dest, _ = QFileDialog.getSaveFileName(self, "Download Sample Template", default_name, file_filter)
            if not dest:
                return None

        sample_rows = [
            {
                "SR": 1,
                "Enabled": "TRUE",
                "Workspace Name": "Sales Operations",
                "Workspace ID": "11111111-2222-3333-4444-555555555555",
                "Report Name": "Executive Sales Dashboard",
                "Dataset ID": "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
                "Test to Do": "Null / Blank Check",
                "Table Name": "Orders",
                "Column Name": "OrderID",
                "Measure Name": "",
                "Conditions Summary": "allowed blanks = 0",
            },
            {
                "SR": 2,
                "Enabled": "TRUE",
                "Workspace Name": "Sales Operations",
                "Workspace ID": "11111111-2222-3333-4444-555555555555",
                "Report Name": "Executive Sales Dashboard",
                "Dataset ID": "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
                "Test to Do": "Duplicate Check",
                "Table Name": "Orders",
                "Column Name": "OrderID",
                "Measure Name": "",
                "Conditions Summary": "allowed dups = 0",
            },
            {
                "SR": 3,
                "Enabled": "TRUE",
                "Workspace Name": "Sales Operations",
                "Workspace ID": "11111111-2222-3333-4444-555555555555",
                "Report Name": "Executive Sales Dashboard",
                "Dataset ID": "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
                "Test to Do": "Latest Date Freshness",
                "Table Name": "Orders",
                "Column Name": "OrderDate",
                "Measure Name": "",
                "Conditions Summary": "max age <= 24h",
            },
            {
                "SR": 4,
                "Enabled": "TRUE",
                "Workspace Name": "Sales Operations",
                "Workspace ID": "11111111-2222-3333-4444-555555555555",
                "Report Name": "Executive Sales Dashboard",
                "Dataset ID": "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
                "Test to Do": "Power BI Refresh SLA",
                "Table Name": "",
                "Column Name": "",
                "Measure Name": "",
                "Conditions Summary": "status = Completed, age <= 24h",
            },
            {
                "SR": 5,
                "Enabled": "TRUE",
                "Workspace Name": "Sales Operations",
                "Workspace ID": "11111111-2222-3333-4444-555555555555",
                "Report Name": "Executive Sales Dashboard",
                "Dataset ID": "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
                "Test to Do": "DAX Measure Check",
                "Table Name": "",
                "Column Name": "",
                "Measure Name": "[Total Revenue]",
                "Conditions Summary": "expected 1000000.0 (±5%)",
            },
        ]

        try:
            if is_xlsx:
                import openpyxl
                from openpyxl.styles import Font, PatternFill

                wb = openpyxl.Workbook()
                ws = wb.active
                ws.title = "Validation Sheet"

                header_font = Font(name="Segoe UI", size=11, bold=True, color="FFFFFF")
                header_fill = PatternFill(start_color="1668DC", end_color="1668DC", fill_type="solid")

                headers = list(sample_rows[0].keys())
                ws.append(headers)
                for col_idx in range(1, len(headers) + 1):
                    cell = ws.cell(row=1, column=col_idx)
                    cell.font = header_font
                    cell.fill = header_fill

                for row_data in sample_rows:
                    ws.append(list(row_data.values()))

                for col in ws.columns:
                    max_len = max(len(str(cell.value or "")) for cell in col)
                    col_letter = openpyxl.utils.get_column_letter(col[0].column)
                    ws.column_dimensions[col_letter].width = max(max_len + 3, 14)

                wb.save(dest)
            else:
                with open(dest, mode="w", newline="", encoding="utf-8-sig") as f:
                    writer = csv.DictWriter(f, fieldnames=list(sample_rows[0].keys()))
                    writer.writeheader()
                    writer.writerows(sample_rows)

            self.status_label.setText(f"Saved sample template: {Path(dest).name}")
            return Path(dest)
        except Exception as exc:
            logger.exception("Failed to create sample template: %s", exc)
            self.status_label.setText(f"Error generating template: {exc}")
            return None

    def _handle_execute_import(self) -> None:
        if not self._selected_file or not self._selected_file.exists():
            self.status_label.setText("Please select a valid file first.")
            return

        forced_test = self.test_selector_combo.currentData()
        self._replace_mode = self.radio_replace.isChecked()

        try:
            raw_dicts = self._read_file_records(self._selected_file)
            if not raw_dicts:
                self.status_label.setText("No data rows found in the selected file.")
                return

            parsed: list[SheetRowDTO] = []
            for item in raw_dicts:
                dto = self._parse_dict(item, forced_test)
                if dto:
                    parsed.append(dto)

            if not parsed:
                self.status_label.setText("Could not map any rows. Ensure 'Workspace ID' and 'Dataset ID' columns exist.")
                return

            self._parsed_rows = parsed
            self.accept()
        except Exception as exc:
            logger.exception("Failed to parse import file: %s", exc)
            self.status_label.setText(f"Error parsing file: {exc}")

    def _read_file_records(self, path: Path) -> list[dict[str, Any]]:
        records: list[dict[str, Any]] = []
        if path.suffix.lower() == ".csv":
            with open(path, mode="r", encoding="utf-8-sig") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    records.append(row)
        else:
            import openpyxl

            wb = openpyxl.load_workbook(path, data_only=True)
            ws = wb.active
            rows_iter = ws.iter_rows(values_only=True)
            try:
                headers = [str(c or "").strip() for c in next(rows_iter)]
            except StopIteration:
                return []

            for row_vals in rows_iter:
                if not any(row_vals):
                    continue
                d = {headers[i]: row_vals[i] for i in range(min(len(headers), len(row_vals)))}
                records.append(d)
        return records

    def _parse_dict(self, item: dict[str, Any], forced_test: str | None) -> SheetRowDTO | None:
        # Flexible key matching
        def _get_val(*keys: str) -> str:
            for k in keys:
                for actual_k, v in item.items():
                    if actual_k.strip().lower() == k.strip().lower():
                        return str(v or "").strip()
            return ""

        ws_id = _get_val("Workspace ID", "WorkspaceID", "Workspace_ID", "WorkspaceId")
        ds_id = _get_val("Dataset ID", "DatasetID", "Dataset_ID", "DatasetId")
        if not ws_id or not ds_id:
            return None

        ws_name = _get_val("Workspace Name", "WorkspaceName", "Workspace") or f"Workspace {ws_id[:8]}"
        rpt_name = _get_val("Report Name", "ReportName", "Report", "Dataset Name") or f"Dataset {ds_id[:8]}"

        # Resolve validation test
        from app.services.sheet_service import TEST_NAME_TO_TYPE

        if forced_test and forced_test != "auto":
            vtype = forced_test
        else:
            raw_test = _get_val("Test to Do", "Test", "Validation Type", "ValidationType").lower()
            vtype = TEST_NAME_TO_TYPE.get(raw_test, VALIDATION_TYPE_NULL)

        tbl = _get_val("Table Name", "TableName", "Table") or None
        col = _get_val("Column Name", "ColumnName", "Column") or None
        meas = _get_val("Measure Name", "MeasureName", "Measure") or None

        # Check if Column or Measure is unified
        unified_col_meas = _get_val("Column or Measure", "Column / Measure", "Target")
        if unified_col_meas:
            if vtype == VALIDATION_TYPE_DAX_MEASURE or (unified_col_meas.startswith("[") and unified_col_meas.endswith("]")):
                meas = unified_col_meas.strip("[]")
            else:
                col = unified_col_meas

        enabled_str = _get_val("Enabled", "IsActive", "Active")
        enabled = enabled_str.upper() != "FALSE" if enabled_str else True

        sr_str = _get_val("SR", "Sr.", "Sr", "Row")
        sr_no = int(sr_str) if sr_str.isdigit() else 1

        return SheetRowDTO(
            sr_no=sr_no,
            enabled=enabled,
            workspace_name=ws_name,
            workspace_id=ws_id,
            report_name=rpt_name,
            dataset_name=rpt_name,
            dataset_id=ds_id,
            validation_type=vtype,
            table_name=tbl,
            column_name=col,
            measure_name=meas,
            config={},
        )
