"""Power BI DAX Query Execution Client and Result Parser (Stage 9).

Executes DAX queries against semantic models using the Power BI Execute Queries REST API,
with extensible connector architecture for XMLA/ADOMD.NET endpoints.
"""

from __future__ import annotations

import logging
import re
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

from app.integrations.powerbi.rest_client import PowerBIHttpError, PowerBIRestClient
from app.integrations.powerbi.workspace_client import MY_WORKSPACE_ID

logger = logging.getLogger(__name__)


def escape_measure_name(name: str) -> str:
    """Safely format a measure name into standard bracketed DAX identifier syntax [Measure]."""
    clean = name.strip()
    if not clean:
        raise ValueError("Measure name cannot be empty.")
    if clean.startswith("[") and clean.endswith("]"):
        clean = clean[1:-1].strip()
    # Replace internal closing brackets to avoid syntax escapes
    clean = clean.replace("]", "")
    return f"[{clean}]"


def escape_table_name(name: str) -> str:
    """Safely format a table name into standard single-quoted DAX identifier syntax 'Table'."""
    clean = name.strip()
    if not clean:
        raise ValueError("Table name cannot be empty.")
    if clean.startswith("'") and clean.endswith("'"):
        clean = clean[1:-1].strip()
    clean = clean.replace("'", "''")
    return f"'{clean}'"


def escape_column_reference(column_name: str, table_name: str | None = None) -> str:
    """Safely format a column reference into 'Table'[Column] or [Column]."""
    col = escape_measure_name(column_name)
    if table_name and table_name.strip():
        tbl = escape_table_name(table_name)
        return f"{tbl}{col}"
    return col


def build_measure_query(measure_name: str, filter_context: str | None = None) -> str:
    """Construct a safe DAX query returning a single measure value in a tabular row.

    Example without filter:
        EVALUATE ROW("Value", [Total Sales])

    Example with filter:
        EVALUATE ROW("Value", CALCULATE([Total Sales], Dates[Year] = 2024))
    """
    escaped_measure = escape_measure_name(measure_name)
    if filter_context and filter_context.strip():
        clean_filter = filter_context.strip()
        return f'EVALUATE ROW("Value", CALCULATE({escaped_measure}, {clean_filter}))'
    return f'EVALUATE ROW("Value", {escaped_measure})'


def build_test_query() -> str:
    """Construct a minimal, fast DAX probe query to confirm Execute Queries eligibility."""
    return 'EVALUATE ROW("TestValue", 1)'


@dataclass(frozen=True, slots=True)
class DaxQueryResult:
    """Detached immutable representation of the parsed output from a DAX query execution."""

    is_success: bool
    scalar_value: Any
    is_blank: bool
    value_type: str  # "numeric", "text", "boolean", "datetime", "blank", "empty", "error"
    raw_rows: list[dict[str, Any]]
    error_message: str | None
    error_code: str | None
    duration_ms: int
    query: str

    @property
    def display_value(self) -> str:
        """Formatted string representation explicitly distinguishing BLANK() from 0."""
        if not self.is_success:
            return f"Error: {self.error_message or 'Unknown query error'}"
        if self.is_blank:
            return "BLANK()"
        if self.scalar_value is None:
            return "BLANK()"
        if isinstance(self.scalar_value, bool):
            return "TRUE" if self.scalar_value else "FALSE"
        if isinstance(self.scalar_value, float):
            # Trim trailing zero decimals if integer value
            if self.scalar_value.is_integer():
                return f"{int(self.scalar_value):,}"
            return f"{self.scalar_value:,.4f}".rstrip("0").rstrip(".")
        if isinstance(self.scalar_value, int):
            return f"{self.scalar_value:,}"
        return str(self.scalar_value)

    @classmethod
    def from_raw_rows(
        cls,
        rows: list[dict[str, Any]],
        *,
        query: str = "",
        duration_ms: int = 0,
    ) -> DaxQueryResult:
        scalar = None
        is_blank = True
        val_type = "empty"
        if rows:
            first_row = rows[0]
            if first_row:
                scalar = next(iter(first_row.values()))
                is_blank = scalar is None
                val_type = "numeric" if isinstance(scalar, (int, float)) and not isinstance(scalar, bool) else "text"
        return cls(
            is_success=True,
            scalar_value=scalar,
            is_blank=is_blank,
            value_type=val_type,
            raw_rows=rows,
            error_message=None,
            error_code=None,
            duration_ms=duration_ms,
            query=query,
        )

    @classmethod
    def from_error(
        cls,
        error_message: str,
        *,
        error_code: str = "ERROR",
        query: str = "",
        duration_ms: int = 0,
    ) -> DaxQueryResult:
        return cls(
            is_success=False,
            scalar_value=None,
            is_blank=False,
            value_type="error",
            raw_rows=[],
            error_message=error_message,
            error_code=error_code,
            duration_ms=duration_ms,
            query=query,
        )


