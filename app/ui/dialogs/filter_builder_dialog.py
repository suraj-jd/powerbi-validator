"""Popup dialog for building Power BI / DAX filter conditions for sheet validation rules.

Allows non-technical users to pick Table, Column, Condition (=, <>, <, >, <=, >=,
IN, NOT IN, IS BLANK, IS NOT BLANK) and value in a compact, professional dialog
with live DAX preview, or enter custom DAX directly.
"""

from __future__ import annotations

import logging
import re
from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from app.ui.widgets.enterprise import EnterpriseDialog

logger = logging.getLogger(__name__)

# Supported Power BI slicer / filter operators
OPERATOR_EQUALS = "="
OPERATOR_NOT_EQUALS = "<>"
OPERATOR_GREATER_THAN = ">"
OPERATOR_GREATER_EQUAL = ">="
OPERATOR_LESS_THAN = "<"
OPERATOR_LESS_EQUAL = "<="
OPERATOR_IN = "IN"
OPERATOR_NOT_IN = "NOT IN"
OPERATOR_IS_BLANK = "IS BLANK"
OPERATOR_IS_NOT_BLANK = "IS NOT BLANK"

OPERATOR_CHOICES: list[tuple[str, str]] = [
    ("= (Equals)", OPERATOR_EQUALS),
    ("<> (Does not equal)", OPERATOR_NOT_EQUALS),
    ("> (Greater than)", OPERATOR_GREATER_THAN),
    (">= (Greater than or equal to)", OPERATOR_GREATER_EQUAL),
    ("< (Less than)", OPERATOR_LESS_THAN),
    ("<= (Less than or equal to)", OPERATOR_LESS_EQUAL),
    ("IN (In list / Slicer)", OPERATOR_IN),
    ("NOT IN (Not in list)", OPERATOR_NOT_IN),
    ("IS BLANK (Blank or empty)", OPERATOR_IS_BLANK),
    ("IS NOT BLANK (Has value)", OPERATOR_IS_NOT_BLANK),
]

OPERATOR_TOOLTIPS: dict[str, str] = {
    OPERATOR_EQUALS: "Keeps rows where the column matches this exact value.",
    OPERATOR_NOT_EQUALS: "Keeps rows where the column is different from this value.",
    OPERATOR_GREATER_THAN: "Keeps rows where the column value is strictly greater than this number.",
    OPERATOR_GREATER_EQUAL: "Keeps rows where the column value is greater than or equal to this number.",
    OPERATOR_LESS_THAN: "Keeps rows where the column value is strictly less than this number.",
    OPERATOR_LESS_EQUAL: "Keeps rows where the column value is less than or equal to this number.",
    OPERATOR_IN: 'Keeps rows where the value is in a list (for example: "US", "UK" or 10, 20).',
    OPERATOR_NOT_IN: "Keeps rows where the value is not in the list.",
    OPERATOR_IS_BLANK: "Keeps rows that are empty or have no value.",
    OPERATOR_IS_NOT_BLANK: "Keeps rows that have a value and are not blank.",
}


def escape_dax_table(table_name: str) -> str:
    """Escape a table name for DAX expressions wrapped in single quotes."""
    clean = table_name.strip()
    if not clean:
        return ""
    if clean.startswith("'") and clean.endswith("'") and len(clean) >= 2:
        clean = clean[1:-1]
    escaped = clean.replace("'", "''")
    return f"'{escaped}'"


def escape_dax_column(column_name: str) -> str:
    """Escape a column name for DAX expressions wrapped in square brackets."""
    clean = column_name.strip()
    if not clean:
        return ""
    if clean.startswith("[") and clean.endswith("]") and len(clean) >= 2:
        clean = clean[1:-1]
    return f"[{clean}]"


