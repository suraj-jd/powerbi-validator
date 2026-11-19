"""Unit tests for Stage 9 DAX query execution foundation."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from app.integrations.powerbi.dax_client import (
    DaxQueryClient,
    DaxQueryResult,
    RestExecuteQueriesConnector,
    XmlaAdomdConnector,
    build_measure_query,
    build_test_query,
    escape_column_reference,
    escape_measure_name,
    escape_table_name,
)
from app.integrations.powerbi.rest_client import PowerBIHttpError
from app.services.dax_service import DaxQueryService

WS_ID = "11111111-2222-3333-4444-555555555555"
DS_ID = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"


def test_safe_dax_identifiers_and_queries() -> None:
    # 1. Measure escaping
    assert escape_measure_name("Total Sales") == "[Total Sales]"
    assert escape_measure_name("[Total Sales]") == "[Total Sales]"
    assert escape_measure_name("  Margin %  ") == "[Margin %]"
    with pytest.raises(ValueError):
        escape_measure_name("")

    # 2. Table escaping
    assert escape_table_name("Sales") == "'Sales'"
    assert escape_table_name("'Sales'") == "'Sales'"
    assert escape_table_name("Customer Orders") == "'Customer Orders'"
    assert escape_table_name("O'Connor") == "'O''Connor'"
    with pytest.raises(ValueError):
        escape_table_name("")

    # 3. Column reference
    assert escape_column_reference("Amount", "Sales") == "'Sales'[Amount]"
    assert escape_column_reference("Amount") == "[Amount]"

    # 4. Measure query construction
    q_simple = build_measure_query("Total Revenue")
    assert q_simple == 'EVALUATE ROW("Value", [Total Revenue])'

    q_filtered = build_measure_query("Total Revenue", "Dates[Year] = 2024")
    assert q_filtered == 'EVALUATE ROW("Value", CALCULATE([Total Revenue], Dates[Year] = 2024))'

    # 5. Minimal test probe query
    assert build_test_query() == 'EVALUATE ROW("TestValue", 1)'


def test_dax_result_parser_distinguishes_blank_from_zero() -> None:
    mock_rest = MagicMock()
    connector = RestExecuteQueriesConnector(mock_rest)

    # 1. Numeric Zero Result: 0 MUST NOT BE BLANK
    mock_resp_zero = MagicMock()
    mock_resp_zero.json.return_value = {
        "results": [
            {
                "tables": [
                    {
                        "rows": [{"[Value]": 0}]
                    }
                ]
            }
        ]
    }
    mock_rest.post.return_value = mock_resp_zero

    res_zero = connector.execute_query(WS_ID, DS_ID, 'EVALUATE ROW("Value", [Balance])')
    assert res_zero.is_success is True
    assert res_zero.is_blank is False
    assert res_zero.scalar_value == 0
    assert res_zero.value_type == "numeric"
    assert res_zero.display_value == "0"

    # 2. BLANK Result (null returned from Analysis Services)
    mock_resp_blank = MagicMock()
    mock_resp_blank.json.return_value = {
        "results": [
            {
                "tables": [
                    {
                        "rows": [{"[Value]": None}]
                    }
                ]
            }
        ]
    }
    mock_rest.post.return_value = mock_resp_blank

    res_blank = connector.execute_query(WS_ID, DS_ID, 'EVALUATE ROW("Value", [NonExistent])')
    assert res_blank.is_success is True
    assert res_blank.is_blank is True
    assert res_blank.scalar_value is None
    assert res_blank.value_type == "blank"
    assert res_blank.display_value == "BLANK()"


def test_dax_result_parser_handles_numeric_text_boolean() -> None:
    mock_rest = MagicMock()
    connector = RestExecuteQueriesConnector(mock_rest)

    # Floating point number
    mock_resp_float = MagicMock()
    mock_resp_float.json.return_value = {
        "results": [{"tables": [{"rows": [{"[Value]": 1234567.89}]}]}]
    }
    mock_rest.post.return_value = mock_resp_float
    res_float = connector.execute_query(WS_ID, DS_ID, "EVALUATE ...")
    assert res_float.is_success is True
    assert res_float.scalar_value == 1234567.89
    assert res_float.value_type == "numeric"
    assert res_float.display_value == "1,234,567.89"

    # Boolean result
    mock_resp_bool = MagicMock()
    mock_resp_bool.json.return_value = {
        "results": [{"tables": [{"rows": [{"[Value]": True}]}]}]
    }
    mock_rest.post.return_value = mock_resp_bool
    res_bool = connector.execute_query(WS_ID, DS_ID, "EVALUATE ...")
    assert res_bool.is_success is True
    assert res_bool.scalar_value is True
    assert res_bool.value_type == "boolean"
    assert res_bool.display_value == "TRUE"

    # Text string result
    mock_resp_text = MagicMock()
    mock_resp_text.json.return_value = {
        "results": [{"tables": [{"rows": [{"[Value]": "Active Status"}]}]}]
    }
    mock_rest.post.return_value = mock_resp_text
    res_text = connector.execute_query(WS_ID, DS_ID, "EVALUATE ...")
    assert res_text.is_success is True
    assert res_text.scalar_value == "Active Status"
    assert res_text.value_type == "text"
    assert res_text.display_value == "Active Status"


def test_dax_query_error_handling() -> None:
    mock_rest = MagicMock()
    connector = RestExecuteQueriesConnector(mock_rest)

    # 1. Semantic DAX query syntax error inside results
    mock_resp_err = MagicMock()
    mock_resp_err.json.return_value = {
        "results": [
            {
                "error": {
                    "code": "SemanticError",
                    "message": "The measure 'MissingMeasure' is not defined in the semantic model.",
                }
            }
        ]
    }
    mock_rest.post.return_value = mock_resp_err
    res_err = connector.execute_query(WS_ID, DS_ID, 'EVALUATE ROW("Value", [MissingMeasure])')
    assert res_err.is_success is False
    assert res_err.value_type == "error"
    assert "MissingMeasure" in (res_err.error_message or "")
    assert res_err.error_code == "SemanticError"

    # 2. HTTP 403 Forbidden (e.g. Execute Queries disabled on tenant)
    mock_rest.post.side_effect = PowerBIHttpError(
        "Forbidden: Dataset Execute Queries API is disabled for this tenant.",
        status_code=403,
        error_code="Forbidden",
    )
    res_forbidden = connector.execute_query(WS_ID, DS_ID, "EVALUATE ...")
    assert res_forbidden.is_success is False
    assert res_forbidden.error_code == "HTTP_403"
    assert "Forbidden" in (res_forbidden.error_message or "")


def test_dax_query_client_my_workspace_and_endpoints() -> None:
    mock_rest = MagicMock()
    mock_resp = MagicMock()
    mock_resp.json.return_value = {
        "results": [{"tables": [{"rows": [{"[TestValue]": 1}]}]}]
    }
    mock_rest.post.return_value = mock_resp

    client = DaxQueryClient(rest_client=mock_rest)

    # Group workspace call
    res_ws = client.test_connection(WS_ID, DS_ID)
    assert res_ws.is_success is True
    mock_rest.post.assert_called_with(
        f"/groups/{WS_ID}/datasets/{DS_ID}/executeQueries",
        json={"queries": [{"query": 'EVALUATE ROW("TestValue", 1)'}], "serializerSettings": {"includeNulls": True}},
        timeout=30,
    )

    # My Workspace (id="me") call
    client.test_connection("me", DS_ID)
    mock_rest.post.assert_called_with(
        f"/datasets/{DS_ID}/executeQueries",
        json={"queries": [{"query": 'EVALUATE ROW("TestValue", 1)'}], "serializerSettings": {"includeNulls": True}},
        timeout=30,
    )


def test_xmla_adomd_connector_stub() -> None:
    xmla = XmlaAdomdConnector()
    res = xmla.execute_query(WS_ID, DS_ID, "EVALUATE ...")
    assert res.is_success is False
    assert res.error_code == "XMLA_NOT_CONFIGURED"
