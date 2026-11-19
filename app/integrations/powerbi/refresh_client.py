"""Power BI dataset refresh history REST client and timestamp/status parser."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any

from app.core.status import RefreshStatus
from app.integrations.powerbi.models import ParsedRefreshRecord, PowerBIRefreshItem
from app.integrations.powerbi.rest_client import PowerBIHttpError, PowerBIRestClient
from app.integrations.powerbi.workspace_client import (
    MY_WORKSPACE_ID,
    _require_guid,
    _require_workspace_id,
)

logger = logging.getLogger(__name__)


def parse_iso_datetime(value: str | None) -> datetime | None:
    """Parse ISO-8601 timestamp string from Power BI API into UTC datetime."""
    if not value or not value.strip():
        return None

    cleaned = value.strip()
    if cleaned.endswith("Z"):
        cleaned = cleaned[:-1] + "+00:00"

    try:
        dt = datetime.fromisoformat(cleaned)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception as exc:
        logger.debug("Failed parsing datetime '%s': %s", value, exc)
        return None


def map_api_refresh_status(status_str: str | None, end_time: datetime | None) -> RefreshStatus:
    """Map raw Power BI API refresh status to canonical RefreshStatus enum (BRD Section 7).

    Power BI API status values include:
    - 'Completed' -> RefreshStatus.SUCCESS
    - 'Failed' -> RefreshStatus.FAILED
    - 'InProgress', 'NotStarted', or status without end_time -> RefreshStatus.IN_PROGRESS
    - 'Disabled', 'Unknown', or other -> RefreshStatus.UNKNOWN
    """
    if not status_str or not status_str.strip():
        return RefreshStatus.IN_PROGRESS if end_time is None else RefreshStatus.UNKNOWN

    normalized = status_str.strip().lower()

    if normalized in ("completed", "success", "succeeded"):
        return RefreshStatus.SUCCESS
    if normalized in ("failed", "failure", "cancelled"):
        return RefreshStatus.FAILED
    if normalized in ("inprogress", "in_progress", "in progress", "notstarted", "not_started"):
        return RefreshStatus.IN_PROGRESS

    # If the API reports 'Unknown' but the refresh has no end_time, it is actively in progress
    if end_time is None:
        return RefreshStatus.IN_PROGRESS

    return RefreshStatus.UNKNOWN


def calculate_refresh_duration(
    start_time: datetime | None,
    end_time: datetime | None,
) -> int | None:
    """Calculate duration in milliseconds from start and end timestamps.

    In-progress refreshes (end_time is None) return None to avoid displaying
    a false completed duration (BRD Stage 8 Acceptance Criteria).
    """
    if start_time is None or end_time is None:
        return None

    diff_seconds = (end_time - start_time).total_seconds()
    if diff_seconds < 0:
        return 0
    return int(diff_seconds * 1000)


def parse_service_exception_json(raw_json: str | None) -> str | None:
    """Extract a human-readable failure reason from Power BI's serviceExceptionJson."""
    if not raw_json or not raw_json.strip():
        return None

    try:
        data = json.loads(raw_json)
        if not isinstance(data, dict):
            return raw_json[:300]

        # Check standard Power BI error structure: {"error": {"code": "...", "pbi.error": {...}}}
        err_obj = data.get("error") or data
        if isinstance(err_obj, dict):
            pbi_err = err_obj.get("pbi.error") or {}
            if isinstance(pbi_err, dict) and pbi_err.get("details"):
                details = pbi_err.get("details")
                if isinstance(details, list) and details:
                    first = details[0]
                    if isinstance(first, dict) and first.get("detail"):
                        return str(first["detail"]["value"] if isinstance(first["detail"], dict) else first["detail"])
            if err_obj.get("message"):
                return str(err_obj["message"])
            if err_obj.get("code"):
                return f"Error Code: {err_obj['code']}"

        return raw_json[:300]
    except Exception:
        return raw_json[:300]


class RefreshClient:
    """Queries Power BI REST API for dataset refresh history (BRD Section 7, 12.6)."""

    def __init__(self, rest_client: PowerBIRestClient) -> None:
        self._rest = rest_client

    def list_refreshes(
        self,
        workspace_id: str,
        dataset_id: str,
        top: int = 10,
    ) -> list[ParsedRefreshRecord]:
        """Retrieve recent dataset refresh execution history.

        GET /groups/{groupId}/datasets/{datasetId}/refreshes?$top={top}
        or GET /datasets/{datasetId}/refreshes?$top={top} for personal workspace.
        """
        ws_id = _require_workspace_id(workspace_id)
        ds_guid = _require_guid(dataset_id, "Dataset ID")

        path = (
            f"/datasets/{ds_guid}/refreshes?$top={top}"
            if ws_id == MY_WORKSPACE_ID
            else f"/groups/{ws_id}/datasets/{ds_guid}/refreshes?$top={top}"
        )

        try:
            payload = self._rest.get_json(path)
        except PowerBIHttpError as exc:
            if exc.status_code == 404:
                logger.debug("Dataset %s or refreshes not found (404).", ds_guid)
                return []
            raise

        items = payload.get("value") or []
        records: list[ParsedRefreshRecord] = []

        for raw in items:
            try:
                item = PowerBIRefreshItem.model_validate(raw)
                start_dt = parse_iso_datetime(item.start_time)
                end_dt = parse_iso_datetime(item.end_time)
                status = map_api_refresh_status(item.status, end_dt)
                duration_ms = calculate_refresh_duration(start_dt, end_dt)
                err_msg = parse_service_exception_json(item.service_exception_json)
                ref_id_str = str(item.id) if item.id is not None else None

                records.append(
                    ParsedRefreshRecord(
                        refresh_id=ref_id_str,
                        status=status,
                        start_time=start_dt,
                        end_time=end_dt,
                        duration_ms=duration_ms,
                        refresh_type=item.refresh_type,
                        error_details=err_msg,
                        raw_status=item.status or "",
                    )
                )
            except Exception as exc:
                logger.warning("Failed parsing refresh history item %s: %s", raw, exc)

        return records
