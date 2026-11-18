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


@dataclass(slots=True)
class SemanticColumnMetadata:
    """Discovered column metadata for a Power BI semantic model table."""

    name: str
    data_type: str | None = None
    is_hidden: bool = False
    description: str = ""


@dataclass(slots=True)
class SemanticTableMetadata:
    """Discovered table metadata containing its collection of columns."""

    name: str
    columns: list[SemanticColumnMetadata] = field(default_factory=list)
    description: str = ""

    @property
    def column_names(self) -> list[str]:
        return [c.name for c in self.columns]

    def get_column(self, name: str) -> SemanticColumnMetadata | None:
        target = name.strip().lower()
        for col in self.columns:
            if col.name.lower() == target:
                return col
        return None


@dataclass(slots=True)
class SemanticMeasureMetadata:
    """Discovered DAX measure metadata in a Power BI semantic model."""

    name: str
    table_name: str | None = None
    expression: str | None = None
    description: str = ""


@dataclass(slots=True)
class DatasetMetadata:
    """Discovered tables, columns, and measures for a target Power BI semantic model."""

    dataset_id: str
    workspace_id: str
    tables: list[SemanticTableMetadata] = field(default_factory=list)
    measures: list[SemanticMeasureMetadata] = field(default_factory=list)
    is_supported: bool = True
    source: str = "execute_queries"
    error_message: str | None = None

    @property
    def table_names(self) -> list[str]:
        return [t.name for t in self.tables]

    @property
    def measure_names(self) -> list[str]:
        return [m.name for m in self.measures]

    def get_table(self, name: str) -> SemanticTableMetadata | None:
        target = name.strip().lower()
        for tbl in self.tables:
            if tbl.name.lower() == target:
                return tbl
        return None

    def get_column(self, table_name: str, column_name: str) -> SemanticColumnMetadata | None:
        tbl = self.get_table(table_name)
        if tbl is None:
            return None
        return tbl.get_column(column_name)

    def get_measure(self, name: str) -> SemanticMeasureMetadata | None:
        target = name.strip().lower()
        for meas in self.measures:
            if meas.name.lower() == target:
                return meas
        return None

    def validate_object(
        self,
        target_type: str,
        table_name: str | None,
        column_or_measure_name: str | None,
    ) -> tuple[bool, str]:
        """Validate whether a target object exists in this dataset's discovered metadata.

        Returns (is_valid, message).
        If metadata discovery is unsupported, returns (True, warning_message)
        allowing manual entry fallback without blocking the user.
        """
        normalized_type = (target_type or "").strip().lower()

        # Refresh and Model-level checks do not target a specific table/column
        if normalized_type in ("refresh", "model", "refresh / model"):
            return True, "Model-level check does not require table or column targets."

        if not self.is_supported:
            return (
                True,
                "Metadata discovery is not supported for this dataset; manual entry will be evaluated during execution.",
            )

        if normalized_type in ("measure", "dax measure", "dax_measure"):
            if not column_or_measure_name or not column_or_measure_name.strip():
                return False, "Measure name is required."
            m = self.get_measure(column_or_measure_name)
            if m is not None:
                home = f" in table '{m.table_name}'" if m.table_name else ""
                return True, f"Measure '{m.name}' verified{home}."
            return (
                False,
                f"Measure '{column_or_measure_name.strip()}' was not found in discovered model metadata.",
            )

        # Column / Table check
        if not table_name or not table_name.strip():
            return False, "Table name is required."
        tbl = self.get_table(table_name)
        if tbl is None:
            return False, f"Table '{table_name.strip()}' was not found in discovered model metadata."

        if not column_or_measure_name or not column_or_measure_name.strip():
            return False, "Column name is required."
        col = tbl.get_column(column_or_measure_name)
        if col is not None:
            return True, f"Column '{col.name}' verified in table '{tbl.name}'."
        return (
            False,
            f"Column '{column_or_measure_name.strip()}' was not found in table '{tbl.name}'.",
        )
