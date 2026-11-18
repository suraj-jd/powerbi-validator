"""Unit tests for Stage 6 semantic model metadata models and object validation."""

from __future__ import annotations

from app.integrations.powerbi.models import (
    DatasetMetadata,
    SemanticColumnMetadata,
    SemanticMeasureMetadata,
    SemanticTableMetadata,
)


def test_semantic_table_and_column_metadata_lookups() -> None:
    col_order_id = SemanticColumnMetadata(name="Order ID", data_type="string")
    col_amount = SemanticColumnMetadata(name="Amount", data_type="double")
    table_orders = SemanticTableMetadata(
        name="Orders",
        columns=[col_order_id, col_amount],
    )

    assert table_orders.column_names == ["Order ID", "Amount"]
    # Case-insensitive lookup
    assert table_orders.get_column("order id") is col_order_id
    assert table_orders.get_column("AMOUNT") is col_amount
    assert table_orders.get_column("NonExistent") is None


def test_dataset_metadata_table_and_measure_lookups() -> None:
    col_id = SemanticColumnMetadata(name="CustomerID")
    tbl_cust = SemanticTableMetadata(name="Customers", columns=[col_id])
    meas_sales = SemanticMeasureMetadata(name="Total Sales", table_name="Measures")

    meta = DatasetMetadata(
        dataset_id="11111111-2222-3333-4444-555555555555",
        workspace_id="me",
        tables=[tbl_cust],
        measures=[meas_sales],
        is_supported=True,
    )

    assert meta.table_names == ["Customers"]
    assert meta.measure_names == ["Total Sales"]
    assert meta.get_table("customers") is tbl_cust
    assert meta.get_table("Unknown") is None
    assert meta.get_column("customers", "customerid") is col_id
    assert meta.get_column("customers", "invalid") is None
    assert meta.get_column("unknown", "any") is None
    assert meta.get_measure("total sales") is meas_sales
    assert meta.get_measure("missing") is None


def test_validate_object_rules() -> None:
    tbl_orders = SemanticTableMetadata(
        name="Orders",
        columns=[SemanticColumnMetadata(name="Order ID"), SemanticColumnMetadata(name="Sales")],
    )
    meas_rev = SemanticMeasureMetadata(name="Total Revenue", table_name="Measures")

    meta = DatasetMetadata(
        dataset_id="ds-guid",
        workspace_id="me",
        tables=[tbl_orders],
        measures=[meas_rev],
        is_supported=True,
    )

    # 1. Model / Refresh checks never require table or column targets
    ok, msg = meta.validate_object("refresh", None, None)
    assert ok
    assert "Model-level" in msg

    ok, msg = meta.validate_object("model", "", "")
    assert ok

    # 2. Column checks validate table and column existence
    ok, msg = meta.validate_object("column", "Orders", "Order ID")
    assert ok
    assert "verified" in msg.lower()

    # Missing column
    ok, msg = meta.validate_object("column", "Orders", "NonExistentColumn")
    assert not ok
    assert "not found" in msg.lower()

    # Missing table
    ok, msg = meta.validate_object("column", "NoSuchTable", "Col")
    assert not ok
    assert "not found" in msg.lower()

    # Missing table name input
    ok, msg = meta.validate_object("column", "", "Col")
    assert not ok
    assert "Table name is required" in msg

    # Missing column name input
    ok, msg = meta.validate_object("column", "Orders", "")
    assert not ok
    assert "Column name is required" in msg

    # 3. DAX Measure checks validate measure existence
    ok, msg = meta.validate_object("measure", None, "Total Revenue")
    assert ok
    assert "verified" in msg.lower()

    ok, msg = meta.validate_object("measure", None, "Unknown Measure")
    assert not ok
    assert "not found" in msg.lower()

    ok, msg = meta.validate_object("measure", None, "")
    assert not ok
    assert "Measure name is required" in msg


def test_validate_object_allows_manual_entry_when_metadata_unsupported() -> None:
    meta = DatasetMetadata(
        dataset_id="ds-guid",
        workspace_id="me",
        tables=[],
        measures=[],
        is_supported=False,
        error_message="Execute Queries disabled on tenant.",
    )

    # When metadata is unsupported, object validation never falsely blocks user rules
    ok, msg = meta.validate_object("column", "AnyTable", "AnyColumn")
    assert ok
    assert "not supported" in msg.lower()

    ok, msg = meta.validate_object("measure", None, "AnyMeasure")
    assert ok
    assert "not supported" in msg.lower()
