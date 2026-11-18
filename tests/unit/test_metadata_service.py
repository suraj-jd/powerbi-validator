"""Unit tests for Stage 6 MetadataService asynchronous operations and caching."""

from __future__ import annotations

from unittest.mock import MagicMock

from app.integrations.powerbi.models import (
    DatasetMetadata,
    SemanticColumnMetadata,
    SemanticMeasureMetadata,
    SemanticTableMetadata,
)
from app.services.metadata_service import MetadataService

DATASET_ID = "11111111-2222-3333-4444-555555555555"
WORKSPACE_ID = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"


def test_metadata_service_fetches_async_and_caches(qtbot) -> None:
    tbl = SemanticTableMetadata(name="Orders", columns=[SemanticColumnMetadata(name="Sales")])
    meas = SemanticMeasureMetadata(name="Total Sales")
    expected_meta = DatasetMetadata(
        dataset_id=DATASET_ID,
        workspace_id=WORKSPACE_ID,
        tables=[tbl],
        measures=[meas],
        is_supported=True,
    )

    mock_client = MagicMock()
    mock_client.discover_metadata.return_value = expected_meta

    service = MetadataService(metadata_client=mock_client)

    loaded_events: list[DatasetMetadata] = []
    service.metadata_loaded.connect(loaded_events.append)

    # Initial async fetch triggers background worker
    with qtbot.waitSignal(service.metadata_loaded, timeout=2000):
        service.fetch_metadata_async(workspace_id=WORKSPACE_ID, dataset_id=DATASET_ID)

    assert len(loaded_events) == 1
    assert loaded_events[0] is expected_meta
    assert mock_client.discover_metadata.call_count == 1

    # Second call without force_refresh returns from cache without calling discover_metadata again
    cached = service.get_cached_metadata(workspace_id=WORKSPACE_ID, dataset_id=DATASET_ID)
    assert cached is expected_meta

    service.fetch_metadata_async(workspace_id=WORKSPACE_ID, dataset_id=DATASET_ID, force_refresh=False)
    assert len(loaded_events) == 2
    assert mock_client.discover_metadata.call_count == 1  # Not called again!

    # Calling with force_refresh=True invokes client again
    with qtbot.waitSignal(service.metadata_loaded, timeout=2000):
        service.fetch_metadata_async(workspace_id=WORKSPACE_ID, dataset_id=DATASET_ID, force_refresh=True)

    assert len(loaded_events) == 3
    assert mock_client.discover_metadata.call_count == 2

    # Validate object helper uses cached metadata
    ok, msg = service.validate_object(WORKSPACE_ID, DATASET_ID, "column", "Orders", "Sales")
    assert ok
    assert "verified" in msg.lower()

    # Clear cache removes in-memory entry
    service.clear_cache()
    assert service.get_cached_metadata(WORKSPACE_ID, DATASET_ID) is None
