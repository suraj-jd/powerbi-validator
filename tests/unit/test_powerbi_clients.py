"""Unit tests for Power BI WorkspaceClient, DatasetClient, and permission verification."""

from __future__ import annotations

import httpx
import pytest

from app.core.exceptions import PowerBIApiError
from app.integrations.powerbi.dataset_client import DatasetClient
from app.integrations.powerbi.rest_client import PowerBIRestClient
from app.integrations.powerbi.workspace_client import WorkspaceClient

WS_ID = "11111111-2222-3333-4444-555555555555"
DS_ID = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
OTHER_DS_ID = "99999999-bbbb-cccc-dddd-eeeeeeeeeeee"
RPT_ID = "12345678-1234-1234-1234-1234567890ab"


def _make_clients(handler) -> tuple[PowerBIRestClient, WorkspaceClient, DatasetClient]:
    rest = PowerBIRestClient(
        token_provider=lambda: "signed-in-token",
        transport=httpx.MockTransport(handler),
    )
    ws_client = WorkspaceClient(rest)
    ds_client = DatasetClient(rest, ws_client)
    return rest, ws_client, ds_client


def test_verify_access_succeeds_with_explicit_workspace_role() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path.endswith("/groups"):
            return httpx.Response(
                200,
                json={"value": [{"id": WS_ID, "name": "Bosch Analytics", "isReadOnly": False}]},
            )
        if path.endswith(f"/groups/{WS_ID}/users"):
            return httpx.Response(
                200,
                json={
                    "value": [
                        {
                            "emailAddress": "john.doe@contoso.com",
                            "displayName": "John Doe",
                            "groupUserAccessRight": "Member",
                        }
                    ]
                },
            )
        if path.endswith(f"/groups/{WS_ID}/datasets/{DS_ID}"):
            return httpx.Response(
                200,
                json={"id": DS_ID, "name": "HR Semantic Model", "isRefreshable": True},
            )
        if path.endswith(f"/groups/{WS_ID}/reports/{RPT_ID}"):
            return httpx.Response(
                200,
                json={"id": RPT_ID, "name": "Employee Dashboard", "datasetId": DS_ID},
            )
        return httpx.Response(404)

    rest, _, ds_client = _make_clients(handler)
    try:
        res = ds_client.verify_access(
            workspace_id=WS_ID,
            dataset_id=DS_ID,
            report_id=RPT_ID,
            signed_in_email="john.doe@contoso.com",
        )
        assert res.is_verified is True
        assert res.workspace is not None and res.workspace.name == "Bosch Analytics"
        assert res.dataset is not None and res.dataset.name == "HR Semantic Model"
        assert res.report is not None and res.report.name == "Employee Dashboard"
        assert res.effective_access_level == "Member"
        assert res.issues == []
    finally:
        rest.close()


def test_verify_access_handles_non_admin_403_on_users_without_claiming_owner() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path.endswith("/groups"):
            return httpx.Response(
                200,
                json={"value": [{"id": WS_ID, "name": "Finance Reports", "isReadOnly": False}]},
            )
        if path.endswith(f"/groups/{WS_ID}/users"):
            return httpx.Response(403, json={"error": {"code": "PowerBINotAuthorizedException"}})
        if path.endswith(f"/groups/{WS_ID}/datasets/{DS_ID}"):
            return httpx.Response(200, json={"id": DS_ID, "name": "Finance Model"})
        return httpx.Response(404)

    rest, _, ds_client = _make_clients(handler)
    try:
        res = ds_client.verify_access(
            workspace_id=WS_ID,
            dataset_id=DS_ID,
            signed_in_email="contributor@contoso.com",
        )
        assert res.is_verified is True
        assert "Owner" not in res.effective_access_level
        assert "not exposed" in res.effective_access_level.lower()
    finally:
        rest.close()


def test_verify_access_rejects_inaccessible_workspace() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/groups"):
            return httpx.Response(200, json={"value": []})
        return httpx.Response(404)

    rest, _, ds_client = _make_clients(handler)
    try:
        res = ds_client.verify_access(workspace_id=WS_ID, dataset_id=DS_ID)
        assert res.is_verified is False
        assert res.workspace_accessible is False
        assert res.effective_access_level == "Not Accessible"
        assert "Owner" not in res.effective_access_level
        assert len(res.issues) == 1
    finally:
        rest.close()


