"""Power BI Semantic Model metadata discovery client (tables, columns, measures).

Queries Analysis Services Dynamic Management Views (DMVs) via the Power BI
Dataset Execute Queries REST API, filtering internal system tables and measures,
with robust graceful fallbacks for unsupported datasets or restricted tenants.
"""

from __future__ import annotations

import logging
from typing import Any

from app.core.exceptions import format_safe_user_error
from app.integrations.powerbi.models import (
    DatasetMetadata,
    SemanticColumnMetadata,
    SemanticMeasureMetadata,
    SemanticTableMetadata,
)
from app.integrations.powerbi.rest_client import PowerBIHttpError, PowerBIRestClient
from app.integrations.powerbi.workspace_client import MY_WORKSPACE_ID

logger = logging.getLogger(__name__)

# DMVs queried via the Power BI Execute Queries API (one query per HTTP request)
DMV_HIERARCHIES_QUERY = (
    "SELECT [HIERARCHY_NAME], [DIMENSION_UNIQUE_NAME], [HIERARCHY_CAPTION] "
    "FROM $SYSTEM.MDSCHEMA_HIERARCHIES"
)
DMV_MEASURES_QUERY = (
    "SELECT [MEASURE_NAME], [MEASUREGROUP_NAME], [MEASURE_CAPTION], [DESCRIPTION] "
    "FROM $SYSTEM.MDSCHEMA_MEASURES"
)

# Power BI auto-generated date and system table prefixes to filter from user selections
SYSTEM_TABLE_PREFIXES: tuple[str, ...] = (
    "datetabletemplate",
    "localdatetable",
    "$",
)


def is_system_table(name: str) -> bool:
    """Return True if the table is an auto-generated Power BI date or system table."""
    lowered = name.strip().lower()
    return any(lowered.startswith(prefix) for prefix in SYSTEM_TABLE_PREFIXES)


def is_system_measure(name: str) -> bool:
    """Return True if the measure is an internal system measure."""
    return name.strip().startswith("__")


