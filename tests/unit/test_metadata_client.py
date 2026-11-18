"""Unit tests for Stage 6 MetadataClient discovering tables, columns, and measures."""

from __future__ import annotations

import httpx
import pytest

from app.integrations.powerbi.metadata_client import MetadataClient, is_system_measure, is_system_table
from app.integrations.powerbi.rest_client import PowerBIRestClient
from app.integrations.powerbi.workspace_client import MY_WORKSPACE_ID

DATASET_ID = "11111111-2222-3333-4444-555555555555"
WORKSPACE_ID = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"


def test_system_object_filters() -> None:
    assert is_system_table("DateTableTemplate_c974c596-1821-4c7d")
    assert is_system_table("LocalDateTable_3ff89f18-0066")
    assert is_system_table("$SYSTEM")
    assert not is_system_table("Orders")
    assert not is_system_table("Dim_Date")

    assert is_system_measure("__Default measure")
    assert is_system_measure("__Count of Orders")
    assert not is_system_measure("Total Sales")
    assert not is_system_measure("Profit Margin %")


def test_discover_metadata_via_execute_queries_success() -> None:
    calls: list[tuple[str, dict]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        body = request.read().decode("utf-8")
        calls.append((url, body))

        if "MDSCHEMA_HIERARCHIES" in body:
            payload = {
                "results": [
                    {
                        "tables": [
                            {
                                "rows": [
                                    # User tables and columns
                                    {
                                        "DIMENSION_UNIQUE_NAME": "[Orders]",
                                        "HIERARCHY_NAME": "OrderID",
                                        "HIERARCHY_CAPTION": "Order ID",
                                    },
                                    {
                                        "DIMENSION_UNIQUE_NAME": "[Orders]",
                                        "HIERARCHY_NAME": "Sales",
                                        "HIERARCHY_CAPTION": "Sales Amount",
                                    },
                                    {
                                        "DIMENSION_UNIQUE_NAME": "[Customers]",
                                        "HIERARCHY_NAME": "CustName",
                                        "HIERARCHY_CAPTION": "Customer Name",
                                    },
                                    # System date table should be filtered out
                                    {
                                        "DIMENSION_UNIQUE_NAME": "[DateTableTemplate_1234]",
                                        "HIERARCHY_NAME": "Year",
                                        "HIERARCHY_CAPTION": "Year",
                                    },
                                    {
                                        "DIMENSION_UNIQUE_NAME": "[LocalDateTable_5678]",
                                        "HIERARCHY_NAME": "Month",
                                        "HIERARCHY_CAPTION": "Month",
                                    },
                                ]
                            }
                        ]
                    }
                ]
            }
            return httpx.Response(200, json=payload)

        if "MDSCHEMA_MEASURES" in body:
            payload = {
                "results": [
                    {
                        "tables": [
                            {
                                "rows": [
                                    {
                                        "MEASURE_NAME": "Total Sales",
                                        "MEASUREGROUP_NAME": "Measures",
                                        "DESCRIPTION": "Sum of sales amount",
                                    },
                                    {
                                        "MEASURE_NAME": "Discount %",
                                        "MEASUREGROUP_NAME": "Orders",
                                        "DESCRIPTION": "",
                                    },
                                    # Internal measure should be filtered out
                                    {
                                        "MEASURE_NAME": "__Default measure",
                                        "MEASUREGROUP_NAME": "",
                                        "DESCRIPTION": "",
                                    },
                                ]
                            }
                        ]
                    }
                ]
            }
            return httpx.Response(200, json=payload)

        return httpx.Response(404, json={"error": {"code": "NotFound"}})

    transport = httpx.MockTransport(handler)
    rest = PowerBIRestClient(lambda: "fake-token", transport=transport)
    client = MetadataClient(rest)

    # Call with shared workspace GUID
    meta = client.discover_metadata(dataset_id=DATASET_ID, workspace_id=WORKSPACE_ID)

    assert meta.is_supported
    assert meta.source == "execute_queries"
    assert meta.dataset_id == DATASET_ID
    assert meta.workspace_id == WORKSPACE_ID

    # System date tables filtered; only Customers and Orders remain
    assert meta.table_names == ["Customers", "Orders"]
    tbl_orders = meta.get_table("Orders")
    assert tbl_orders is not None
    assert tbl_orders.column_names == ["Order ID", "Sales Amount"]

    # Measures returned and system measures filtered
    assert meta.measure_names == ["Discount %", "Total Sales"]
    m_sales = meta.get_measure("Total Sales")
    assert m_sales is not None
    assert m_sales.table_name == "Measures"
    assert m_sales.description == "Sum of sales amount"

    # Verify group endpoint was targeted
    assert f"/groups/{WORKSPACE_ID}/datasets/{DATASET_ID}/executeQueries" in calls[0][0]


def test_discover_metadata_my_workspace_uses_personal_endpoint() -> None:
    requested_urls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requested_urls.append(str(request.url))
        return httpx.Response(200, json={"results": [{"tables": [{"rows": []}]}]})

    transport = httpx.MockTransport(handler)
    rest = PowerBIRestClient(lambda: "fake-token", transport=transport)
    client = MetadataClient(rest)

    client.discover_metadata(dataset_id=DATASET_ID, workspace_id="me")
    assert f"/datasets/{DATASET_ID}/executeQueries" in requested_urls[0]
    assert "/groups/" not in requested_urls[0]


def test_discover_metadata_gracefully_handles_restricted_tenant_or_errors() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        # Simulate Execute Queries disabled by tenant admin (HTTP 403 / 400)
        return httpx.Response(
            403,
            json={"error": {"code": "PowerBINotAuthorizedException", "message": "Execute Queries is disabled."}},
        )

    transport = httpx.MockTransport(handler)
    rest = PowerBIRestClient(lambda: "fake-token", transport=transport)
    client = MetadataClient(rest)

    # Must never raise an exception!
    meta = client.discover_metadata(dataset_id=DATASET_ID, workspace_id="me")

    assert not meta.is_supported
    assert meta.source == "none"
    assert meta.tables == []
    assert meta.measures == []
    assert meta.error_message is not None
    assert "Manual table, column, and measure entry is enabled" in meta.error_message
