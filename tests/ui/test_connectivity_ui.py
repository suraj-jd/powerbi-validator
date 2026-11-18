"""UI tests for Stage 4 Power BI connectivity and access verification panel."""

from __future__ import annotations

from app.auth.msal_auth import AuthAccount, AuthStateSnapshot, AuthStatus
from app.integrations.powerbi.models import (
    AccessVerificationResult,
    PowerBIDataset,
    PowerBIReport,
    PowerBIWorkspace,
)
from app.ui.pages.home_page import HomePage

WS_ID = "11111111-2222-3333-4444-555555555555"
DS_ID = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
RPT_ID = "12345678-1234-1234-1234-1234567890ab"


def test_home_page_populates_workspaces_datasets_and_displays_verification(qtbot) -> None:
    page = HomePage()
    qtbot.addWidget(page)
    page.show()

    page.auth_banner.apply_state(
        AuthStateSnapshot(
            status=AuthStatus.AUTHENTICATED,
            account=AuthAccount(
                home_account_id="oid.tid",
                display_name="John Doe",
                username="john.doe@contoso.com",
                tenant_id="tid",
            ),
            client_id_configured=True,
        )
    )

    page.set_workspaces([PowerBIWorkspace(id=WS_ID, name="Bosch Analytics")])
    assert page.workspace_combo.count() == 2

    page.set_workspace_assets(
        WS_ID,
        [PowerBIDataset(id=DS_ID, name="HR Semantic Model")],
        [PowerBIReport(id=RPT_ID, name="Employee Dashboard", datasetId=DS_ID)],
    )
    assert page.dataset_combo.count() == 2

    # Selecting dataset populates Dataset ID and auto-fills matching Report ID
    page.dataset_combo.setCurrentIndex(1)
    assert page.dataset_id_input.text() == DS_ID
    assert page.report_id_input.text() == RPT_ID

    result = AccessVerificationResult(
        workspace_id=WS_ID,
        dataset_id=DS_ID,
        report_id=RPT_ID,
        workspace_accessible=True,
        dataset_accessible=True,
        report_accessible=True,
        workspace=PowerBIWorkspace(id=WS_ID, name="Bosch Analytics"),
        dataset=PowerBIDataset(id=DS_ID, name="HR Semantic Model"),
        report=PowerBIReport(id=RPT_ID, name="Employee Dashboard", datasetId=DS_ID),
        effective_access_level="Contributor",
        summary="Verified access to workspace 'Bosch Analytics' (Contributor) and dataset 'HR Semantic Model'.",
    )
    page.display_verification_result(result)
    page.auth_banner.apply_state(
        AuthStateSnapshot(
            status=AuthStatus.AUTHENTICATED,
            account=AuthAccount(
                home_account_id="oid.tid",
                display_name="John Doe",
                username="john.doe@contoso.com",
                tenant_id="tid",
            ),
            client_id_configured=True,
        )
    )

    assert page.verification_banner.isVisible()
    assert page.verification_details_label.isVisible()
    assert "Contributor" in page.verification_details_label.text()
    assert "Bosch Analytics — Contributor" in page.auth_banner.details_label.text()
