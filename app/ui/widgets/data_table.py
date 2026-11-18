"""Reusable enterprise table widget combining QTableView, DictTableModel, and filters."""

from __future__ import annotations

from typing import Any

from PySide6.QtCore import QModelIndex, Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QHBoxLayout,
    QHeaderView,
    QLineEdit,
    QTableView,
    QVBoxLayout,
    QWidget,
)

from app.ui.models.dict_table_model import ColumnSpec, DictTableModel, TableFilterProxyModel


class DataTableWidget(QWidget):
    """Searchable, sortable, status-filterable table built on Qt Model/View."""

    row_activated = Signal(dict)

    def __init__(
        self,
        columns: list[ColumnSpec],
        *,
        rows: list[dict[str, Any]] | None = None,
        show_search: bool = True,
        filter_column_key: str | None = None,
        filter_options: list[str] | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._filter_column_key = filter_column_key

        self.source_model = DictTableModel(columns=columns, rows=rows, parent=self)
        self.proxy_model = TableFilterProxyModel(parent=self)
        self.proxy_model.setSourceModel(self.source_model)

        self.search_input: QLineEdit | None = None
        self.filter_combo: QComboBox | None = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        if show_search or filter_column_key:
            toolbar = QHBoxLayout()
            toolbar.setSpacing(10)

            if show_search:
                self.search_input = QLineEdit(self)
                self.search_input.setObjectName("SearchInput")
                self.search_input.setPlaceholderText("Search table...")
                self.search_input.setClearButtonEnabled(True)
                self.search_input.textChanged.connect(self.proxy_model.set_search_text)
                toolbar.addWidget(self.search_input, stretch=1)

            if filter_column_key:
                self.filter_combo = QComboBox(self)
                self.filter_combo.setObjectName("FilterCombo")
                self.filter_combo.addItem("All", "")
                for option in filter_options or []:
                    self.filter_combo.addItem(option, option)
                self.filter_combo.currentIndexChanged.connect(self._on_filter_changed)
                toolbar.addWidget(self.filter_combo)

            layout.addLayout(toolbar)

        self.table_view = QTableView(self)
        self.table_view.setObjectName("EnterpriseTableView")
        self.table_view.setModel(self.proxy_model)
        self.table_view.setSortingEnabled(True)
        self.table_view.sortByColumn(-1, Qt.SortOrder.AscendingOrder)
        self.table_view.setAlternatingRowColors(True)
        self.table_view.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table_view.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table_view.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table_view.setShowGrid(False)
        self.table_view.verticalHeader().setVisible(False)
        self.table_view.verticalHeader().setDefaultSectionSize(34)

        header = self.table_view.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        header.setStretchLastSection(True)
        header.setDefaultAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)

        self.table_view.doubleClicked.connect(self._on_double_clicked)
        layout.addWidget(self.table_view)

    def _on_filter_changed(self, _index: int) -> None:
        if self.filter_combo is None or not self._filter_column_key:
            return
        col_idx = self.source_model.column_index(self._filter_column_key)
        value = str(self.filter_combo.currentData() or "")
        self.proxy_model.set_column_filter(col_idx, value or None)

    def _on_double_clicked(self, proxy_index: QModelIndex) -> None:
        source_index = self.proxy_model.mapToSource(proxy_index)
        if source_index.isValid():
            self.row_activated.emit(self.source_model.row_at(source_index.row()))

    def set_rows(self, rows: list[dict[str, Any]]) -> None:
        """Replace all rows displayed in the table."""
        self.source_model.set_rows(rows)

    def visible_row_count(self) -> int:
        """Return the number of rows currently visible after filtering."""
        return self.proxy_model.rowCount()