class DaxConnectorInterface(ABC):
    """Abstract connector interface for querying Power BI semantic models."""

    @abstractmethod
    def execute_query(
        self,
        workspace_id: str,
        dataset_id: str,
        query: str,
        timeout_seconds: int = 30,
    ) -> DaxQueryResult:
        """Execute a DAX query and return parsed results."""
        raise NotImplementedError


class RestExecuteQueriesConnector(DaxConnectorInterface):
    """Executes DAX queries via the official Power BI Dataset Execute Queries REST API."""

    def __init__(self, rest_client: PowerBIRestClient) -> None:
        self._rest = rest_client

    def _execute_queries_endpoint(self, workspace_id: str, dataset_id: str) -> str:
        clean_ws = workspace_id.strip()
        clean_ds = dataset_id.strip()
        if clean_ws.lower() == MY_WORKSPACE_ID:
            return f"/datasets/{clean_ds}/executeQueries"
        return f"/groups/{clean_ws}/datasets/{clean_ds}/executeQueries"

    def execute_query(
        self,
        workspace_id: str,
        dataset_id: str,
        query: str,
        timeout_seconds: int = 30,
    ) -> DaxQueryResult:
        endpoint = self._execute_queries_endpoint(workspace_id, dataset_id)
        payload = {
            "queries": [{"query": query}],
            "serializerSettings": {"includeNulls": True},
        }

        t_start = time.perf_counter()
        try:
            resp = self._rest.post(endpoint, json=payload, timeout=timeout_seconds)
            duration_ms = int((time.perf_counter() - t_start) * 1000)
            data = resp.json()
            return self._parse_api_response(data, duration_ms, query)
        except PowerBIHttpError as exc:
            duration_ms = int((time.perf_counter() - t_start) * 1000)
            logger.error("Execute Queries HTTP error for dataset %s: %s", dataset_id, exc)
            return DaxQueryResult(
                is_success=False,
                scalar_value=None,
                is_blank=False,
                value_type="error",
                raw_rows=[],
                error_message=exc.user_message or str(exc),
                error_code=f"HTTP_{exc.status_code}",
                duration_ms=duration_ms,
                query=query,
            )
        except Exception as exc:
            duration_ms = int((time.perf_counter() - t_start) * 1000)
            logger.error("Execute Queries unexpected error for dataset %s: %s", dataset_id, exc, exc_info=True)
            return DaxQueryResult(
                is_success=False,
                scalar_value=None,
                is_blank=False,
                value_type="error",
                raw_rows=[],
                error_message=str(exc),
                error_code="QUERY_FAILED",
                duration_ms=duration_ms,
                query=query,
            )

    def _parse_api_response(
        self,
        data: dict[str, Any],
        duration_ms: int,
        query: str,
    ) -> DaxQueryResult:
        # Check top-level error
        if "error" in data:
            err = data["error"]
            msg = err.get("message") or "Execute Queries error reported by Power BI."
            code = err.get("code") or "API_ERROR"
            return DaxQueryResult(
                is_success=False,
                scalar_value=None,
                is_blank=False,
                value_type="error",
                raw_rows=[],
                error_message=msg,
                error_code=code,
                duration_ms=duration_ms,
                query=query,
            )

        results = data.get("results") or []
        if not results:
            return DaxQueryResult(
                is_success=True,
                scalar_value=None,
                is_blank=True,
                value_type="empty",
                raw_rows=[],
                error_message=None,
                error_code=None,
                duration_ms=duration_ms,
                query=query,
            )

        first_res = results[0]
        # Check query-level error
        if "error" in first_res:
            err = first_res["error"]
            msg = err.get("message") or "Query syntax or execution error in DAX expression."
            code = err.get("code") or "DAX_ERROR"
            return DaxQueryResult(
                is_success=False,
                scalar_value=None,
                is_blank=False,
                value_type="error",
                raw_rows=[],
                error_message=msg,
                error_code=code,
                duration_ms=duration_ms,
                query=query,
            )

        tables = first_res.get("tables") or []
        if not tables:
            return DaxQueryResult(
                is_success=True,
                scalar_value=None,
                is_blank=True,
                value_type="empty",
                raw_rows=[],
                error_message=None,
                error_code=None,
                duration_ms=duration_ms,
                query=query,
            )

        rows: list[dict[str, Any]] = tables[0].get("rows") or []
        if not rows:
            return DaxQueryResult(
                is_success=True,
                scalar_value=None,
                is_blank=True,
                value_type="empty",
                raw_rows=[],
                error_message=None,
                error_code=None,
                duration_ms=duration_ms,
                query=query,
            )

        first_row = rows[0]
        # In ROW("Value", ...), first key is usually "[Value]" or "[TestValue]"
        raw_val = next(iter(first_row.values())) if first_row else None

        # Critical acceptance requirement: BLANK must be distinguished from zero
        if raw_val is None:
            return DaxQueryResult(
                is_success=True,
                scalar_value=None,
                is_blank=True,
                value_type="blank",
                raw_rows=rows,
                error_message=None,
                error_code=None,
                duration_ms=duration_ms,
                query=query,
            )

        # Detect value type
        if isinstance(raw_val, bool):
            val_type = "boolean"
        elif isinstance(raw_val, (int, float)):
            val_type = "numeric"
        elif isinstance(raw_val, str):
            val_type = "text"
        else:
            val_type = "other"

        return DaxQueryResult(
            is_success=True,
            scalar_value=raw_val,
            is_blank=False,
            value_type=val_type,
            raw_rows=rows,
            error_message=None,
            error_code=None,
            duration_ms=duration_ms,
            query=query,
        )