def format_filter_scalar_value(raw: str) -> str:
    """Format a single value for DAX comparison (quotes text, preserves numbers and booleans)."""
    val = raw.strip()
    if not val:
        return '""'
    # Already double-quoted or single-quoted
    if (val.startswith('"') and val.endswith('"')) or (val.startswith("'") and val.endswith("'")):
        return val
    # Boolean or null literals
    up = val.upper()
    if up in ("TRUE", "FALSE", "BLANK()"):
        return f"{up}()" if not up.endswith("()") else up
    if up in ("TRUE()", "FALSE()"):
        return up
    # Numeric (int or float)
    if re.match(r"^-?\d+(\.\d+)?$", val):
        return val
    # Plain string -> wrap in double quotes, escaping internal quotes
    escaped = val.replace('"', '""')
    return f'"{escaped}"'


def format_filter_in_list(raw: str) -> str:
    """Format a list of values for DAX IN syntax: { "A", "B", 10 }."""
    cleaned = raw.strip()
    if cleaned.startswith("{") and cleaned.endswith("}"):
        cleaned = cleaned[1:-1].strip()

    # Split by comma while respecting quotes
    parts: list[str] = []
    in_quote = False
    quote_char = ""
    cur: list[str] = []
    for ch in cleaned:
        if ch in ('"', "'"):
            if not in_quote:
                in_quote = True
                quote_char = ch
            elif quote_char == ch:
                in_quote = False
            cur.append(ch)
        elif ch == "," and not in_quote:
            item = "".join(cur).strip()
            if item:
                parts.append(item)
            cur = []
        else:
            cur.append(ch)
    if cur:
        item = "".join(cur).strip()
        if item:
            parts.append(item)

    if not parts:
        return '{ "" }'

    formatted = [format_filter_scalar_value(p) for p in parts]
    return "{ " + ", ".join(formatted) + " }"


def build_dax_filter_expression(
    table_name: str,
    column_name: str,
    operator: str,
    value: str,
) -> str:
    """Build a standard Power BI DAX filter expression for CALCULATE."""
    tbl_part = escape_dax_table(table_name) if table_name and table_name.strip() else ""
    col_part = escape_dax_column(column_name) if column_name and column_name.strip() else ""
    if not col_part:
        return ""

    target = f"{tbl_part}{col_part}" if tbl_part else col_part
    op_clean = operator.strip().upper()

    if op_clean in ("IS BLANK", "ISBLANK"):
        return f"ISBLANK({target})"
    if op_clean in ("IS NOT BLANK", "NOT ISBLANK", "NOT BLANK"):
        return f"NOT(ISBLANK({target}))"
    if op_clean == "IN":
        return f"{target} IN {format_filter_in_list(value)}"
    if op_clean == "NOT IN":
        return f"NOT({target} IN {format_filter_in_list(value)})"

    val_part = format_filter_scalar_value(value)
    return f"{target} {operator} {val_part}"


