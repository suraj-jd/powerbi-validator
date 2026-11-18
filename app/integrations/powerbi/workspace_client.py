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

MY_WORKSPACE_ID = "me"
_MY_WORKSPACE_ALIASES = {"me", "my-workspace", "my workspace", "myworkspace"}


def is_my_workspace(workspace_id: str) -> bool:
    """Return True if `workspace_id` refers to the signed-in user's personal My Workspace."""
    return workspace_id.strip().lower() in _MY_WORKSPACE_ALIASES


def is_valid_workspace_id(workspace_id: str) -> bool:
    """Return True if `workspace_id` is either a valid GUID or the My Workspace identifier."""
    return is_my_workspace(workspace_id) or is_valid_guid(workspace_id)


def _my_workspace_model() -> PowerBIWorkspace:
    return PowerBIWorkspace(
        id=MY_WORKSPACE_ID,
        name="My Workspace (Personal)",
        isReadOnly=False,
        type="PersonalGroup",
    )


def _require_guid(value: str, label: str) -> str:
    cleaned = value.strip()
    if not is_valid_guid(cleaned):
        raise PowerBIApiError(
            f"Invalid {label} GUID: {cleaned!r}",
            user_message=f"{label} must be a valid GUID (xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx).",
        )
    return cleaned.lower()


def _require_workspace_id(value: str) -> str:
    if is_my_workspace(value):
        return MY_WORKSPACE_ID
    return _require_guid(value, "Workspace ID")


class WorkspaceClient:
    """Queries accessible Power BI workspaces, roles, and reports for the signed-in user."""

    def __init__(self, rest_client: PowerBIRestClient) -> None:
        self._rest = rest_client

    def list_workspaces(self, *, include_my_workspace: bool = True) -> list[PowerBIWorkspace]:
        """Return Power BI workspaces accessible to the signed-in user (`GET /groups`).

        Because Microsoft's `GET /groups` endpoint excludes the user's personal
        'My Workspace', `include_my_workspace=True` prepends it so personal reports
        and semantic models can also be selected and validated.
        """
        payload = self._rest.get_json("/groups")
        items = payload.get("value") or []
        shared = [PowerBIWorkspace.model_validate(item) for item in items]
        if include_my_workspace:
            return [_my_workspace_model(), *shared]
        return shared

    def get_workspace(self, workspace_id: str) -> PowerBIWorkspace | None:
        """Retrieve a specific workspace by GUID (or `'me'` for personal My Workspace)."""
        ws_id = _require_workspace_id(workspace_id)
        if ws_id == MY_WORKSPACE_ID:
            return _my_workspace_model()

        payload = self._rest.get_json("/groups", params={"$filter": f"id eq '{ws_id}'"})
        items = payload.get("value") or []
        for item in items:
            ws = PowerBIWorkspace.model_validate(item)
            if ws.id.lower() == ws_id:
                return ws
        return None

    def get_workspace_users(self, workspace_id: str) -> list[PowerBIWorkspaceUser] | None:
        """Return workspace user role assignments when permitted by the API.

        Returns `None` for My Workspace or when the API denies listing workspace members
        (HTTP 403/401).
        """
        ws_id = _require_workspace_id(workspace_id)
        if ws_id == MY_WORKSPACE_ID:
            return None

        try:
            payload = self._rest.get_json(f"/groups/{ws_id}/users")
        except PowerBIHttpError as exc:
            if exc.status_code in (401, 403, 404):
                logger.info(
                    "Workspace user list not accessible for %s (HTTP %s); role cannot be enumerated.",
                    ws_id,
                    exc.status_code,
                )
                return None
            raise

        items = payload.get("value") or []
        return [PowerBIWorkspaceUser.model_validate(item) for item in items]

    def list_reports(self, workspace_id: str) -> list[PowerBIReport]:
        """List reports inside an accessible workspace or My Workspace."""
        ws_id = _require_workspace_id(workspace_id)
        path = "/reports" if ws_id == MY_WORKSPACE_ID else f"/groups/{ws_id}/reports"
        payload = self._rest.get_json(path)
        items = payload.get("value") or []
        return [PowerBIReport.model_validate(item) for item in items]

    def get_report(self, workspace_id: str, report_id: str) -> PowerBIReport | None:
        """Retrieve a single report inside a workspace or My Workspace, or None if not found."""
        ws_id = _require_workspace_id(workspace_id)
        rpt_guid = _require_guid(report_id, "Report ID")
        path = (
            f"/reports/{rpt_guid}"
            if ws_id == MY_WORKSPACE_ID
            else f"/groups/{ws_id}/reports/{rpt_guid}"
        )
        try:
            payload = self._rest.get_json(path)
            return PowerBIReport.model_validate(payload)
        except PowerBIHttpError as exc:
            if exc.status_code == 404:
                return None
            raise
