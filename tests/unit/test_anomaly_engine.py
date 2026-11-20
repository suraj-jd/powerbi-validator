"""Unit tests for Stage 11 KPI baseline and historical anomaly detection engine."""

from __future__ import annotations

from datetime import datetime, timezone
import math
from unittest.mock import MagicMock

import pytest

from app.core.status import ValidationStatus
from app.integrations.powerbi.dax_client import DaxQueryClient, DaxQueryResult
from app.services.rule_service import (
    RuleRecord,
    TARGET_TYPE_MEASURE,
    VALIDATION_TYPE_ANOMALY,
    VALIDATION_TYPE_DAX_MEASURE,
)
from app.validation.stats import (
    compute_percentage_deviation,
    compute_sample_stats,
    compute_z_score,
    filter_weekend_observations,
)
from app.validation.validator_factory import get_validator
from app.validation.validators.anomaly_validator import AnomalyValidator
from app.validation.validators.dax_measure_validator import DaxMeasureValidator


# =========================================================================
# Statistics Utilities Tests
# =========================================================================

def test_compute_sample_stats_calculations():
    # Known dataset: [10, 20, 30, 40, 50]
    # Mean = 30, Median = 30, Stdev = 15.8114
    stats = compute_sample_stats([10, 20, 30, 40, 50])
    assert stats.sample_count == 5
    assert stats.mean == 30.0
    assert stats.median == 30.0
    assert math.isclose(stats.stdev, 15.8114, abs_tol=1e-3)
    assert stats.min_val == 10.0
    assert stats.max_val == 50.0


def test_compute_sample_stats_empty_raises():
    with pytest.raises(ValueError, match="empty collection"):
        compute_sample_stats([])


def test_compute_z_score():
    # Mean = 100, Stdev = 10
    assert compute_z_score(120, 100, 10) == 2.0
    assert compute_z_score(85, 100, 10) == -1.5
    # Zero stdev handling
    assert compute_z_score(100, 100, 0.0) == 0.0
    assert compute_z_score(110, 100, 0.0) == 999.0


def test_compute_percentage_deviation_zero_and_negative_baselines():
    # Standard
    diff, pct = compute_percentage_deviation(105, 100)
    assert diff == 5.0
    assert pct == 5.0

    # Negative baseline: baseline = -100, actual = -110 -> 10% deviation
    diff, pct = compute_percentage_deviation(-110, -100)
    assert diff == -10.0
    assert pct == 10.0

    # Both zero -> 0% deviation, no error
    diff, pct = compute_percentage_deviation(0, 0)
    assert diff == 0.0
    assert pct == 0.0

    # Zero baseline, positive actual -> safe 100% without division by zero
    diff, pct = compute_percentage_deviation(50, 0)
    assert diff == 50.0
    assert pct == 100.0


def test_filter_weekend_observations():
    # 2026-11-20 is Friday (weekday 4)
    # 2026-11-21 is Saturday (weekday 5)
    # 2026-11-22 is Sunday (weekday 6)
    # 2026-11-23 is Monday (weekday 0)
    points = [
        (datetime(2026, 11, 20, 10, 0, tzinfo=timezone.utc), 100.0),
        (datetime(2026, 11, 21, 10, 0, tzinfo=timezone.utc), 110.0),
        (datetime(2026, 11, 22, 10, 0, tzinfo=timezone.utc), 120.0),
        (datetime(2026, 11, 23, 10, 0, tzinfo=timezone.utc), 130.0),
    ]
    filtered = filter_weekend_observations(points)
    assert len(filtered) == 2
    assert filtered[0][1] == 100.0
    assert filtered[1][1] == 130.0


# =========================================================================
# DaxMeasureValidator Tests
# =========================================================================

def _make_measure_rule(config: dict | None = None) -> RuleRecord:
    return RuleRecord(
        id=20,
        workspace_registration_id=1,
        rule_name="Total Sales KPI",
        enabled=True,
        target_type=TARGET_TYPE_MEASURE,
        table_name=None,
        column_name=None,
        measure_name="Total Sales",
        validation_type=VALIDATION_TYPE_DAX_MEASURE,
        config=config or {},
        display_order=1,
    )


def test_dax_measure_fixed_baseline_passes():
    client = MagicMock(spec=DaxQueryClient)
    client.execute_raw_dax.return_value = DaxQueryResult.from_raw_rows([{"[Value]": 1025.0}], duration_ms=25)

    validator = DaxMeasureValidator()
    rule = _make_measure_rule({"expected_value": 1000.0, "allowed_deviation_pct": 5.0})

    res = validator.validate(rule=rule, dax_client=client, workspace_id="ws1", dataset_id="ds1")

    assert res.status == ValidationStatus.PASS
    assert "1,025" in res.actual_value
    assert "2.50% deviation" in res.deviation


