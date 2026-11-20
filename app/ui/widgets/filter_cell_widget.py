"""Filter cell widget with an embedded bold 'Add' / 'Edit' button for SheetSettingsPage.

Subclasses QLineEdit to preserve complete drop-in compatibility with existing table
rendering, cellWidget inspections, and textChanged signal bindings.
"""

from __future__ import annotations

import logging
from typing import Any, Callable

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QResizeEvent
from PySide6.QtWidgets import QLineEdit, QPushButton, QWidget

from app.ui.dialogs.filter_builder_dialog import FilterBuilderDialog

logger = logging.getLogger(__name__)


class FilterCellWidget(QLineEdit):
    """Table cell line edit with a right-docked bold 'Add' or 'Edit' button.
    
    Clicking the button launches the FilterBuilderDialog popup, allowing users
    to pick tables, columns, operators (=, <>, <, >, <=, >=, IN, NOT IN, IS BLANK,
    IS NOT BLANK), and values with live DAX preview.
    """

    filterApplied = Signal(str)

    def __init__(
        self,
        text: str = "",
        *,
        filter_index: int = 1,
        get_context_callback: Callable[[], dict[str, Any]] | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(text, parent)
        self._filter_index = filter_index
        self._get_context = get_context_callback

        self.setObjectName(f"FilterInput_{filter_index}")
        self.setPlaceholderText(f"Filter {filter_index} (Optional)")
        self.setToolTip(
            f"Optional DAX filter condition {filter_index} for CALCULATE. Click 'Add' or edit directly."
        )

        self.setStyleSheet(
            "QLineEdit { background: #FFFFFF; border: 1px solid #E2E8F0; border-radius: 3px; "
            "padding: 2px 46px 2px 6px; font-size: 11px; font-family: Consolas, 'Courier New', monospace; color: #0F172A; } "
            "QLineEdit:focus { border: 1px solid #1668DC; background: #F8FAFC; } "
            "QLineEdit:disabled { background: #F1F5F9; color: #94A3B8; border-color: #E2E8F0; }"
        )

        # Embedded right-docked bold Add / Edit button
        self.btn_add = QPushButton("Add", self)
        self.btn_add.setObjectName(f"FilterBtn_{filter_index}")
        self.btn_add.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.btn_add.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_add.setStyleSheet(
            "QPushButton { font-weight: 700; color: #1668DC; background: #EFF6FF; "
            "border: 1px solid #BFDBFE; border-radius: 3px; font-size: 10px; margin: 0; padding: 0 4px; } "
            "QPushButton:hover { background: #DBEAFE; color: #1D4ED8; border-color: #3B82F6; } "
            "QPushButton:disabled { color: #94A3B8; background: #F1F5F9; border-color: #E2E8F0; }"
        )
        self.btn_add.clicked.connect(self.open_filter_builder)

        self.textChanged.connect(self._sync_button_state)
        self._sync_button_state()

    def _sync_button_state(self) -> None:
        has_text = bool(self.text().strip())
        if has_text:
            self.btn_add.setText("Edit")
            self.btn_add.setToolTip(f"Edit Filter {self._filter_index} condition in popup")
        else:
            self.btn_add.setText("Add")
            self.btn_add.setToolTip(f"Add Filter {self._filter_index} condition via popup")

    def setEnabled(self, enabled: bool) -> None:
        super().setEnabled(enabled)
        self.btn_add.setVisible(enabled)

    def resizeEvent(self, event: QResizeEvent) -> None:
        super().resizeEvent(event)
        btn_w = 38
        btn_h = min(20, max(16, self.height() - 6))
        y = (self.height() - btn_h) // 2
        x = self.width() - btn_w - 4
        self.btn_add.setGeometry(x, y, btn_w, btn_h)

    def open_filter_builder(self) -> None:
        """Open the FilterBuilderDialog popup to edit this cell's filter condition."""
        ctx = self._get_context() if self._get_context else {}
        dialog = FilterBuilderDialog(
            filter_index=self._filter_index,
            current_expression=self.text(),
            workspace_id=ctx.get("workspace_id", ""),
            dataset_id=ctx.get("dataset_id", ""),
            table_name=ctx.get("table_name", ""),
            metadata_service=ctx.get("metadata_service"),
            parent=self.window(),
        )
        if dialog.exec():
            new_expr = dialog.generated_expression
            self.setText(new_expr)
            self.filterApplied.emit(new_expr)
            self.setFocus()
