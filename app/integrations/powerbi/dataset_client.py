"""Power BI semantic model (dataset) client and end-to-end access verifier."""

from __future__ import annotations

import logging

from app.integrations.powerbi.models import (
    AccessVerificationResult,
    PowerBIDataset,
    PowerBIWorkspace,
    PowerBIWorkspaceUser,
)
from app.integrations.powerbi.rest_client import PowerBIHttpError, PowerBIRestClient
from app.integrations.powerbi.workspace_client import WorkspaceClient, _require_guid

logger = logging.getLogger(__name__)


def _resolve_effective_access_level(
    workspace: PowerBIWorkspace,
    users: list[PowerBIWorkspaceUser] | None,
    signed_in_email: str | None,
) -> str:
    """Determine honest workspace access level strictly from API responses.

    Never fabricates 'Owner' or 'Admin' when the API does not confirm it.
    """
    if users and signed_in_email:
        target = signed_in_email.strip().lower()
        for entry in users:
            email = (entry.email_address or "").strip().lower()
            ident = (entry.identifier or "").strip().lower()
            if target in (email, ident) and entry.access_right:
                return entry.access_right

    if workspace.is_read_only:
        return "Accessible (Read-Only)"
    return "Accessible (Role not exposed by API)"


class DatasetClient:
    """Queries semantic models and verifies workspace, dataset, and report access."""

    def __init__(
        self,
        rest_client: PowerBIRestClient,
        workspace_client: WorkspaceClient | None = None,
    ) -> None:
        self._rest = rest_client
        self._workspaces = workspace_client or WorkspaceClient(rest_client)

    def list_datasets(self, workspace_id: str) -> list[PowerBIDataset]:
        """List semantic models in a workspace (`GET /groups/{id}/datasets`)."""
        ws_guid = _require_guid(workspace_id, "Workspace ID")
        payload = self._rest.get_json(f"/groups/{ws_guid}/datasets")
        items = payload.get("value") or []
        return [PowerBIDataset.model_validate(item) for item in items]

    def get_dataset(self, workspace_id: str, dataset_id: str) -> PowerBIDataset | None:
        """Retrieve a specific semantic model in a workspace, or None if not found."""
        ws_guid = _require_guid(workspace_id, "Workspace ID")
        ds_guid = _require_guid(dataset_id, "Dataset ID")
        try:
            payload = self._rest.get_json(f"/groups/{ws_guid}/datasets/{ds_guid}")
            return PowerBIDataset.model_validate(payload)
        except PowerBIHttpError as exc:
            if exc.status_code == 404:
                return None
            raise

    def verify_access(
        self,
        *,
        workspace_id: str,
        dataset_id: str,
        report_id: str | None = None,
        signed_in_email: str | None = None,
    ) -> AccessVerificationResult:
        """Verify that the signed-in user can access the workspace, dataset, and optional report."""
        ws_guid = _require_guid(workspace_id, "Workspace ID")
        ds_guid = _require_guid(dataset_id, "Dataset ID")
        rpt_guid = _require_guid(report_id, "Report ID") if report_id and report_id.strip() else None

        result = AccessVerificationResult(
            workspace_id=ws_guid,
            dataset_id=ds_guid,
            report_id=rpt_guid,
        )

        # 1. Verify workspace accessibility
        workspace = self._workspaces.get_workspace(ws_guid)
        if workspace is None:
            result.workspace_accessible = False
            result.effective_access_level = "Not Accessible"
            result.issues.append(
                f"Workspace {ws_guid} was not found or is not accessible to the signed-in account."
            )
            result.summary = "Workspace access verification failed."
            return result

        result.workspace_accessible = True
        result.workspace = workspace

        users = self._workspaces.get_workspace_users(ws_guid)
        result.effective_access_level = _resolve_effective_access_level(
            workspace,
            users,
            signed_in_email,
        )

        # 2. Verify dataset exists in and belongs to this workspace
        try:
            dataset = self.get_dataset(ws_guid, ds_guid)
        except PowerBIHttpError as exc:
            if exc.status_code in (401, 403):
                result.dataset_accessible = False
                result.issues.append(exc.user_message)
                result.summary = (
                    f"Workspace '{workspace.name}' is accessible ({result.effective_access_level}), "
                    "but dataset access was denied."
                )
                return result
            raise

        if dataset is None:
            result.dataset_accessible = False
            result.issues.append(
                f"Dataset {ds_guid} was not found inside workspace '{workspace.name}'."
            )
            result.summary = (
                f"Workspace '{workspace.name}' is accessible, but the specified Dataset ID "
                "was not found in this workspace."
            )
            return result

        result.dataset_accessible = True
        result.dataset = dataset

        # 3. Verify optional report ID and confirm it binds to the expected semantic model
        if rpt_guid is not None:
            try:
                report = self._workspaces.get_report(ws_guid, rpt_guid)
            except PowerBIHttpError as exc:
                if exc.status_code in (401, 403):
                    result.report_accessible = False
                    result.issues.append(exc.user_message)
                    result.summary = "Workspace and dataset verified, but report access was denied."
                    return result
                raise

            if report is None:
                result.report_accessible = False
                result.issues.append(
                    f"Report {rpt_guid} was not found inside workspace '{workspace.name}'."
                )
            else:
                result.report_accessible = True
                result.report = report
                if report.dataset_id and report.dataset_id.lower() != ds_guid:
                    result.issues.append(
                        f"Report '{report.name}' is bound to dataset {report.dataset_id}, "
                        f"which differs from the supplied Dataset ID ({ds_guid})."
                    )

        if result.is_verified and not result.issues:
            result.summary = (
                f"Verified access to workspace '{workspace.name}' "
                f"({result.effective_access_level}) and dataset '{dataset.name}'."
            )
        elif result.is_verified:
            result.summary = (
                f"Workspace '{workspace.name}' and dataset '{dataset.name}' are accessible, "
                "with warnings noted below."
            )
        else:
            result.summary = "Access verification completed with errors."

        logger.info(
            "Verified Power BI access: workspace=%s (%s) dataset_ok=%s report_ok=%s",
            ws_guid,
            result.effective_access_level,
            result.dataset_accessible,
            result.report_accessible,
        )
        return result