def test_dax_measure_executes_with_filters():
    client = MagicMock(spec=DaxQueryClient)
    client.execute_raw_dax.return_value = DaxQueryResult.from_raw_rows([{"[Value]": 500.0}], duration_ms=25)

    validator = DaxMeasureValidator()
    rule = _make_measure_rule({
        "expected_value": 500.0,
        "filter_1": "'Dates'[Year] = 2024",
        "filter_2": "'Region'[Country] = \"US\"",
        "filter_3": "'Product'[Category] = \"Bikes\"",
    })

    res = validator.validate(rule=rule, dax_client=client, workspace_id="ws1", dataset_id="ds1")
    assert res.status == ValidationStatus.PASS
    executed_query = client.execute_raw_dax.call_args[0][2]
    assert "CALCULATE(" in executed_query
    assert "'Dates'[Year] = 2024" in executed_query
    assert "'Region'[Country] = \"US\"" in executed_query
    assert "'Product'[Category] = \"Bikes\"" in executed_query


def test_dax_measure_fixed_baseline_fails_deviation():
    client = MagicMock(spec=DaxQueryClient)
    client.execute_raw_dax.return_value = DaxQueryResult.from_raw_rows([{"[Value]": 1200.0}], duration_ms=25)

    validator = DaxMeasureValidator()
    rule = _make_measure_rule({"expected_value": 1000.0, "allowed_deviation_pct": 5.0})

    res = validator.validate(rule=rule, dax_client=client, workspace_id="ws1", dataset_id="ds1")

    assert res.status == ValidationStatus.FAIL
    assert "+200.00 (+20.00%)" in res.deviation
    assert "exceeds allowed ±5.0%" in res.result_summary


def test_dax_measure_min_max_bounds():
    client = MagicMock(spec=DaxQueryClient)
    client.execute_raw_dax.return_value = DaxQueryResult.from_raw_rows([{"[Value]": 450.0}], duration_ms=25)

    validator = DaxMeasureValidator()
    rule = _make_measure_rule({"expected_method": "min_max", "min_value": 500.0, "max_value": 1500.0})

    res = validator.validate(rule=rule, dax_client=client, workspace_id="ws1", dataset_id="ds1")

    assert res.status == ValidationStatus.FAIL
    assert "-50.00 below min" in res.deviation


def test_dax_measure_blank_fails():
    client = MagicMock(spec=DaxQueryClient)
    client.execute_raw_dax.return_value = DaxQueryResult.from_raw_rows([{"[Value]": None}], duration_ms=20)

    validator = DaxMeasureValidator()
    rule = _make_measure_rule({"expected_value": 100.0})

    res = validator.validate(rule=rule, dax_client=client, workspace_id="ws1", dataset_id="ds1")

    assert res.status == ValidationStatus.FAIL
    assert res.actual_value == "BLANK()"


# =========================================================================
# AnomalyValidator Tests
# =========================================================================

def _make_anomaly_rule(config: dict | None = None) -> RuleRecord:
    return RuleRecord(
        id=30,
        workspace_registration_id=1,
        rule_name="Daily Revenue Anomaly Check",
        enabled=True,
        target_type=TARGET_TYPE_MEASURE,
        table_name=None,
        column_name=None,
        measure_name="Daily Revenue",
        validation_type=VALIDATION_TYPE_ANOMALY,
        config=config or {},
        display_order=1,
    )


def test_anomaly_validator_detects_zscore_outlier():
    client = MagicMock(spec=DaxQueryClient)
    # Actual value: 250 (outlier vs historical distribution of mean ~100, stdev ~10)
    client.execute_raw_dax.return_value = DaxQueryResult.from_raw_rows([{"[Value]": 250.0}], duration_ms=30)

    # 10 historical days around 100
    history = [98.0, 102.0, 101.0, 99.0, 100.0, 104.0, 97.0, 103.0, 99.0, 101.0]

    validator = AnomalyValidator()
    rule = _make_anomaly_rule({
        "comparison_method": "z_score",
        "z_score_threshold": 3.0,
        "min_samples": 5,
    })

    res = validator.validate(
        rule=rule,
        dax_client=client,
        workspace_id="ws1",
        dataset_id="ds1",
        context={"historical_points": history},
    )

    assert res.status == ValidationStatus.FAIL
    assert "Anomaly detected" in res.result_summary
    assert "Z=" in res.deviation


