"""Power BI REST API connectors and typed response models."""

from app.integrations.powerbi.dax_client import (
    DaxConnectorInterface,
    DaxQueryClient,
    DaxQueryResult,
    RestExecuteQueriesConnector,
    XmlaAdomdConnector,
    build_measure_query,
    build_test_query,
    escape_column_reference,
    escape_measure_name,
    escape_table_name,
)
from app.integrations.powerbi.dataset_client import DatasetClient
from app.integrations.powerbi.metadata_client import MetadataClient
from app.integrations.powerbi.models import (
    AccessVerificationResult,
    DatasetMetadata,
    ParsedRefreshRecord,
    PowerBIDataset,
    PowerBIRefreshItem,
    PowerBIReport,
    PowerBIWorkspace,
    PowerBIWorkspaceUser,
    SemanticColumnMetadata,
    SemanticMeasureMetadata,
    SemanticTableMetadata,
)
from app.integrations.powerbi.refresh_client import RefreshClient
from app.integrations.powerbi.rest_client import PowerBIHttpError, PowerBIRestClient
from app.integrations.powerbi.workspace_client import MY_WORKSPACE_ID, WorkspaceClient

__all__ = [
    "AccessVerificationResult",
    "DaxConnectorInterface",
    "DaxQueryClient",
    "DaxQueryResult",
    "DatasetClient",
    "DatasetMetadata",
    "MY_WORKSPACE_ID",
    "MetadataClient",
    "ParsedRefreshRecord",
    "PowerBIDataset",
    "PowerBIHttpError",
    "PowerBIRefreshItem",
    "PowerBIReport",
    "PowerBIRestClient",
    "PowerBIWorkspace",
    "PowerBIWorkspaceUser",
    "RefreshClient",
    "SemanticColumnMetadata",
    "SemanticMeasureMetadata",
    "SemanticTableMetadata",
    "WorkspaceClient",
]
