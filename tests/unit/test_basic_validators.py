"""Unit tests for Stage 10 deterministic validation checks (Null, Duplicate, Latest Date, Row Count, Refresh)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

import pytest

from app.core.formatting import format_hours_duration
from app.core.status import RefreshStatus, ValidationStatus
from app.integrations.powerbi.dax_client import DaxQueryClient, DaxQueryResult
from app.services.refresh_service import RefreshRecordDTO, RefreshService
from app.services.rule_service import (
    RuleRecord,
    VALIDATION_TYPE_DUPLICATE,
    VALIDATION_TYPE_LATEST_DATE,
    VALIDATION_TYPE_NULL,
    VALIDATION_TYPE_REFRESH,
    VALIDATION_TYPE_ROW_COUNT,
)
from app.validation.validator_factory import get_validator
from app.validation.validators.duplicate_validator import DuplicateValidator
from app.validation.validators.latest_date_validator import LatestDateValidator
from app.validation.validators.null_validator import NullValidator
from app.validation.validators.refresh_validator import RefreshValidator
from app.validation.validators.row_count_validator import RowCountValidator


def _make_rule(
    val_type: str,
    *,
    rule_id: int = 1,
    rule_name: str = "Test Rule",
    tbl: str | None = "Sales",
    col: str | None = "Amount",
    config: dict | None = None,
) -> RuleRecord:
    return RuleRecord(
        id=rule_id,
        workspace_registration_id=10,
        rule_name=rule_name,
        enabled=True,
        target_type="COLUMN" if val_type != VALIDATION_TYPE_REFRESH else "MODEL",
        table_name=tbl,
        column_name=col,
        measure_name=None,
        validation_type=val_type,
        config=config or {},
        display_order=1,
    )


# =========================================================================
# NullValidator Tests
# =========================================================================

def test_null_validator_passes_when_under_threshold():
    client = MagicMock(spec=DaxQueryClient)
    client.execute_raw_dax.return_value = DaxQueryResult.from_raw_rows(
        [{"[TotalRows]": 1000, "[BlankCount]": 5}], duration_ms=25
    )

    validator = NullValidator()
    rule = _make_rule(VALIDATION_TYPE_NULL, config={"allowed_blank_count": 10, "allowed_blank_percentage": 2.0})

    res = validator.validate(rule=rule, dax_client=client, workspace_id="ws1", dataset_id="ds1")

    assert res.status == ValidationStatus.PASS
    assert "5 blanks / 1,000 rows (0.5%)" in res.actual_value
    assert res.duration_ms == 25


def test_null_validator_with_filters():
    client = MagicMock(spec=DaxQueryClient)
    client.execute_raw_dax.return_value = DaxQueryResult.from_raw_rows(
        [{"[TotalRows]": 100, "[BlankCount]": 0}], duration_ms=25
    )

    validator = NullValidator()
    rule = _make_rule(
        VALIDATION_TYPE_NULL,
        config={"allowed_blank_count": 0, "filter_1": "'Dates'[Year] = 2024", "filter_2": "'Region'[Country] = \"US\""},
    )

    res = validator.validate(rule=rule, dax_client=client, workspace_id="ws1", dataset_id="ds1")
    assert res.status == ValidationStatus.PASS
    executed_query = client.execute_raw_dax.call_args[0][2]
    assert "CALCULATETABLE('Sales', 'Dates'[Year] = 2024, 'Region'[Country] = \"US\")" in executed_query


def test_null_validator_fails_when_count_exceeded():
    client = MagicMock(spec=DaxQueryClient)
    client.execute_raw_dax.return_value = DaxQueryResult.from_raw_rows(
        [{"[TotalRows]": 500, "[BlankCount]": 50}], duration_ms=30
    )

    validator = NullValidator()
    rule = _make_rule(VALIDATION_TYPE_NULL, config={"allowed_blank_count": 0, "allowed_blank_percentage": 0.0})

    res = validator.validate(rule=rule, dax_client=client, workspace_id="ws1", dataset_id="ds1")

    assert res.status == ValidationStatus.FAIL
    assert "+50 blanks over limit" in res.deviation
    assert "50 blanks / 500 rows (10.0%)" in res.actual_value


def test_null_validator_handles_empty_table():
    client = MagicMock(spec=DaxQueryClient)
    client.execute_raw_dax.return_value = DaxQueryResult.from_raw_rows(
        [{"[TotalRows]": 0, "[BlankCount]": 0}], duration_ms=10
    )

    validator = NullValidator()
    rule = _make_rule(VALIDATION_TYPE_NULL)

    res = validator.validate(rule=rule, dax_client=client, workspace_id="ws1", dataset_id="ds1")

    assert res.status == ValidationStatus.PASS
    assert "0 blanks detected" in res.result_summary


def test_null_validator_error_on_query_failure():
    client = MagicMock(spec=DaxQueryClient)
    client.execute_raw_dax.return_value = DaxQueryResult.from_error("Syntax error in DAX expression", duration_ms=15)

    validator = NullValidator()
    rule = _make_rule(VALIDATION_TYPE_NULL)

    res = validator.validate(rule=rule, dax_client=client, workspace_id="ws1", dataset_id="ds1")

    assert res.status == ValidationStatus.ERROR
    assert "Syntax error in DAX" in res.result_summary


# =========================================================================
# DuplicateValidator Tests
# =========================================================================

def test_duplicate_validator_passes_when_unique():
    client = MagicMock(spec=DaxQueryClient)
    client.execute_raw_dax.return_value = DaxQueryResult.from_raw_rows(
        [{"[TotalRows]": 1000, "[DistinctKeys]": 1000}], duration_ms=40
    )

    validator = DuplicateValidator()
    rule = _make_rule(VALIDATION_TYPE_DUPLICATE, col="OrderID", config={"allowed_duplicate_count": 0})

    res = validator.validate(rule=rule, dax_client=client, workspace_id="ws1", dataset_id="ds1")

    assert res.status == ValidationStatus.PASS
    assert "0 duplicates / 1,000 rows" in res.actual_value
    assert res.deviation == "None (Within threshold)"


def test_duplicate_validator_fails_when_duplicates_exist():
    client = MagicMock(spec=DaxQueryClient)
    client.execute_raw_dax.return_value = DaxQueryResult.from_raw_rows(
        [{"[TotalRows]": 1000, "[DistinctKeys]": 980}], duration_ms=45
    )

    validator = DuplicateValidator()
    rule = _make_rule(VALIDATION_TYPE_DUPLICATE, col="CustomerID", config={"allowed_duplicate_count": 5})

    res = validator.validate(rule=rule, dax_client=client, workspace_id="ws1", dataset_id="ds1")

    assert res.status == ValidationStatus.FAIL
    assert "+15 duplicates over limit" in res.deviation
    assert "20 duplicates / 1,000 rows (2.0%)" in res.actual_value


def test_duplicate_validator_supports_composite_keys():
    client = MagicMock(spec=DaxQueryClient)
    client.execute_raw_dax.return_value = DaxQueryResult.from_raw_rows(
        [{"[TotalRows]": 500, "[DistinctKeys]": 500}], duration_ms=30
    )

    validator = DuplicateValidator()
    rule = _make_rule(
        VALIDATION_TYPE_DUPLICATE,
        col=None,
        config={"key_columns": ["Region", "FiscalYear", "Quarter"], "allowed_duplicate_count": 0},
    )

    res = validator.validate(rule=rule, dax_client=client, workspace_id="ws1", dataset_id="ds1")

    assert res.status == ValidationStatus.PASS
    assert "Region, FiscalYear, Quarter" in res.result_summary
    # Verify DAX query uses SUMMARIZE with all 3 columns
    query_called = client.execute_raw_dax.call_args[0][2]
    assert "'Sales'[Region]" in query_called
    assert "'Sales'[FiscalYear]" in query_called
    assert "'Sales'[Quarter]" in query_called


# =========================================================================
# LatestDateValidator Tests
# =========================================================================

def test_latest_date_validator_passes_when_fresh():
    client = MagicMock(spec=DaxQueryClient)
    ref_time = datetime(2026, 11, 19, 12, 0, 0, tzinfo=timezone.utc)
    latest_date_str = "2026-11-19T10:00:00Z"  # 2 hours old

    client.execute_raw_dax.return_value = DaxQueryResult.from_raw_rows(
        [{"[TotalRows]": 100, "[LatestDate]": latest_date_str}], duration_ms=35
    )

    validator = LatestDateValidator()
    rule = _make_rule(VALIDATION_TYPE_LATEST_DATE, col="OrderDate", config={"max_age_hours": 24.0})

    res = validator.validate(
        rule=rule,
        dax_client=client,
        workspace_id="ws1",
        dataset_id="ds1",
        context={"reference_timestamp": ref_time},
    )

    assert res.status == ValidationStatus.PASS
    assert "2.0h ago" in res.actual_value
    assert "margin" in res.deviation


def test_latest_date_validator_fails_when_stale():
    client = MagicMock(spec=DaxQueryClient)
    ref_time = datetime(2026, 11, 19, 12, 0, 0, tzinfo=timezone.utc)
    latest_date_str = "2026-11-17T12:00:00Z"  # 48 hours old

    client.execute_raw_dax.return_value = DaxQueryResult.from_raw_rows(
        [{"[TotalRows]": 100, "[LatestDate]": latest_date_str}], duration_ms=35
    )

    validator = LatestDateValidator()
    rule = _make_rule(VALIDATION_TYPE_LATEST_DATE, col="OrderDate", config={"max_age_hours": 24.0})

    res = validator.validate(
        rule=rule,
        dax_client=client,
        workspace_id="ws1",
        dataset_id="ds1",
        context={"reference_timestamp": ref_time},
    )

    assert res.status == ValidationStatus.FAIL
    assert "Data is stale" in res.result_summary
    assert "+24.0h over limit" in res.deviation


def test_latest_date_validator_detects_future_dates():
    client = MagicMock(spec=DaxQueryClient)
    ref_time = datetime(2026, 11, 19, 12, 0, 0, tzinfo=timezone.utc)
    future_date_str = "2026-11-20T12:00:00Z"  # 24 hours in the future

    client.execute_raw_dax.return_value = DaxQueryResult.from_raw_rows(
        [{"[TotalRows]": 100, "[LatestDate]": future_date_str}], duration_ms=35
    )

    validator = LatestDateValidator()
    rule = _make_rule(VALIDATION_TYPE_LATEST_DATE, col="ShipDate", config={"allow_future_dates": False})

    res = validator.validate(
        rule=rule,
        dax_client=client,
        workspace_id="ws1",
        dataset_id="ds1",
        context={"reference_timestamp": ref_time},
    )

    assert res.status == ValidationStatus.FAIL
    assert "Future date detected" in res.result_summary
    assert "future" in res.deviation


def test_format_hours_duration_under_and_over_48h():
    # Under 48 hours: stays as hours
    assert format_hours_duration(0.5) == "0.5h"
    assert format_hours_duration(2.0) == "2.0h"
    assert format_hours_duration(24.0) == "24.0h"
    assert format_hours_duration(47.9) == "47.9h"

    # 48 hours and above: converts to days and hours
    assert format_hours_duration(48.0) == "2d"
    assert format_hours_duration(48.5) == "2d 0.5h"
    assert format_hours_duration(49.0) == "2d 1h"
    assert format_hours_duration(72.0) == "3d"
    assert format_hours_duration(16160.0) == "673d 8h"
    assert format_hours_duration(16184.0) == "674d 8h"
    assert format_hours_duration(None) == "-"


def test_latest_date_validator_converts_exceeding_48h_to_days_and_hours():
    client = MagicMock(spec=DaxQueryClient)
    # 2026-11-21 07:59:40 UTC
    ref_time = datetime(2026, 11, 21, 7, 59, 40, tzinfo=timezone.utc)
    # Order Date: 2025-01-16 00:00:00 UTC (16,183.99 hours old = 674d 8h)
    latest_date_str = "2025-01-16T00:00:00Z"

    client.execute_raw_dax.return_value = DaxQueryResult.from_raw_rows(
        [{"[TotalRows]": 10000, "[LatestDate]": latest_date_str}], duration_ms=45
    )

    validator = LatestDateValidator()
    rule = _make_rule(VALIDATION_TYPE_LATEST_DATE, col="Order_Date", config={"max_age_hours": 24.0})

    res = validator.validate(
        rule=rule,
        dax_client=client,
        workspace_id="ws1",
        dataset_id="ds1",
        context={"reference_timestamp": ref_time},
    )

    assert res.status == ValidationStatus.FAIL
    assert "674d 8h ago" in res.actual_value
    assert "+673d 8h over limit" in res.deviation
    assert "674d 8h old" in res.result_summary
    assert "674d 8h" in res.detailed_message


# =========================================================================
# RowCountValidator Tests
# =========================================================================

def test_row_count_validator_passes_within_fixed_baseline():
    client = MagicMock(spec=DaxQueryClient)
    client.execute_raw_dax.return_value = DaxQueryResult.from_raw_rows([{"[RowCount]": 1020}], duration_ms=20)

    validator = RowCountValidator()
    rule = _make_rule(
        VALIDATION_TYPE_ROW_COUNT,
        config={"baseline_method": "fixed", "baseline_value": 1000, "allowed_deviation_pct": 5.0},
    )

    res = validator.validate(rule=rule, dax_client=client, workspace_id="ws1", dataset_id="ds1")

    assert res.status == ValidationStatus.PASS
    assert "1,020 rows" in res.actual_value
    assert "2.00% deviation" in res.deviation


def test_row_count_validator_fails_when_deviation_exceeded():
    client = MagicMock(spec=DaxQueryClient)
    client.execute_raw_dax.return_value = DaxQueryResult.from_raw_rows([{"[RowCount]": 800}], duration_ms=20)

    validator = RowCountValidator()
    rule = _make_rule(
        VALIDATION_TYPE_ROW_COUNT,
        config={"baseline_method": "fixed", "baseline_value": 1000, "allowed_deviation_pct": 5.0},
    )

    res = validator.validate(rule=rule, dax_client=client, workspace_id="ws1", dataset_id="ds1")

    assert res.status == ValidationStatus.FAIL
    assert "-200 (-20.00%)" in res.deviation


def test_row_count_validator_range_min_max():
    client = MagicMock(spec=DaxQueryClient)
    client.execute_raw_dax.return_value = DaxQueryResult.from_raw_rows([{"[RowCount]": 45}], duration_ms=20)

    validator = RowCountValidator()
    rule = _make_rule(
        VALIDATION_TYPE_ROW_COUNT,
        config={"baseline_method": "min_max", "min_count": 50, "max_count": 200},
    )

    res = validator.validate(rule=rule, dax_client=client, workspace_id="ws1", dataset_id="ds1")

    assert res.status == ValidationStatus.FAIL
    assert "-5 below minimum" in res.deviation


def test_row_count_validator_previous_run_from_context():
    client = MagicMock(spec=DaxQueryClient)
    client.execute_raw_dax.return_value = DaxQueryResult.from_raw_rows([{"[RowCount]": 505}], duration_ms=20)

    validator = RowCountValidator()
    rule = _make_rule(
        VALIDATION_TYPE_ROW_COUNT,
        config={"baseline_method": "previous_run", "allowed_deviation_pct": 5.0},
    )

    res = validator.validate(
        rule=rule,
        dax_client=client,
        workspace_id="ws1",
        dataset_id="ds1",
        context={"previous_row_count": 500},
    )

    assert res.status == ValidationStatus.PASS
    assert "previous run" in res.result_summary


# =========================================================================
# RefreshValidator Tests
# =========================================================================

def test_refresh_validator_integration():
    svc = MagicMock(spec=RefreshService)
    now = datetime(2026, 11, 19, 12, 0, 0, tzinfo=timezone.utc)
    rec = RefreshRecordDTO(
        id=1,
        workspace_registration_id=10,
        dataset_id="ds1",
        refresh_id="999",
        refresh_type="ViaApi",
        status=RefreshStatus.SUCCESS,
        start_time=now - timedelta(minutes=15),
        end_time=now - timedelta(minutes=10),
        duration_ms=300000,
        error_details=None,
        retrieved_at=now,
    )

    from app.services.refresh_service import RefreshCheckEvaluation
    svc.evaluate_refresh_rule.return_value = RefreshCheckEvaluation(
        status=ValidationStatus.PASS,
        actual_value="Status: Completed, Duration: 5m 0s, Age: 0.2h ago",
        expected_value="Status = Completed, Age <= 24h",
        deviation=None,
        result_summary="Latest refresh succeeded and meets freshness SLA.",
        detailed_message="Details...",
        refresh_record=rec,
    )

    validator = RefreshValidator()
    rule = _make_rule(VALIDATION_TYPE_REFRESH, tbl=None, col=None, config={"expected_status": "Completed"})

    res = validator.validate(
        rule=rule,
        dax_client=MagicMock(spec=DaxQueryClient),
        workspace_id="ws1",
        dataset_id="ds1",
        context={"refresh_service": svc},
    )

    assert res.status == ValidationStatus.PASS
    assert "Completed" in res.actual_value
    assert res.metadata_snapshot["refresh_id"] == "999"


# =========================================================================
# Factory Registry Tests
# =========================================================================

def test_factory_returns_expected_validators():
    assert isinstance(get_validator(VALIDATION_TYPE_NULL), NullValidator)
    assert isinstance(get_validator(VALIDATION_TYPE_DUPLICATE), DuplicateValidator)
    assert isinstance(get_validator(VALIDATION_TYPE_LATEST_DATE), LatestDateValidator)
    assert isinstance(get_validator(VALIDATION_TYPE_ROW_COUNT), RowCountValidator)
    assert isinstance(get_validator(VALIDATION_TYPE_REFRESH), RefreshValidator)


def test_factory_raises_for_unknown():
    with pytest.raises(ValueError, match="No validator registered"):
        get_validator("unknown_rule_type")
