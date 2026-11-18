"""Pydantic models for Power BI Service REST API responses and access verification."""

from __future__ import annotations

from dataclasses import dataclass, field

from pydantic import BaseModel, ConfigDict, Field


class PowerBIWorkspace(BaseModel):
    """Power BI workspace (group) returned by GET /groups."""

    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    id: str
    name: str
    is_read_only: bool = Field(default=False, alias="isReadOnly")
    is_on_dedicated_capacity: bool = Field(default=False, alias="isOnDedicatedCapacity")
    type: str | None = None
    state: str | None = None


class PowerBIWorkspaceUser(BaseModel):
    """Workspace user entry returned by GET /groups/{groupId}/users."""

    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    email_address: str | None = Field(default=None, alias="emailAddress")
    identifier: str | None = None
    display_name: str | None = Field(default=None, alias="displayName")
    principal_type: str | None = Field(default=None, alias="principalType")
    access_right: str | None = Field(default=None, alias="groupUserAccessRight")


class PowerBIDataset(BaseModel):
    """Power BI semantic model (dataset) returned by GET /groups/{groupId}/datasets."""

    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    id: str
    name: str
    configured_by: str | None = Field(default=None, alias="configuredBy")
    is_refreshable: bool | None = Field(default=None, alias="isRefreshable")
    is_effective_identity_required: bool | None = Field(
        default=None,
        alias="isEffectiveIdentityRequired",
    )
    web_url: str | None = Field(default=None, alias="webUrl")


class PowerBIReport(BaseModel):
    """Power BI report returned by GET /groups/{groupId}/reports."""

    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    id: str
    name: str
    dataset_id: str | None = Field(default=None, alias="datasetId")
    web_url: str | None = Field(default=None, alias="webUrl")
    report_type: str | None = Field(default=None, alias="reportType")


@dataclass(slots=True)
class AccessVerificationResult:
    """Outcome of verifying the signed-in user's access to a workspace, dataset, and report."""

    workspace_id: str
    dataset_id: str
    report_id: str | None = None
    workspace_accessible: bool = False
    dataset_accessible: bool = False
    report_accessible: bool | None = None
    workspace: PowerBIWorkspace | None = None
    dataset: PowerBIDataset | None = None
    report: PowerBIReport | None = None
    effective_access_level: str = "Not Accessible"
    summary: str = ""
    issues: list[str] = field(default_factory=list)

    @property
    def is_verified(self) -> bool:
        report_ok = True if self.report_accessible is None else self.report_accessible
        return self.workspace_accessible and self.dataset_accessible and report_ok
