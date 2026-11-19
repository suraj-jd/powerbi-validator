"""Unit tests for Stage 8 RefreshClient, RefreshService, and Refresh Check evaluation."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from app.core.status import RefreshStatus, ValidationStatus
from app.database.db import DatabaseManager
from app.integrations.file_import import RegistrationInput
from app.integrations.powerbi.models import ParsedRefreshRecord
from app.integrations.powerbi.refresh_client import (
    RefreshClient,
    calculate_refresh_duration,
    map_api_refresh_status,
    parse_iso_datetime,
    parse_service_exception_json,
)
from app.services.registry_service import RegistryService
from app.services.refresh_service import RefreshService, format_duration

WS_ID = "33333333-4444-5555-6666-777777777777"
DS_ID = "cccccccc-dddd-eeee-ffff-000000000000"


@pytest.fixture
def db(tmp_path: Path):
    manager = DatabaseManager(tmp_path / "test_refresh.db")
    manager.run_migrations()
    try:
        yield manager
    finally:
        manager.dispose()


@pytest.fixture
def sample_reg_id(db: DatabaseManager) -> int:
    registry = RegistryService(db)
    rec = registry.create_registration(
        RegistrationInput(
            workspace_name="Ops Workspace",
            workspace_id=WS_ID,
            report_name="Daily Executive",
            report_id=None,
            dataset_name="Daily Ops Model",
            dataset_id=DS_ID,
            is_active=True,
        )
    )
    return rec.id


def test_parse_iso_datetime_and_timezone() -> None:
    dt1 = parse_iso_datetime("2026-11-19T10:30:00.000Z")
    assert dt1 is not None
    assert dt1.tzinfo == timezone.utc
    assert dt1.year == 2026
    assert dt1.hour == 10
    assert dt1.minute == 30

    dt2 = parse_iso_datetime("2026-11-19T10:30:00+00:00")
    assert dt2 is not None
    assert dt2 == dt1

    assert parse_iso_datetime(None) is None
    assert parse_iso_datetime("") is None
    assert parse_iso_datetime("not-a-timestamp") is None


def test_map_api_refresh_status() -> None:
    now = datetime.now(timezone.utc)
    # Success
    assert map_api_refresh_status("Completed", now) == RefreshStatus.SUCCESS
    assert map_api_refresh_status("Success", now) == RefreshStatus.SUCCESS

    # Failed
    assert map_api_refresh_status("Failed", now) == RefreshStatus.FAILED
    assert map_api_refresh_status("Cancelled", now) == RefreshStatus.FAILED

    # In Progress (explicit status or missing end_time)
    assert map_api_refresh_status("InProgress", None) == RefreshStatus.IN_PROGRESS
    assert map_api_refresh_status("NotStarted", None) == RefreshStatus.IN_PROGRESS
    assert map_api_refresh_status("Unknown", None) == RefreshStatus.IN_PROGRESS

    # Unknown
    assert map_api_refresh_status("Disabled", now) == RefreshStatus.UNKNOWN
    assert map_api_refresh_status("Unknown", now) == RefreshStatus.UNKNOWN


def test_calculate_refresh_duration_and_in_progress() -> None:
    t1 = datetime(2026, 11, 19, 10, 0, 0, tzinfo=timezone.utc)
    t2 = datetime(2026, 11, 19, 10, 4, 30, tzinfo=timezone.utc)

    # 4 minutes 30 seconds = 270,000 ms
    assert calculate_refresh_duration(t1, t2) == 270_000
    assert format_duration(270_000) == "4m 30s"

    # In-progress refresh (end_time is None) must return None without false duration
    assert calculate_refresh_duration(t1, None) is None
    assert format_duration(None) == "— (In Progress)"


def test_parse_service_exception_json() -> None:
    raw_pbi = (
        '{"error":{"code":"DM_GWPipeline_Gateway_TimeoutError",'
        '"pbi.error":{"details":[{"detail":{"value":"The operation timed out after 120s."}}]}}}'
    )
    assert parse_service_exception_json(raw_pbi) == "The operation timed out after 120s."

    raw_simple = '{"error":{"message":"Credentials expired for data source."}}'
    assert parse_service_exception_json(raw_simple) == "Credentials expired for data source."

    assert parse_service_exception_json(None) is None


def test_refresh_client_queries_and_parses(tmp_path: Path) -> None:
    mock_rest = MagicMock()
    mock_rest.get_json.return_value = {
        "value": [
            {
                "id": 1001,
                "refreshType": "Scheduled",
                "startTime": "2026-11-19T08:00:00.000Z",
                "endTime": "2026-11-19T08:05:00.000Z",
                "status": "Completed",
            },
            {
                "id": 1002,
                "refreshType": "ViaApi",
                "startTime": "2026-11-19T09:00:00.000Z",
                "endTime": None,
                "status": "InProgress",
            },
        ]
    }

    client = RefreshClient(mock_rest)
    records = client.list_refreshes(WS_ID, DS_ID, top=5)

    assert len(records) == 2
    # Item 0: completed
    assert records[0].refresh_id == "1001"
    assert records[0].status == RefreshStatus.SUCCESS
    assert records[0].duration_ms == 300_000

    # Item 1: in progress
    assert records[1].refresh_id == "1002"
    assert records[1].status == RefreshStatus.IN_PROGRESS
    assert records[1].duration_ms is None

    # Verify endpoint called
    mock_rest.get_json.assert_called_with(f"/groups/{WS_ID}/datasets/{DS_ID}/refreshes?$top=5")


def test_refresh_service_persistence_and_distinguishes_latest_and_success(
    db: DatabaseManager,
    sample_reg_id: int,
) -> None:
    mock_client = MagicMock()
    t1_start = datetime(2026, 11, 19, 6, 0, 0, tzinfo=timezone.utc)
    t1_end = datetime(2026, 11, 19, 6, 3, 0, tzinfo=timezone.utc)

    t2_start = datetime(2026, 11, 19, 7, 0, 0, tzinfo=timezone.utc)
    t2_end = datetime(2026, 11, 19, 7, 1, 0, tzinfo=timezone.utc)

    # Item 1 was successful, Item 2 failed
    mock_client.list_refreshes.return_value = [
        ParsedRefreshRecord(
            refresh_id="ref-latest-failed",
            status=RefreshStatus.FAILED,
            start_time=t2_start,
            end_time=t2_end,
            duration_ms=60_000,
            refresh_type="Scheduled",
            error_details="Credentials expired",
            raw_status="Failed",
        ),
        ParsedRefreshRecord(
            refresh_id="ref-earlier-success",
            status=RefreshStatus.SUCCESS,
            start_time=t1_start,
            end_time=t1_end,
            duration_ms=180_000,
            refresh_type="Scheduled",
            error_details=None,
            raw_status="Completed",
        ),
    ]

    service = RefreshService(db=db, refresh_client=mock_client)
    records = service.fetch_and_persist_refreshes(
        workspace_registration_id=sample_reg_id,
        workspace_id=WS_ID,
        dataset_id=DS_ID,
    )
    assert len(records) == 2

    # Latest attempt is Failed
    latest = service.get_latest_attempt(sample_reg_id)
    assert latest is not None
    assert latest.refresh_id == "ref-latest-failed"
    assert latest.status == RefreshStatus.FAILED
    assert latest.error_details == "Credentials expired"

    # Latest successful refresh is the earlier one (BRD Section 7, Stage 8 Task 7)
    latest_success = service.get_latest_successful(sample_reg_id)
    assert latest_success is not None
    assert latest_success.refresh_id == "ref-earlier-success"
    assert latest_success.status == RefreshStatus.SUCCESS


def test_evaluate_refresh_rule(db: DatabaseManager, sample_reg_id: int) -> None:
    mock_client = MagicMock()
    service = RefreshService(db=db, refresh_client=mock_client)

    # 1. No refresh records -> WARNING
    eval_no_data = service.evaluate_refresh_rule(sample_reg_id, {"expected_status": "Completed"})
    assert eval_no_data.status == ValidationStatus.WARNING
    assert "No refresh history" in eval_no_data.result_summary

    # 2. Add recent successful refresh -> PASS
    t_recent_start = datetime.now(timezone.utc) - timedelta(hours=2)
    t_recent_end = t_recent_start + timedelta(minutes=5)

    mock_client.list_refreshes.return_value = [
        ParsedRefreshRecord(
            refresh_id="ref-ok",
            status=RefreshStatus.SUCCESS,
            start_time=t_recent_start,
            end_time=t_recent_end,
            duration_ms=300_000,
            refresh_type="Scheduled",
            error_details=None,
            raw_status="Completed",
        )
    ]
    service.fetch_and_persist_refreshes(
        workspace_registration_id=sample_reg_id,
        workspace_id=WS_ID,
        dataset_id=DS_ID,
    )

    eval_pass = service.evaluate_refresh_rule(
        sample_reg_id,
        {"expected_status": "Completed", "max_age_hours": 24, "max_duration_minutes": 10},
    )
    assert eval_pass.status == ValidationStatus.PASS
    assert "completed successfully" in eval_pass.result_summary

    # 3. Exceeded max age threshold -> FAIL (Stale)
    eval_stale = service.evaluate_refresh_rule(
        sample_reg_id,
        {"expected_status": "Completed", "max_age_hours": 1.0},
    )
    assert eval_stale.status == ValidationStatus.FAIL
    assert "stale" in eval_stale.result_summary.lower()

    # 4. Exceeded max duration threshold -> FAIL (Slow)
    eval_slow = service.evaluate_refresh_rule(
        sample_reg_id,
        {"expected_status": "Completed", "max_duration_minutes": 2.0},
    )
    assert eval_slow.status == ValidationStatus.FAIL
    assert "exceeded" in eval_slow.result_summary.lower()

    # 5. Failed refresh -> FAIL
    t_fail_start = datetime.now(timezone.utc) - timedelta(minutes=30)
    mock_client.list_refreshes.return_value = [
        ParsedRefreshRecord(
            refresh_id="ref-broken",
            status=RefreshStatus.FAILED,
            start_time=t_fail_start,
            end_time=t_fail_start + timedelta(minutes=1),
            duration_ms=60_000,
            refresh_type="Scheduled",
            error_details="Data source timeout",
            raw_status="Failed",
        )
    ]
    service.fetch_and_persist_refreshes(
        workspace_registration_id=sample_reg_id,
        workspace_id=WS_ID,
        dataset_id=DS_ID,
    )

    eval_failed = service.evaluate_refresh_rule(
        sample_reg_id,
        {"expected_status": "Completed"},
    )
    assert eval_failed.status == ValidationStatus.FAIL
    assert "Data source timeout" in eval_failed.result_summary

    # 6. Test evaluating against Latest Success when Latest Attempt is Failed
    eval_target_success = service.evaluate_refresh_rule(
        sample_reg_id,
        {"expected_status": "Completed", "definition": "latest_success", "max_age_hours": 24},
    )
    assert eval_target_success.status == ValidationStatus.PASS
    assert eval_target_success.refresh_record is not None
    assert eval_target_success.refresh_record.refresh_id == "ref-ok"

    # 7. Test get_refresh_summary
    summary = service.get_refresh_summary(sample_reg_id)
    assert summary.total_runs == 2
    assert summary.success_count == 1
    assert summary.failure_count == 1
    assert summary.in_progress_count == 0
    assert summary.success_rate_pct == 50.0
    assert "50.0% (1/2)" in summary.success_rate_display
    assert summary.latest_attempt.refresh_id == "ref-broken"
    assert summary.latest_successful.refresh_id == "ref-ok"
    assert summary.latest_completed.refresh_id == "ref-broken"

