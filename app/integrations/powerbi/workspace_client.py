"""Power BI workspace and report metadata client."""

from __future__ import annotations

import logging

from app.auth.msal_auth import is_valid_guid
from app.core.exceptions import PowerBIApiError
from app.integrations.powerbi.models import (
    PowerBIReport,
    PowerBIWorkspace,
    PowerBIWorkspaceUser,
)
from app.integrations.powerbi.rest_client import PowerBIHttpError, PowerBIRestClient

logger = logging.getLogger(__name__)


def _require_guid(value: str, label: str) -> str:
    cleaned = value.strip()
    if not is_valid_guid(cleaned):
        raise PowerBIApiError(
            f"Invalid {label} GUID: {cleaned!r}",
            user_message=f"{label} must be a valid GUID (xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx).",
        )
    return cleaned.lower()


class WorkspaceClient:
    """Queries accessible Power BI workspaces, roles, and reports for the signed-in user."""

    def __init__(self, rest_client: PowerBIRestClient) -> None:
        self._rest = rest_client

    def list_workspaces(self) -> list[PowerBIWorkspace]:
        """Return all Power BI workspaces accessible to the signed-in user (`GET /groups`)."""
        payload = self._rest.get_json("/groups")
        items = payload.get("value") or []
        return [PowerBIWorkspace.model_validate(item) for item in items]

    def get_workspace(self, workspace_id: str) -> PowerBIWorkspace | None:
        """Retrieve a specific workspace by GUID if accessible to the signed-in user."""
        guid = _require_guid(workspace_id, "Workspace ID")
        payload = self._rest.get_json("/groups", params={"$filter": f"id eq '{guid}'"})
        items = payload.get("value") or []
        for item in items:
            ws = PowerBIWorkspace.model_validate(item)
            if ws.id.lower() == guid:
                return ws
        return None

    def get_workspace_users(self, workspace_id: str) -> list[PowerBIWorkspaceUser] | None:
        """Return workspace user role assignments when permitted by the API.

        Returns `None` when the API denies listing workspace members (HTTP 403/401),
        since non-admin members/contributors/viewers may not have permission to enumerate users.
        """
        guid = _require_guid(workspace_id, "Workspace ID")
        try:
            payload = self._rest.get_json(f"/groups/{guid}/users")
        except PowerBIHttpError as exc:
            if exc.status_code in (401, 403, 404):
                logger.info(
                    "Workspace user list not accessible for %s (HTTP %s); role cannot be enumerated.",
                    guid,
                    exc.status_code,
                )
                return None
            raise

        items = payload.get("value") or []
        return [PowerBIWorkspaceUser.model_validate(item) for item in items]

    def list_reports(self, workspace_id: str) -> list[PowerBIReport]:
        """List reports inside an accessible workspace (`GET /groups/{id}/reports`)."""
        guid = _require_guid(workspace_id, "Workspace ID")
        payload = self._rest.get_json(f"/groups/{guid}/reports")
        items = payload.get("value") or []
        return [PowerBIReport.model_validate(item) for item in items]

    def get_report(self, workspace_id: str, report_id: str) -> PowerBIReport | None:
        """Retrieve a single report inside a workspace, or None if not found."""
        ws_guid = _require_guid(workspace_id, "Workspace ID")
        rpt_guid = _require_guid(report_id, "Report ID")
        try:
            payload = self._rest.get_json(f"/groups/{ws_guid}/reports/{rpt_guid}")
            return PowerBIReport.model_validate(payload)
        except PowerBIHttpError as exc:
            if exc.status_code == 404:
                return None
            raise