def test_anomaly_validator_passes_normal_observation():
    client = MagicMock(spec=DaxQueryClient)
    client.execute_raw_dax.return_value = DaxQueryResult.from_raw_rows([{"[Value]": 102.0}], duration_ms=30)

    history = [98.0, 102.0, 101.0, 99.0, 100.0, 104.0, 97.0, 103.0, 99.0, 101.0]

    validator = AnomalyValidator()
    rule = _make_anomaly_rule({
        "comparison_method": "z_score",
        "z_score_threshold": 3.0,
        "min_samples": 5,
    })

    res = validator.validate(
        rule=rule,
        dax_client=client,
        workspace_id="ws1",
        dataset_id="ds1",
        context={"historical_points": history},
    )

    assert res.status == ValidationStatus.PASS
    assert "passed" in res.result_summary.lower()


def test_anomaly_validator_insufficient_history_warning():
    client = MagicMock(spec=DaxQueryClient)
    client.execute_raw_dax.return_value = DaxQueryResult.from_raw_rows([{"[Value]": 100.0}], duration_ms=20)

    # Only 2 points, but min_samples is 5
    history = [98.0, 102.0]

    validator = AnomalyValidator()
    rule = _make_anomaly_rule({
        "min_samples": 5,
        "insufficient_history_action": "warning",
    })

    res = validator.validate(
        rule=rule,
        dax_client=client,
        workspace_id="ws1",
        dataset_id="ds1",
        context={"historical_points": history},
    )

    assert res.status == ValidationStatus.WARNING
    assert "Insufficient history: Found 2 observations" in res.result_summary


def test_anomaly_validator_direction_filter():
    client = MagicMock(spec=DaxQueryClient)
    # Actual value: 50 (sharp drop). If direction is 'increase' only, drops should NOT alert!
    client.execute_raw_dax.return_value = DaxQueryResult.from_raw_rows([{"[Value]": 50.0}], duration_ms=30)

    history = [100.0, 101.0, 99.0, 100.0, 102.0, 98.0]

    validator = AnomalyValidator()
    rule = _make_anomaly_rule({
        "comparison_method": "z_score",
        "z_score_threshold": 2.0,
        "direction": "increase",
        "min_samples": 5,
    })

    res = validator.validate(
        rule=rule,
        dax_client=client,
        workspace_id="ws1",
        dataset_id="ds1",
        context={"historical_points": history},
    )

    assert res.status == ValidationStatus.PASS  # Ignored because direction is increase only


def test_factory_registry_stage_11():
    assert isinstance(get_validator(VALIDATION_TYPE_DAX_MEASURE), DaxMeasureValidator)
    assert isinstance(get_validator(VALIDATION_TYPE_ANOMALY), AnomalyValidator)


def test_anomaly_validator_fast_fail_min_baseline():
    """If actual value is below configured min baseline (e.g. 900 < 1000), immediately fail as anomaly."""
    client = MagicMock(spec=DaxQueryClient)
    client.execute_raw_dax.return_value = DaxQueryResult.from_raw_rows([{"[Value]": 900.0}], duration_ms=25)

    validator = AnomalyValidator()
    rule = _make_anomaly_rule({
        "min_baseline": 1000.0,
        "comparison_method": "z_score",
        "min_samples": 5,
    })

    # Even with no historical points or z-score, it fails immediately on min baseline
    res = validator.validate(
        rule=rule,
        dax_client=client,
        workspace_id="ws1",
        dataset_id="ds1",
        context={},
    )

    assert res.status == ValidationStatus.FAIL
    assert "below minimum baseline" in res.result_summary.lower()
    assert res.actual_value == "900.00"
    assert ">= 1,000.00" in res.expected_value


def test_anomaly_validator_fast_fail_max_baseline():
    """If actual value exceeds configured max baseline ceiling (e.g. 6200 > 5000), immediately fail as anomaly."""
    client = MagicMock(spec=DaxQueryClient)
    client.execute_raw_dax.return_value = DaxQueryResult.from_raw_rows([{"[Value]": 6200.0}], duration_ms=25)

    validator = AnomalyValidator()
    rule = _make_anomaly_rule({
        "max_baseline": 5000.0,
        "comparison_method": "threshold_only",
    })

    res = validator.validate(
        rule=rule,
        dax_client=client,
        workspace_id="ws1",
        dataset_id="ds1",
        context={},
    )

    assert res.status == ValidationStatus.FAIL
    assert "exceeds maximum baseline" in res.result_summary.lower()
    assert res.actual_value == "6,200.00"
    assert "<= 5,000.00" in res.expected_value