def parse_dax_filter_expression(expr: str) -> dict[str, str] | None:
    """Parse an existing DAX filter expression back into table, column, operator, and value.
    
    Returns a dict with keys 'table', 'column', 'operator', 'value' if matched,
    or None if it is a complex custom expression.
    """
    raw = expr.strip()
    if not raw:
        return None

    # 1. NOT(ISBLANK('Table'[Col])) or NOT(ISBLANK([Col]))
    m_not_blank = re.match(
        r"^NOT\s*\(\s*ISBLANK\s*\(\s*(?:'([^']+)')?\[([^\]]+)\]\s*\)\s*\)$",
        raw,
        re.IGNORECASE,
    )
    if m_not_blank:
        return {
            "table": m_not_blank.group(1) or "",
            "column": m_not_blank.group(2) or "",
            "operator": OPERATOR_IS_NOT_BLANK,
            "value": "",
        }

    # 2. ISBLANK('Table'[Col]) or ISBLANK([Col])
    m_blank = re.match(
        r"^ISBLANK\s*\(\s*(?:'([^']+)')?\[([^\]]+)\]\s*\)$",
        raw,
        re.IGNORECASE,
    )
    if m_blank:
        return {
            "table": m_blank.group(1) or "",
            "column": m_blank.group(2) or "",
            "operator": OPERATOR_IS_BLANK,
            "value": "",
        }

    # 3. NOT('Table'[Col] IN { ... })
    m_not_in = re.match(
        r"^NOT\s*\(\s*(?:'([^']+)')?\[([^\]]+)\]\s+IN\s+\{\s*(.*?)\s*\}\s*\)$",
        raw,
        re.IGNORECASE,
    )
    if m_not_in:
        return {
            "table": m_not_in.group(1) or "",
            "column": m_not_in.group(2) or "",
            "operator": OPERATOR_NOT_IN,
            "value": m_not_in.group(3) or "",
        }

    # 4. 'Table'[Col] IN { ... }
    m_in = re.match(
        r"^(?:'([^']+)')?\[([^\]]+)\]\s+IN\s+\{\s*(.*?)\s*\}$",
        raw,
        re.IGNORECASE,
    )
    if m_in:
        return {
            "table": m_in.group(1) or "",
            "column": m_in.group(2) or "",
            "operator": OPERATOR_IN,
            "value": m_in.group(3) or "",
        }

    # 5. 'Table'[Col] <op> <val>
    m_op = re.match(
        r"^(?:'([^']+)')?\[([^\]]+)\]\s*(=|<>|>=|<=|>|<)\s*(.+)$",
        raw,
    )
    if m_op:
        v = (m_op.group(4) or "").strip()
        if (v.startswith('"') and v.endswith('"')) or (v.startswith("'") and v.endswith("'")):
            v = v[1:-1].replace('""', '"')
        return {
            "table": m_op.group(1) or "",
            "column": m_op.group(2) or "",
            "operator": m_op.group(3) or "=",
            "value": v,
        }

    return None