def test_verify_access_flags_missing_dataset_and_report_mismatch() -> None:
    # 1. Dataset not in workspace
    def missing_ds_handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path.endswith("/groups"):
            return httpx.Response(200, json={"value": [{"id": WS_ID, "name": "Analytics"}]})
        if path.endswith(f"/groups/{WS_ID}/users"):
            return httpx.Response(403)
        return httpx.Response(404)

    rest1, _, ds_client1 = _make_clients(missing_ds_handler)
    try:
        res = ds_client1.verify_access(workspace_id=WS_ID, dataset_id=DS_ID)
        assert res.workspace_accessible is True
        assert res.dataset_accessible is False
        assert res.is_verified is False
    finally:
        rest1.close()

    # 2. Report bound to a different dataset
    def mismatch_handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path.endswith("/groups"):
            return httpx.Response(200, json={"value": [{"id": WS_ID, "name": "Analytics"}]})
        if path.endswith(f"/groups/{WS_ID}/users"):
            return httpx.Response(403)
        if path.endswith(f"/groups/{WS_ID}/datasets/{DS_ID}"):
            return httpx.Response(200, json={"id": DS_ID, "name": "Expected Model"})
        if path.endswith(f"/groups/{WS_ID}/reports/{RPT_ID}"):
            return httpx.Response(
                200,
                json={"id": RPT_ID, "name": "Other Report", "datasetId": OTHER_DS_ID},
            )
        return httpx.Response(404)

    rest2, _, ds_client2 = _make_clients(mismatch_handler)
    try:
        res2 = ds_client2.verify_access(workspace_id=WS_ID, dataset_id=DS_ID, report_id=RPT_ID)
        assert res2.is_verified is True
        assert any("differs" in issue.lower() for issue in res2.issues)
    finally:
        rest2.close()


def test_invalid_guid_rejected_before_network_call() -> None:
    called = {"count": 0}

    def handler(_request: httpx.Request) -> httpx.Response:
        called["count"] += 1
        return httpx.Response(200, json={"value": []})

    rest, _, ds_client = _make_clients(handler)
    try:
        with pytest.raises(PowerBIApiError, match="GUID"):
            ds_client.verify_access(workspace_id="not-a-guid", dataset_id=DS_ID)
        assert called["count"] == 0
    finally:
        rest.close()


def test_my_workspace_lists_datasets_reports_and_verifies_access() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path.endswith("/groups"):
            return httpx.Response(200, json={"value": []})
        if path.endswith("/datasets"):
            return httpx.Response(200, json={"value": [{"id": DS_ID, "name": "Personal Model"}]})
        if path.endswith("/reports"):
            return httpx.Response(
                200,
                json={"value": [{"id": RPT_ID, "name": "Personal Report", "datasetId": DS_ID}]},
            )
        if path.endswith(f"/datasets/{DS_ID}"):
            return httpx.Response(200, json={"id": DS_ID, "name": "Personal Model"})
        if path.endswith(f"/reports/{RPT_ID}"):
            return httpx.Response(200, json={"id": RPT_ID, "name": "Personal Report", "datasetId": DS_ID})
        return httpx.Response(404)

    rest, ws_client, ds_client = _make_clients(handler)
    try:
        workspaces = ws_client.list_workspaces()
        assert len(workspaces) == 1
        assert workspaces[0].id == "me"
        assert "My Workspace" in workspaces[0].name

        datasets = ds_client.list_datasets("me")
        assert len(datasets) == 1 and datasets[0].name == "Personal Model"

        reports = ws_client.list_reports("me")
        assert len(reports) == 1 and reports[0].name == "Personal Report"

        res = ds_client.verify_access(workspace_id="me", dataset_id=DS_ID, report_id=RPT_ID)
        assert res.is_verified is True
        assert res.effective_access_level == "Personal Workspace"
    finally:
        rest.close()
