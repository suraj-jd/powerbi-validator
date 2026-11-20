"""Unit tests for DictTableModel and TableFilterProxyModel."""

from __future__ import annotations

from PySide6.QtCore import Qt

from app.core.status import ValidationStatus
from app.ui.models.dict_table_model import ColumnSpec, DictTableModel, TableFilterProxyModel


def _sample_columns() -> list[ColumnSpec]:
    return [
        ColumnSpec(key="sr", header="SR"),
        ColumnSpec(key="name", header="Check"),
        ColumnSpec(key="status", header="Status", is_status=True),
    ]


def test_dict_table_model_crud_and_blank_formatting() -> None:
    model = DictTableModel(
        columns=_sample_columns(),
        rows=[
            {"sr": 1, "name": "Null Check", "status": ValidationStatus.PASS.value},
            {"sr": 2, "name": "", "status": ValidationStatus.FAIL.value},
        ],
    )

    assert model.rowCount() == 2
    assert model.columnCount() == 3
    assert model.headerData(1, Qt.Orientation.Horizontal) == "Check"
    assert model.data(model.index(0, 1)) == "Null Check"
    assert model.data(model.index(1, 1)) == "-"

    # Status column returns foreground and background brushes
    assert model.data(model.index(0, 2), Qt.ItemDataRole.ForegroundRole) is not None
    assert model.data(model.index(0, 2), Qt.ItemDataRole.BackgroundRole) is not None

    model.add_row({"sr": 3, "name": "Refresh Check", "status": ValidationStatus.WARNING.value})
    assert model.rowCount() == 3

    model.update_row(1, {"sr": 2, "name": "Duplicate Check", "status": ValidationStatus.ERROR.value})
    assert model.row_at(1)["name"] == "Duplicate Check"

    removed = model.remove_row(0)
    assert removed["sr"] == 1
    assert model.rowCount() == 2


def test_table_filter_proxy_search_column_filter_and_numeric_sort() -> None:
    model = DictTableModel(
        columns=_sample_columns(),
        rows=[
            {"sr": 10, "name": "DAX Measure", "status": ValidationStatus.PASS.value},
            {"sr": 2, "name": "Null Check", "status": ValidationStatus.FAIL.value},
            {"sr": 1, "name": "Anomaly Check", "status": ValidationStatus.WARNING.value},
        ],
    )
    proxy = TableFilterProxyModel()
    proxy.setSourceModel(model)

    # Numeric sort on SR column should order 1, 2, 10 (not "1", "10", "2")
    proxy.sort(0, Qt.SortOrder.AscendingOrder)
    ordered_sr = [proxy.data(proxy.index(r, 0)) for r in range(proxy.rowCount())]
    assert ordered_sr == ["1", "2", "10"]

    # Search filter
    proxy.set_search_text("null")
    assert proxy.rowCount() == 1
    assert proxy.data(proxy.index(0, 1)) == "Null Check"

    # Column filter
    proxy.clear_filters()
    proxy.set_column_filter(2, ValidationStatus.WARNING.value)
    assert proxy.rowCount() == 1
    assert proxy.data(proxy.index(0, 1)) == "Anomaly Check"