class XmlaAdomdConnector(DaxConnectorInterface):
    """Stub/Interface for XMLA endpoint query connector (Premium / Fabric capacities)."""

    def __init__(self, connection_string: str = "") -> None:
        self._connection_string = connection_string

    def execute_query(
        self,
        workspace_id: str,
        dataset_id: str,
        query: str,
        timeout_seconds: int = 30,
    ) -> DaxQueryResult:
        return DaxQueryResult(
            is_success=False,
            scalar_value=None,
            is_blank=False,
            value_type="error",
            raw_rows=[],
            error_message="XMLA / ADOMD.NET endpoint is not configured for this tenant.",
            error_code="XMLA_NOT_CONFIGURED",
            duration_ms=0,
            query=query,
        )


class DaxQueryClient:
    """Primary client coordinating DAX measure and semantic query evaluations."""

    def __init__(
        self,
        connector: DaxConnectorInterface | None = None,
        *,
        rest_client: PowerBIRestClient | None = None,
    ) -> None:
        if connector is not None:
            self._connector = connector
        elif rest_client is not None:
            self._connector = RestExecuteQueriesConnector(rest_client)
        else:
            raise ValueError("Either connector or rest_client must be provided to DaxQueryClient.")

    def test_connection(self, workspace_id: str, dataset_id: str) -> DaxQueryResult:
        """Execute a minimal test probe to verify Execute Queries eligibility and permissions."""
        query = build_test_query()
        return self._connector.execute_query(workspace_id, dataset_id, query)

    def query_measure(
        self,
        workspace_id: str,
        dataset_id: str,
        measure_name: str,
        filter_context: str | None = None,
        timeout_seconds: int = 30,
    ) -> DaxQueryResult:
        """Execute a DAX query for a selected measure, preserving BLANK distinction."""
        query = build_measure_query(measure_name, filter_context)
        return self._connector.execute_query(
            workspace_id=workspace_id,
            dataset_id=dataset_id,
            query=query,
            timeout_seconds=timeout_seconds,
        )

    def execute_raw_dax(
        self,
        workspace_id: str,
        dataset_id: str,
        query: str,
        timeout_seconds: int = 30,
    ) -> DaxQueryResult:
        """Execute a custom DAX expression."""
        return self._connector.execute_query(
            workspace_id=workspace_id,
            dataset_id=dataset_id,
            query=query,
            timeout_seconds=timeout_seconds,
        )