class MetadataClient:
    """Discovers tables, columns, and DAX measures from a Power BI semantic model."""

    def __init__(self, rest_client: PowerBIRestClient) -> None:
        self._rest = rest_client

    def discover_metadata(
        self,
        dataset_id: str,
        workspace_id: str = MY_WORKSPACE_ID,
    ) -> DatasetMetadata:
        """Query semantic model metadata via Execute Queries or REST API fallback.

        Never raises exceptions; if metadata access is unsupported or forbidden,
        returns DatasetMetadata with is_supported=False and a friendly error message,
        enabling manual entry fallback.
        """
        clean_ds = dataset_id.strip()
        clean_ws = workspace_id.strip() or MY_WORKSPACE_ID

        # Try Execute Queries DMV inspection first (standard on Power BI Service)
        try:
            return self._discover_via_execute_queries(clean_ds, clean_ws)
        except Exception as exc:
            logger.info(
                "Execute Queries metadata discovery unavailable for dataset %s in workspace %s: %s",
                clean_ds,
                clean_ws,
                exc,
            )

        # Secondary fallback: try REST API tables endpoint (supported for push/streaming models)
        try:
            return self._discover_via_rest_tables(clean_ds, clean_ws)
        except Exception as exc:
            logger.debug(
                "REST tables fallback also unavailable for dataset %s: %s",
                clean_ds,
                exc,
            )

        user_msg = (
            "Semantic model metadata discovery is not supported for this dataset "
            "(Execute Queries may be disabled on this tenant or capacity, or your account "
            "has Build-restricted permissions). Manual table, column, and measure entry is enabled."
        )
        return DatasetMetadata(
            dataset_id=clean_ds,
            workspace_id=clean_ws,
            tables=[],
            measures=[],
            is_supported=False,
            source="none",
            error_message=user_msg,
        )

    def _execute_queries_path(self, dataset_id: str, workspace_id: str) -> str:
        if workspace_id.lower() == MY_WORKSPACE_ID:
            return f"/datasets/{dataset_id}/executeQueries"
        return f"/groups/{workspace_id}/datasets/{dataset_id}/executeQueries"

    def _discover_via_execute_queries(
        self,
        dataset_id: str,
        workspace_id: str,
    ) -> DatasetMetadata:
        path = self._execute_queries_path(dataset_id, workspace_id)

        # 1. Query table and column hierarchies
        hier_body = {
            "queries": [{"query": DMV_HIERARCHIES_QUERY}],
            "serializerSettings": {"includeNulls": True},
        }
        hier_resp = self._rest.post_json(path, json_body=hier_body)
        tables_dict: dict[str, list[SemanticColumnMetadata]] = {}

        results = hier_resp.get("results") or []
        if results and isinstance(results, list):
            tables_list = results[0].get("tables") or []
            if tables_list and isinstance(tables_list, list):
                rows = tables_list[0].get("rows") or []
                for row in rows:
                    if not isinstance(row, dict):
                        continue
                    dim_raw = str(row.get("DIMENSION_UNIQUE_NAME") or "").strip()
                    dim_clean = dim_raw.strip("[]")
                    col_name = str(row.get("HIERARCHY_CAPTION") or row.get("HIERARCHY_NAME") or "").strip()

                    if not dim_clean or is_system_table(dim_clean):
                        continue
                    if not col_name or is_system_measure(col_name):
                        continue

                    cols = tables_dict.setdefault(dim_clean, [])
                    if not any(c.name.lower() == col_name.lower() for c in cols):
                        cols.append(SemanticColumnMetadata(name=col_name))

        # 2. Query DAX measures
        meas_body = {
            "queries": [{"query": DMV_MEASURES_QUERY}],
            "serializerSettings": {"includeNulls": True},
        }
        measures: list[SemanticMeasureMetadata] = []
        try:
            meas_resp = self._rest.post_json(path, json_body=meas_body)
            meas_results = meas_resp.get("results") or []
            if meas_results and isinstance(meas_results, list):
                m_tables = meas_results[0].get("tables") or []
                if m_tables and isinstance(m_tables, list):
                    m_rows = m_tables[0].get("rows") or []
                    for mrow in m_rows:
                        if not isinstance(mrow, dict):
                            continue
                        m_name = str(mrow.get("MEASURE_NAME") or mrow.get("MEASURE_CAPTION") or "").strip()
                        if not m_name or is_system_measure(m_name):
                            continue
                        grp = str(mrow.get("MEASUREGROUP_NAME") or "").strip()
                        desc = str(mrow.get("DESCRIPTION") or "").strip()
                        measures.append(
                            SemanticMeasureMetadata(
                                name=m_name,
                                table_name=grp if grp and not is_system_table(grp) else None,
                                description=desc,
                            )
                        )
        except Exception as meas_exc:
            logger.debug("Failed querying measures on %s (continuing with tables): %s", path, meas_exc)

        # Assemble SemanticTableMetadata objects sorted alphabetically
        tables: list[SemanticTableMetadata] = []
        for tbl_name in sorted(tables_dict.keys(), key=str.lower):
            sorted_cols = sorted(tables_dict[tbl_name], key=lambda c: c.name.lower())
            tables.append(SemanticTableMetadata(name=tbl_name, columns=sorted_cols))

        sorted_measures = sorted(measures, key=lambda m: m.name.lower())

        if not tables and not sorted_measures:
            # If queries returned 200 but 0 user objects, check if it was empty or unsupported
            logger.info("Execute Queries returned no user tables or measures for dataset %s", dataset_id)

        return DatasetMetadata(
            dataset_id=dataset_id,
            workspace_id=workspace_id,
            tables=tables,
            measures=sorted_measures,
            is_supported=True,
            source="execute_queries",
        )

    def _discover_via_rest_tables(
        self,
        dataset_id: str,
        workspace_id: str,
    ) -> DatasetMetadata:
        """Fallback querying GET /datasets/{id}/tables for push/streaming datasets."""
        if workspace_id.lower() == MY_WORKSPACE_ID:
            path = f"/datasets/{dataset_id}/tables"
        else:
            path = f"/groups/{workspace_id}/datasets/{dataset_id}/tables"

        resp = self._rest.get_json(path)
        raw_tables = resp.get("value") or []
        tables: list[SemanticTableMetadata] = []

        for tbl in raw_tables:
            if not isinstance(tbl, dict):
                continue
            name = str(tbl.get("name") or "").strip()
            if not name or is_system_table(name):
                continue
            cols: list[SemanticColumnMetadata] = []
            for col in tbl.get("columns") or []:
                if isinstance(col, dict):
                    c_name = str(col.get("name") or "").strip()
                    c_type = str(col.get("dataType") or "").strip() or None
                    if c_name:
                        cols.append(SemanticColumnMetadata(name=c_name, data_type=c_type))
            tables.append(SemanticTableMetadata(name=name, columns=cols))

        return DatasetMetadata(
            dataset_id=dataset_id,
            workspace_id=workspace_id,
            tables=tables,
            measures=[],
            is_supported=bool(tables),
            source="rest_api",
        )