class FilterBuilderDialog(EnterpriseDialog):
    """Compact, professional popup dialog for creating or editing a Power BI / DAX filter condition.
    
    Uses a neat 2x2 grid (Table | Column, Condition | Value) with live DAX preview
    to keep the dialog clean, rectangular, and comfortably sized.
    """

    def __init__(
        self,
        *,
        filter_index: int = 1,
        current_expression: str = "",
        workspace_id: str = "",
        dataset_id: str = "",
        table_name: str = "",
        metadata_service: Any | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setModal(True)
        self.setFixedWidth(460)
        self.setWindowTitle(f"Configure Filter {filter_index}")
        self.setObjectName("FilterBuilderDialog")
        self.setStyleSheet(
            "QDialog { background: #FFFFFF; font-family: Segoe UI, -apple-system, sans-serif; }"
        )

        self._filter_index = filter_index
        self._initial_expression = current_expression.strip()
        self._workspace_id = workspace_id
        self._dataset_id = dataset_id
        self._initial_table = table_name.strip()
        self._metadata_service = metadata_service

        self._result_expression: str = self._initial_expression

        self._build_ui()
        self._populate_tables()
        self._load_initial_state()
        self._update_preview()

    @property
    def generated_expression(self) -> str:
        """The final generated or custom DAX filter expression."""
        return self._result_expression

    def _build_ui(self) -> None:
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(18, 16, 18, 16)
        main_layout.setSpacing(10)

        # 1. Sleek Compact Header
        h_layout = QHBoxLayout()
        lbl_title = QLabel(f"Filter {self._filter_index} Condition Builder")
        lbl_title.setStyleSheet("font-size: 13px; font-weight: 700; color: #16243A;")
        h_layout.addWidget(lbl_title)

        h_layout.addStretch()

        badge = QLabel("DAX CALCULATE")
        badge.setStyleSheet(
            "font-size: 10px; font-weight: 600; color: #2563EB; background: #EFF6FF; "
            "border: 1px solid #BFDBFE; border-radius: 3px; padding: 2px 6px;"
        )
        h_layout.addWidget(badge)
        main_layout.addLayout(h_layout)

        # 2. Compact 2x2 Grid Form (Table | Column, Condition | Value)
        self.grid_container = QWidget()
        grid = QGridLayout(self.grid_container)
        grid.setContentsMargins(0, 2, 0, 2)
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(8)

        # Row 0 & 1: Table (left) and Column (right)
        lbl_table = QLabel("Table Name:")
        lbl_table.setStyleSheet("font-size: 11px; font-weight: 600; color: #334155;")
        self.combo_table = QComboBox()
        self.combo_table.setEditable(True)
        self.combo_table.setPlaceholderText("Select or enter table")
        self.combo_table.setToolTip("Choose or type the table name to apply this filter to.")
        self.combo_table.setStyleSheet(
            "QComboBox { background: #FFFFFF; border: 1px solid #CBD5E1; border-radius: 4px; "
            "padding: 4px 7px; font-size: 11px; color: #16243A; } "
            "QComboBox:focus { border-color: #2563EB; }"
        )
        self.combo_table.currentTextChanged.connect(self._on_table_changed)

        lbl_col = QLabel("Column Name:")
        lbl_col.setStyleSheet("font-size: 11px; font-weight: 600; color: #334155;")
        self.combo_column = QComboBox()
        self.combo_column.setEditable(True)
        self.combo_column.setPlaceholderText("Select or enter column")
        self.combo_column.setToolTip("Choose or type the column name to filter.")
        self.combo_column.setStyleSheet(
            "QComboBox { background: #FFFFFF; border: 1px solid #CBD5E1; border-radius: 4px; "
            "padding: 4px 7px; font-size: 11px; color: #16243A; } "
            "QComboBox:focus { border-color: #2563EB; }"
        )
        self.combo_column.currentTextChanged.connect(lambda _: self._update_preview())

        grid.addWidget(lbl_table, 0, 0)
        grid.addWidget(lbl_col, 0, 1)
        grid.addWidget(self.combo_table, 1, 0)
        grid.addWidget(self.combo_column, 1, 1)

        # Row 2 & 3: Condition (left) and Value (right)
        lbl_op = QLabel("Condition / Operator:")
        lbl_op.setStyleSheet("font-size: 11px; font-weight: 600; color: #334155;")
        self.combo_operator = QComboBox()
        for label, op_code in OPERATOR_CHOICES:
            tip = OPERATOR_TOOLTIPS.get(op_code, "")
            self.combo_operator.addItem(label, op_code)
            if tip:
                self.combo_operator.setItemData(self.combo_operator.count() - 1, tip, Qt.ItemDataRole.ToolTipRole)
        self.combo_operator.setStyleSheet(
            "QComboBox { background: #FFFFFF; border: 1px solid #CBD5E1; border-radius: 4px; "
            "padding: 4px 7px; font-size: 11px; color: #16243A; } "
            "QComboBox:focus { border-color: #2563EB; }"
        )
        self.combo_operator.setToolTip(OPERATOR_TOOLTIPS.get(OPERATOR_EQUALS, ""))
        self.combo_operator.currentIndexChanged.connect(self._on_operator_changed)

        self.lbl_value = QLabel("Filter Value:")
        self.lbl_value.setStyleSheet("font-size: 11px; font-weight: 600; color: #334155;")
        self.input_value = QLineEdit()
        self.input_value.setPlaceholderText("e.g. Completed or 2024")
        self.input_value.setToolTip("Enter the filter value (for example: Completed or 2024).")
        self.input_value.setStyleSheet(
            "QLineEdit { background: #FFFFFF; border: 1px solid #CBD5E1; border-radius: 4px; "
            "padding: 4px 7px; font-size: 11px; color: #16243A; } "
            "QLineEdit:focus { border-color: #2563EB; } "
            "QLineEdit:disabled { background: #F1F5F9; color: #94A3B8; }"
        )
        self.input_value.textChanged.connect(lambda _: self._update_preview())

        grid.addWidget(lbl_op, 2, 0)
        grid.addWidget(self.lbl_value, 2, 1)
        grid.addWidget(self.combo_operator, 3, 0)
        grid.addWidget(self.input_value, 3, 1)

        main_layout.addWidget(self.grid_container)

        # 3. Custom DAX toggle and input
        custom_box = QFrame()
        c_layout = QVBoxLayout(custom_box)
        c_layout.setContentsMargins(0, 0, 0, 0)
        c_layout.setSpacing(4)

        self.chk_custom_dax = QCheckBox("Custom DAX expression")
        self.chk_custom_dax.setToolTip("Check this box to type your own custom DAX formula.")
        self.chk_custom_dax.setStyleSheet(
            "QCheckBox { font-size: 11px; font-weight: 500; color: #475569; } "
            "QCheckBox::indicator { width: 13px; height: 13px; }"
        )
        self.chk_custom_dax.toggled.connect(self._on_custom_toggle)
        c_layout.addWidget(self.chk_custom_dax)

        self.input_custom_dax = QLineEdit()
        self.input_custom_dax.setPlaceholderText("Write DAX expression (e.g. 'Dates'[Year] = 2024)")
        self.input_custom_dax.setToolTip("Type a custom Power BI filter formula (for example: 'Dates'[Year] = 2024).")
        self.input_custom_dax.setStyleSheet(
            "QLineEdit { background: #FFFFFF; border: 1px solid #CBD5E1; border-radius: 4px; "
            "padding: 4px 7px; font-size: 11px; font-family: Consolas, monospace; color: #16243A; } "
            "QLineEdit:focus { border-color: #2563EB; }"
        )
        self.input_custom_dax.setVisible(False)
        self.input_custom_dax.textChanged.connect(lambda _: self._update_preview())
        c_layout.addWidget(self.input_custom_dax)

        main_layout.addWidget(custom_box)

        # 4. Sleek DAX Preview Box
        preview_card = QFrame()
        preview_card.setToolTip("Preview of the generated DAX filter formula.")
        preview_card.setStyleSheet(
            "QFrame { background: #16243A; border-radius: 5px; padding: 6px 10px; }"
        )
        p_layout = QHBoxLayout(preview_card)
        p_layout.setContentsMargins(4, 2, 4, 2)
        p_layout.setSpacing(8)

        lbl_prev_title = QLabel("DAX:")
        lbl_prev_title.setStyleSheet("font-size: 10px; font-weight: 700; color: #94A3B8; font-family: Consolas;")
        p_layout.addWidget(lbl_prev_title)

        self.lbl_preview_code = QLabel("- (Empty filter)")
        self.lbl_preview_code.setStyleSheet(
            "font-family: Consolas, 'Courier New', monospace; font-size: 11px; font-weight: 600; color: #38BDF8;"
        )
        self.lbl_preview_code.setWordWrap(True)
        self.lbl_preview_code.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        p_layout.addWidget(self.lbl_preview_code, 1)

        main_layout.addWidget(preview_card)

        # 5. Action Buttons
        btn_layout = QHBoxLayout()
        btn_layout.setContentsMargins(0, 4, 0, 0)
        btn_layout.setSpacing(8)

        self.btn_clear = QPushButton("Clear Filter")
        self.btn_clear.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_clear.setToolTip("Remove this filter and leave the cell blank.")
        self.btn_clear.setStyleSheet(
            "QPushButton { background: #FFFFFF; color: #DC2626; border: 1px solid #FCA5A5; "
            "border-radius: 4px; padding: 5px 12px; font-size: 11px; font-weight: 600; } "
            "QPushButton:hover { background: #FEF2F2; border-color: #EF4444; }"
        )
        self.btn_clear.clicked.connect(self._handle_clear)
        btn_layout.addWidget(self.btn_clear)

        btn_layout.addStretch()

        self.btn_cancel = QPushButton("Cancel")
        self.btn_cancel.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_cancel.setToolTip("Close without saving changes.")
        self.btn_cancel.setStyleSheet(
            "QPushButton { background: #FFFFFF; color: #475569; border: 1px solid #CBD5E1; "
            "border-radius: 4px; padding: 5px 14px; font-size: 11px; font-weight: 500; } "
            "QPushButton:hover { background: #F8FAFC; color: #1E293B; }"
        )
        self.btn_cancel.clicked.connect(self.reject)
        btn_layout.addWidget(self.btn_cancel)

        self.btn_apply = QPushButton("Apply Filter")
        self.btn_apply.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_apply.setToolTip("Save and use this filter.")
        self.btn_apply.setStyleSheet(
            "QPushButton { background: #2563EB; color: #FFFFFF; border: 1px solid #2563EB; "
            "border-radius: 4px; padding: 5px 16px; font-size: 11px; font-weight: 700; } "
            "QPushButton:hover { background: #1D4ED8; border-color: #1D4ED8; } "
            "QPushButton:disabled { background: #93C5FD; border-color: #93C5FD; color: #EFF6FF; }"
        )
        self.btn_apply.clicked.connect(self._handle_apply)
        btn_layout.addWidget(self.btn_apply)

        main_layout.addLayout(btn_layout)

    def _populate_tables(self) -> None:
        """Populate the table combo from metadata service if available."""
        self.combo_table.blockSignals(True)
        self.combo_table.clear()

        table_names: list[str] = []
        if self._metadata_service is not None and self._workspace_id and self._dataset_id:
            try:
                meta = self._metadata_service.get_cached_metadata(self._workspace_id, self._dataset_id)
                if meta is not None and meta.table_names:
                    table_names = list(meta.table_names)
            except Exception as e:
                logger.debug("Failed to retrieve cached table names: %s", e)

        for tbl in table_names:
            self.combo_table.addItem(tbl, tbl)

        # Select initial table if given
        if self._initial_table:
            idx = self.combo_table.findText(self._initial_table)
            if idx >= 0:
                self.combo_table.setCurrentIndex(idx)
            else:
                self.combo_table.setEditText(self._initial_table)
        elif table_names:
            self.combo_table.setCurrentIndex(0)
        else:
            self.combo_table.setCurrentIndex(-1)

        self.combo_table.blockSignals(False)
        self._populate_columns()

    def _on_table_changed(self, _: str) -> None:
        self._populate_columns()
        self._update_preview()

    def _populate_columns(self) -> None:
        """Populate the column combo from the currently selected table's metadata."""
        current_col = self.combo_column.currentText().strip()
        self.combo_column.blockSignals(True)
        self.combo_column.clear()

        selected_table = self.combo_table.currentText().strip()
        columns: list[str] = []
        if self._metadata_service is not None and self._workspace_id and self._dataset_id and selected_table:
            try:
                meta = self._metadata_service.get_cached_metadata(self._workspace_id, self._dataset_id)
                if meta is not None:
                    tbl_meta = None
                    if hasattr(meta, "get_table"):
                        tbl_meta = meta.get_table(selected_table)
                    elif hasattr(meta, "tables"):
                        if isinstance(meta.tables, dict):
                            tbl_meta = meta.tables.get(selected_table)
                        elif isinstance(meta.tables, list):
                            for t in meta.tables:
                                if getattr(t, "name", "").lower() == selected_table.lower():
                                    tbl_meta = t
                                    break
                    if tbl_meta is not None and hasattr(tbl_meta, "column_names"):
                        columns = list(tbl_meta.column_names)
            except Exception as e:
                logger.debug("Failed to retrieve columns for table %s: %s", selected_table, e)

        for col in columns:
            self.combo_column.addItem(col, col)

        if current_col:
            idx = self.combo_column.findText(current_col)
            if idx >= 0:
                self.combo_column.setCurrentIndex(idx)
            else:
                self.combo_column.setEditText(current_col)
        elif columns:
            self.combo_column.setCurrentIndex(0)
        else:
            self.combo_column.setCurrentIndex(-1)

        self.combo_column.blockSignals(False)

    def _load_initial_state(self) -> None:
        """Parse initial filter expression if present, or set sensible defaults."""
        if not self._initial_expression:
            return

        parsed = parse_dax_filter_expression(self._initial_expression)
        if parsed is not None:
            # Structured filter matched
            tbl = parsed.get("table", "")
            if tbl:
                idx = self.combo_table.findText(tbl)
                if idx >= 0:
                    self.combo_table.setCurrentIndex(idx)
                else:
                    self.combo_table.setEditText(tbl)
                self._populate_columns()

            col = parsed.get("column", "")
            if col:
                idx = self.combo_column.findText(col)
                if idx >= 0:
                    self.combo_column.setCurrentIndex(idx)
                else:
                    self.combo_column.setEditText(col)

            op = parsed.get("operator", OPERATOR_EQUALS)
            for i in range(self.combo_operator.count()):
                if self.combo_operator.itemData(i) == op:
                    self.combo_operator.setCurrentIndex(i)
                    break

            val = parsed.get("value", "")
            self.input_value.setText(val)
        else:
            # Complex or custom DAX expression: open in custom DAX mode
            self.chk_custom_dax.setChecked(True)
            self.input_custom_dax.setText(self._initial_expression)

    def _on_operator_changed(self, _: int) -> None:
        op = str(self.combo_operator.currentData() or OPERATOR_EQUALS)
        tip = OPERATOR_TOOLTIPS.get(op, "")
        if tip:
            self.combo_operator.setToolTip(tip)
        if op in (OPERATOR_IS_BLANK, OPERATOR_IS_NOT_BLANK):
            self.input_value.setEnabled(False)
            self.input_value.setPlaceholderText("(Not required for blank checks)")
        elif op in (OPERATOR_IN, OPERATOR_NOT_IN):
            self.input_value.setEnabled(True)
            self.input_value.setPlaceholderText('e.g. "US", "UK" or 10, 20')
        else:
            self.input_value.setEnabled(True)
            self.input_value.setPlaceholderText('e.g. Completed or 2024')
        self._update_preview()

    def _on_custom_toggle(self, checked: bool) -> None:
        self.input_custom_dax.setVisible(checked)
        self.combo_table.setEnabled(not checked)
        self.combo_column.setEnabled(not checked)
        self.combo_operator.setEnabled(not checked)
        self.input_value.setEnabled(not checked and self.combo_operator.currentData() not in (OPERATOR_IS_BLANK, OPERATOR_IS_NOT_BLANK))

        if checked and not self.input_custom_dax.text().strip():
            # Seed with current builder preview
            cur_prev = self._compute_builder_expression()
            if cur_prev:
                self.input_custom_dax.setText(cur_prev)

        self._update_preview()

    def _compute_builder_expression(self) -> str:
        table = self.combo_table.currentText().strip()
        col = self.combo_column.currentText().strip()
        op = str(self.combo_operator.currentData() or OPERATOR_EQUALS)
        val = self.input_value.text().strip()

        if not col:
            return ""

        return build_dax_filter_expression(
            table_name=table,
            column_name=col,
            operator=op,
            value=val,
        )

    def _update_preview(self) -> None:
        if self.chk_custom_dax.isChecked():
            expr = self.input_custom_dax.text().strip()
        else:
            expr = self._compute_builder_expression()

        if expr:
            self.lbl_preview_code.setText(expr)
            self.btn_apply.setEnabled(True)
        else:
            self.lbl_preview_code.setText("- (Empty filter)")
            self.btn_apply.setEnabled(self.chk_custom_dax.isChecked() or not bool(self.combo_column.currentText().strip()))

    def _handle_apply(self) -> None:
        if self.chk_custom_dax.isChecked():
            self._result_expression = self.input_custom_dax.text().strip()
        else:
            self._result_expression = self._compute_builder_expression()
        self.accept()

    def _handle_clear(self) -> None:
        self._result_expression = ""
        self.accept()