def test_anomaly_validator_threshold_only_passes_within_bounds():
    """Values within [min, max] pass cleanly in threshold_only mode."""
    client = MagicMock(spec=DaxQueryClient)
    client.execute_raw_dax.return_value = DaxQueryResult.from_raw_rows([{"[Value]": 2500.0}], duration_ms=25)

    validator = AnomalyValidator()
    rule = _make_anomaly_rule({
        "min_baseline": 1000.0,
        "max_baseline": 5000.0,
        "comparison_method": "threshold_only",
    })

    res = validator.validate(
        rule=rule,
        dax_client=client,
        workspace_id="ws1",
        dataset_id="ds1",
        context={},
    )

    assert res.status == ValidationStatus.PASS
    assert "satisfies baseline thresholds" in res.result_summary.lower()


def test_anomaly_validator_fixed_baseline_percentage_mode():
    """Test fixed baseline ± % deviation check without requiring history."""
    client = MagicMock(spec=DaxQueryClient)
    # Expected: 1000, Allowed ± 10% (900 to 1100). Actual: 950 -> PASS
    client.execute_raw_dax.return_value = DaxQueryResult.from_raw_rows([{"[Value]": 950.0}], duration_ms=25)

    validator = AnomalyValidator()
    rule = _make_anomaly_rule({
        "comparison_method": "percentage",
        "baseline_value": 1000.0,
        "allowed_deviation_pct": 10.0,
    })

    res = validator.validate(
        rule=rule,
        dax_client=client,
        workspace_id="ws1",
        dataset_id="ds1",
        context={},
    )
    assert res.status == ValidationStatus.PASS
    assert "within ±10.0% of baseline" in res.result_summary.lower()

    # Outlier: 1200 (> 10% deviation) -> FAIL
    client.execute_raw_dax.return_value = DaxQueryResult.from_raw_rows([{"[Value]": 1200.0}], duration_ms=25)
    res_fail = validator.validate(
        rule=rule,
        dax_client=client,
        workspace_id="ws1",
        dataset_id="ds1",
        context={},
    )
    assert res_fail.status == ValidationStatus.FAIL
    assert "deviates by 20.0%" in res_fail.result_summary.lower()


def test_anomaly_validator_previous_run_mode():
    """Test run-over-run ± % deviation check."""
    client = MagicMock(spec=DaxQueryClient)
    client.execute_raw_dax.return_value = DaxQueryResult.from_raw_rows([{"[Value]": 105.0}], duration_ms=25)

    validator = AnomalyValidator()
    rule = _make_anomaly_rule({
        "comparison_method": "previous_run",
        "allowed_deviation_pct": 10.0,
    })

    # Previous run was 100.0; 105.0 is +5% change (<= 10%) -> PASS
    res = validator.validate(
        rule=rule,
        dax_client=client,
        workspace_id="ws1",
        dataset_id="ds1",
        context={"historical_points": [100.0]},
    )
    assert res.status == ValidationStatus.PASS
    assert "within ±10.0% of previous run" in res.result_summary.lower()

    # If change is 130.0 vs 100.0 (+30% change) -> FAIL
    client.execute_raw_dax.return_value = DaxQueryResult.from_raw_rows([{"[Value]": 130.0}], duration_ms=25)
    res_fail = validator.validate(
        rule=rule,
        dax_client=client,
        workspace_id="ws1",
        dataset_id="ds1",
        context={"historical_points": [100.0]},
    )
    assert res_fail.status == ValidationStatus.FAIL
    assert "changed by 30.0% vs previous run" in res_fail.result_summary.lower()


def test_anomaly_validator_graceful_insufficient_history_when_baseline_met():
    """If history < min_samples but user set a baseline floor that passed, return PASS instead of WARNING."""
    client = MagicMock(spec=DaxQueryClient)
    client.execute_raw_dax.return_value = DaxQueryResult.from_raw_rows([{"[Value]": 1500.0}], duration_ms=25)

    validator = AnomalyValidator()
    rule = _make_anomaly_rule({
        "min_baseline": 1000.0,
        "comparison_method": "z_score",
        "min_samples": 5,
    })

    # Only 1 sample in history (< 5 required), but 1500 >= 1000 floor
    res = validator.validate(
        rule=rule,
        dax_client=client,
        workspace_id="ws1",
        dataset_id="ds1",
        context={"historical_points": [1400.0]},
    )
    assert res.status == ValidationStatus.PASS
    assert "satisfies baseline limits" in res.result_summary.lower()

