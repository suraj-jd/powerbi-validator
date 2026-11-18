"""Reusable Qt Model/View table model and filter proxy for dictionary-backed rows."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from PySide6.QtCore import QAbstractTableModel, QModelIndex, QSortFilterProxyModel, Qt
from PySide6.QtGui import QBrush, QColor, QFont

from app.core.status import ValidationStatus

_STATUS_COLORS: dict[str, tuple[str, str]] = {
    ValidationStatus.PASS.value: ("#15803D", "#DCFCE7"),
    ValidationStatus.FAIL.value: ("#B91C1C", "#FEE2E2"),
    ValidationStatus.WARNING.value: ("#B45309", "#FEF3C7"),
    ValidationStatus.ERROR.value: ("#9F1239", "#FFE4E6"),
}

RAW_VALUE_ROLE = int(Qt.ItemDataRole.UserRole) + 1


@dataclass(frozen=True, slots=True)
class ColumnSpec:
    """Metadata describing one column in a DictTableModel."""

    key: str
    header: str
    alignment: Qt.AlignmentFlag = Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
    is_status: bool = False


class DictTableModel(QAbstractTableModel):
    """Lightweight Qt table model backed by a list of dictionaries."""

    def __init__(
        self,
        columns: list[ColumnSpec],
        rows: list[dict[str, Any]] | None = None,
        parent: Any = None,
    ) -> None:
        super().__init__(parent)
        self._columns = list(columns)
        self._rows: list[dict[str, Any]] = [dict(r) for r in (rows or [])]

    @property
    def columns(self) -> list[ColumnSpec]:
        return list(self._columns)

    def column_index(self, key: str) -> int:
        """Return the integer column index for a column key, or -1 if absent."""
        for idx, col in enumerate(self._columns):
            if col.key == key:
                return idx
        return -1

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:
        if parent.isValid():
            return 0
        return len(self._rows)

    def columnCount(self, parent: QModelIndex = QModelIndex()) -> int:
        if parent.isValid():
            return 0
        return len(self._columns)

    def headerData(
        self,
        section: int,
        orientation: Qt.Orientation,
        role: int = Qt.ItemDataRole.DisplayRole,
    ) -> Any:
        if role != Qt.ItemDataRole.DisplayRole:
            return None
        if orientation == Qt.Orientation.Horizontal and 0 <= section < len(self._columns):
            return self._columns[section].header
        if orientation == Qt.Orientation.Vertical:
            return str(section + 1)
        return None

    def data(
        self,
        index: QModelIndex,
        role: int = Qt.ItemDataRole.DisplayRole,
    ) -> Any:
        if not index.isValid():
            return None
        row_idx = index.row()
        col_idx = index.column()
        if not (0 <= row_idx < len(self._rows) and 0 <= col_idx < len(self._columns)):
            return None

        col = self._columns[col_idx]
        raw_value = self._rows[row_idx].get(col.key)

        if role == RAW_VALUE_ROLE:
            return raw_value

        if role == Qt.ItemDataRole.DisplayRole:
            if raw_value is None or raw_value == "":
                return "—"
            return str(raw_value)

        if role == Qt.ItemDataRole.TextAlignmentRole:
            return int(col.alignment)

        if col.is_status and raw_value is not None:
            normalized = str(raw_value).strip().upper()
            colors = _STATUS_COLORS.get(normalized)
            if colors is not None:
                fg_hex, bg_hex = colors
                if role == Qt.ItemDataRole.ForegroundRole:
                    return QBrush(QColor(fg_hex))
                if role == Qt.ItemDataRole.BackgroundRole:
                    return QBrush(QColor(bg_hex))
                if role == Qt.ItemDataRole.FontRole:
                    font = QFont()
                    font.setBold(True)
                    return font

        return None

    def set_rows(self, rows: list[dict[str, Any]]) -> None:
        """Replace all table rows atomically."""
        self.beginResetModel()
        self._rows = [dict(r) for r in rows]
        self.endResetModel()

    def add_row(self, row: dict[str, Any]) -> None:
        """Append a single row to the end of the model."""
        pos = len(self._rows)
        self.beginInsertRows(QModelIndex(), pos, pos)
        self._rows.append(dict(row))
        self.endInsertRows()

    def update_row(self, row_index: int, row: dict[str, Any]) -> None:
        """Update an existing row by index."""
        if not 0 <= row_index < len(self._rows):
            raise IndexError(f"Row index out of range: {row_index}")
        self._rows[row_index] = dict(row)
        top_left = self.index(row_index, 0)
        bottom_right = self.index(row_index, max(0, len(self._columns) - 1))
        self.dataChanged.emit(top_left, bottom_right)

    def remove_row(self, row_index: int) -> dict[str, Any]:
        """Remove and return a row by index."""
        if not 0 <= row_index < len(self._rows):
            raise IndexError(f"Row index out of range: {row_index}")
        self.beginRemoveRows(QModelIndex(), row_index, row_index)
        removed = self._rows.pop(row_index)
        self.endRemoveRows()
        return removed

    def row_at(self, row_index: int) -> dict[str, Any]:
        """Return a shallow copy of the row dictionary at the given index."""
        if not 0 <= row_index < len(self._rows):
            raise IndexError(f"Row index out of range: {row_index}")
        return dict(self._rows[row_index])

    def all_rows(self) -> list[dict[str, Any]]:
        """Return shallow copies of all rows currently in the model."""
        return [dict(r) for r in self._rows]


class TableFilterProxyModel(QSortFilterProxyModel):
    """Sortable proxy supporting full-row text search and exact column filters."""

    def __init__(self, parent: Any = None) -> None:
        super().__init__(parent)
        self._search_text = ""
        self._column_filters: dict[int, str] = {}
        self.setSortCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)

    def set_search_text(self, text: str) -> None:
        """Filter rows containing `text` (case-insensitive) in any column."""
        normalized = text.strip().lower()
        if normalized != self._search_text:
            if hasattr(self, "beginFilterChange") and hasattr(self, "endFilterChange"):
                self.beginFilterChange()
                self._search_text = normalized
                self.endFilterChange(QSortFilterProxyModel.Direction.Rows)
            else:
                self._search_text = normalized
                self.invalidateFilter()

    def set_column_filter(self, column_index: int, expected_value: str | None) -> None:
        """Require an exact case-insensitive match on one column, or clear if None/empty."""
        if column_index < 0:
            return
        if hasattr(self, "beginFilterChange") and hasattr(self, "endFilterChange"):
            self.beginFilterChange()
            if not expected_value:
                self._column_filters.pop(column_index, None)
            else:
                self._column_filters[column_index] = expected_value.strip().lower()
            self.endFilterChange(QSortFilterProxyModel.Direction.Rows)
        else:
            if not expected_value:
                self._column_filters.pop(column_index, None)
            else:
                self._column_filters[column_index] = expected_value.strip().lower()
            self.invalidateFilter()

    def clear_filters(self) -> None:
        """Clear both text search and column filters."""
        if hasattr(self, "beginFilterChange") and hasattr(self, "endFilterChange"):
            self.beginFilterChange()
            self._search_text = ""
            self._column_filters.clear()
            self.endFilterChange(QSortFilterProxyModel.Direction.Rows)
        else:
            self._search_text = ""
            self._column_filters.clear()
            self.invalidateFilter()

    def filterAcceptsRow(self, source_row: int, source_parent: QModelIndex) -> bool:
        model = self.sourceModel()
        if model is None:
            return True

        for col_idx, expected in self._column_filters.items():
            idx = model.index(source_row, col_idx, source_parent)
            cell_text = str(model.data(idx, Qt.ItemDataRole.DisplayRole) or "").strip().lower()
            if cell_text != expected:
                return False

        if self._search_text:
            for col_idx in range(model.columnCount(source_parent)):
                idx = model.index(source_row, col_idx, source_parent)
                cell_text = str(model.data(idx, Qt.ItemDataRole.DisplayRole) or "").lower()
                if self._search_text in cell_text:
                    return True
            return False

        return True

    def lessThan(self, left: QModelIndex, right: QModelIndex) -> bool:
        model = self.sourceModel()
        if model is None:
            return super().lessThan(left, right)

        left_val = model.data(left, RAW_VALUE_ROLE)
        right_val = model.data(right, RAW_VALUE_ROLE)

        if isinstance(left_val, (int, float)) and isinstance(right_val, (int, float)):
            return left_val < right_val

        return str(left_val or "").lower() < str(right_val or "").lower()
