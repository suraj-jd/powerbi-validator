"""Historical anomaly detection validator using Z-score, mean, median, and lookback windows (Stage 11B)."""

from __future__ import annotations

from datetime import datetime, timezone
import logging
from typing import Any, Sequence

from app.core.status import ValidationStatus
from app.database.models import utc_now
from app.integrations.powerbi.dax_client import (
    DaxQueryClient,
    build_measure_query,
    build_table_expression,
    escape_column_reference,
    escape_measure_name,
    escape_table_name,
    extract_rule_filters,
)
from app.services.rule_service import RuleRecord, TARGET_TYPE_MEASURE
from app.validation.base import BaseValidator
from app.validation.models import CheckEvaluationResult
from app.validation.stats import (
    compute_percentage_deviation,
    compute_sample_stats,
    compute_z_score,
    filter_weekend_observations,
)

logger = logging.getLogger(__name__)


class AnomalyValidator(BaseValidator):
    """Detects metric anomalies by comparing current observations against historical statistical baselines (BRD 5.3 F)."""

    def validate(
        self,
        *,
        rule: RuleRecord,
        dax_client: DaxQueryClient,
        workspace_id: str,
        dataset_id: str,
        context: dict[str, Any] | None = None,
    ) -> CheckEvaluationResult:
        t_start = utc_now()
        cfg = rule.config or {}

        # 1. Build and execute DAX query for current value
        if rule.target_type == TARGET_TYPE_MEASURE or rule.measure_name:
            if not rule.measure_name or not rule.measure_name.strip():
                return CheckEvaluationResult.create_error(
                    rule_id=rule.id,
                    rule_name=rule.rule_name,
                    validation_type=rule.validation_type,
                    target_type=rule.target_type,
                    error_message="Anomaly check on measure requires a Measure Name.",
                    started_at=t_start,
                )
            target_name = escape_measure_name(rule.measure_name)
            filters = extract_rule_filters(cfg)
            query = build_measure_query(target_name, filters=filters)
        else:
            if not rule.table_name or not rule.column_name:
                return CheckEvaluationResult.create_error(
                    rule_id=rule.id,
                    rule_name=rule.rule_name,
                    validation_type=rule.validation_type,
                    target_type=rule.target_type,
                    error_message="Anomaly check on column requires Table Name and Column Name.",
                    started_at=t_start,
                )
            agg = str(cfg.get("aggregation_func", "SUM")).strip().upper()
            tbl_name = escape_table_name(rule.table_name)
            col_ref = escape_column_reference(rule.column_name, rule.table_name)
            filters = extract_rule_filters(cfg)
            table_expr = build_table_expression(rule.table_name, filters)
            target_name = f"{agg}({col_ref})"
            query = f'EVALUATE ROW("Value", {agg}X({table_expr}, {col_ref}))' if agg in ("SUM", "AVERAGE", "MIN", "MAX") else f'EVALUATE ROW("Value", {agg}({col_ref}))'

        dax_res = dax_client.execute_raw_dax(workspace_id, dataset_id, query)
        now = utc_now()
        duration_ms = dax_res.duration_ms

        if not dax_res.is_success:
            return CheckEvaluationResult.create_error(
                rule_id=rule.id,
                rule_name=rule.rule_name,
                validation_type=rule.validation_type,
                target_type=rule.target_type,
                error_message=f"DAX query failed: {dax_res.error_message}",
                started_at=t_start,
                duration_ms=duration_ms,
            )

        if dax_res.is_blank or dax_res.scalar_value is None:
            return CheckEvaluationResult(
                rule_id=rule.id,
                rule_name=rule.rule_name,
                validation_type=rule.validation_type,
                target_type=rule.target_type,
                status=ValidationStatus.WARNING,
                actual_value="BLANK()",
                expected_value="Historical baseline",
                deviation=None,
                result_summary=f"Anomaly check for {target_name} returned BLANK().",
                detailed_message=f"Query executed:\n{query}",
                started_at=t_start,
                completed_at=now,
                duration_ms=duration_ms,
            )

        try:
            actual_val = float(dax_res.scalar_value)
        except (ValueError, TypeError):
            return CheckEvaluationResult.create_error(
                rule_id=rule.id,
                rule_name=rule.rule_name,
                validation_type=rule.validation_type,
                target_type=rule.target_type,
                error_message=f"Anomaly check requires a numeric value, but received: '{dax_res.scalar_value}'",
                started_at=t_start,
                duration_ms=duration_ms,
            )

        actual_display = f"{actual_val:,.2f}" if abs(actual_val) >= 0.01 or actual_val == 0.0 else f"{actual_val:.4f}"

        # 1b. Fast-fail Baseline Floor & Ceiling Checks (Immediate Anomaly)
        min_baseline = cfg.get("min_baseline")
        if min_baseline is None:
            min_baseline = cfg.get("min_value")
        max_baseline = cfg.get("max_baseline")
        if max_baseline is None:
            max_baseline = cfg.get("max_value")

        has_min = min_baseline is not None and str(min_baseline).strip() != ""
        has_max = max_baseline is not None and str(max_baseline).strip() != ""

        if has_min and actual_val < float(min_baseline):
            min_b = float(min_baseline)
            diff = actual_val - min_b
            pct = (diff / abs(min_b) * 100.0) if min_b != 0 else 0.0
            return CheckEvaluationResult(
                rule_id=rule.id,
                rule_name=rule.rule_name,
                validation_type=rule.validation_type,
                target_type=rule.target_type,
                status=ValidationStatus.FAIL,
                actual_value=actual_display,
                expected_value=f">= {min_b:,.2f}",
                deviation=f"{diff:+,.2f} ({pct:+.1f}%) below min baseline",
                result_summary=f"Anomaly detected in {target_name}: {actual_display} is below minimum baseline threshold ({min_b:,.2f}).",
                detailed_message=(
                    f"Target: {target_name}\n"
                    f"Actual Observed Value: {actual_display}\n"
                    f"Minimum Baseline Threshold: {min_b:,.2f}\n"
                    f"Deficit: {abs(diff):,.2f} ({abs(pct):.1f}%)\n"
                    f"Evaluation: FAIL (Baseline Floor Violated — Immediate Anomaly)"
                ),
                started_at=t_start,
                completed_at=now,
                duration_ms=duration_ms,
                metadata_snapshot={
                    "actual_value": actual_val,
                    "min_baseline": min_b,
                    "deficit": diff,
                },
            )

        if has_max and actual_val > float(max_baseline):
            max_b = float(max_baseline)
            diff = actual_val - max_b
            pct = (diff / abs(max_b) * 100.0) if max_b != 0 else 0.0
            return CheckEvaluationResult(
                rule_id=rule.id,
                rule_name=rule.rule_name,
                validation_type=rule.validation_type,
                target_type=rule.target_type,
                status=ValidationStatus.FAIL,
                actual_value=actual_display,
                expected_value=f"<= {max_b:,.2f}",
                deviation=f"{diff:+,.2f} ({pct:+.1f}%) above max baseline",
                result_summary=f"Anomaly detected in {target_name}: {actual_display} exceeds maximum baseline threshold ({max_b:,.2f}).",
                detailed_message=(
                    f"Target: {target_name}\n"
                    f"Actual Observed Value: {actual_display}\n"
                    f"Maximum Baseline Threshold: {max_b:,.2f}\n"
                    f"Excess: {abs(diff):,.2f} ({abs(pct):.1f}%)\n"
                    f"Evaluation: FAIL (Baseline Ceiling Violated — Immediate Anomaly)"
                ),
                started_at=t_start,
                completed_at=now,
                duration_ms=duration_ms,
                metadata_snapshot={
                    "actual_value": actual_val,
                    "max_baseline": max_b,
                    "excess": diff,
                },
            )

        comparison_method = str(cfg.get("comparison_method", "z_score")).strip().lower()

        # 1c. Baseline Thresholds Only Mode (No statistical comparison needed)
        if comparison_method in ("threshold_only", "baseline_only", "none"):
            exp_parts = []
            if has_min:
                exp_parts.append(f">= {float(min_baseline):,.2f}")
            if has_max:
                exp_parts.append(f"<= {float(max_baseline):,.2f}")
            exp_str = " and ".join(exp_parts) if exp_parts else "Baseline satisfied"
            return CheckEvaluationResult(
                rule_id=rule.id,
                rule_name=rule.rule_name,
                validation_type=rule.validation_type,
                target_type=rule.target_type,
                status=ValidationStatus.PASS,
                actual_value=actual_display,
                expected_value=exp_str,
                deviation="Normal",
                result_summary=f"Anomaly check passed for {target_name}: {actual_display} satisfies baseline thresholds ({exp_str}).",
                detailed_message=(
                    f"Target: {target_name}\n"
                    f"Actual Observed Value: {actual_display}\n"
                    f"Configured Thresholds: {exp_str}\n"
                    f"Evaluation: PASS (Within Baseline Bounds)"
                ),
                started_at=t_start,
                completed_at=now,
                duration_ms=duration_ms,
                metadata_snapshot={
                    "actual_value": actual_val,
                    "min_baseline": min_baseline,
                    "max_baseline": max_baseline,
                },
            )

        # 1d. Fixed Baseline ± % Deviation Mode (No historical points needed)
        if comparison_method in ("percentage", "fixed_baseline"):
            baseline_val = float(cfg.get("baseline_value", 0.0))
            allowed_dev_pct = float(cfg.get("allowed_deviation_pct", 10.0))
            direction = str(cfg.get("direction", "both")).strip().lower()
            diff, pct_dev = compute_percentage_deviation(actual_val, baseline_val)
            expected_str = f"Baseline {baseline_val:,.2f} (±{allowed_dev_pct:.1f}%)"

            if direction == "increase" and diff < 0:
                is_anomaly = False
            elif direction == "decrease" and diff > 0:
                is_anomaly = False
            else:
                is_anomaly = pct_dev > allowed_dev_pct

            diff_sign = "+" if diff > 0 else ""
            dev_display = f"{diff_sign}{diff:,.2f} ({diff_sign}{pct_dev:.2f}%) from baseline"

            if is_anomaly:
                return CheckEvaluationResult(
                    rule_id=rule.id,
                    rule_name=rule.rule_name,
                    validation_type=rule.validation_type,
                    target_type=rule.target_type,
                    status=ValidationStatus.FAIL,
                    actual_value=actual_display,
                    expected_value=expected_str,
                    deviation=dev_display,
                    result_summary=f"Anomaly detected in {target_name}: {actual_display} deviates by {pct_dev:.1f}% from baseline {baseline_val:,.2f} (allowed ±{allowed_dev_pct:.1f}%).",
                    detailed_message=(
                        f"Target: {target_name}\n"
                        f"Actual Observed Value: {actual_display}\n"
                        f"Fixed Baseline: {baseline_val:,.2f}\n"
                        f"Allowed Deviation: ±{allowed_dev_pct:.1f}%\n"
                        f"Observed Deviation: {dev_display}\n"
                        f"Evaluation: FAIL (Baseline Deviation Exceeded)"
                    ),
                    started_at=t_start,
                    completed_at=now,
                    duration_ms=duration_ms,
                    metadata_snapshot={
                        "actual_value": actual_val,
                        "baseline_value": baseline_val,
                        "percentage_deviation": pct_dev,
                        "allowed_deviation_pct": allowed_dev_pct,
                    },
                )
            return CheckEvaluationResult(
                rule_id=rule.id,
                rule_name=rule.rule_name,
                validation_type=rule.validation_type,
                target_type=rule.target_type,
                status=ValidationStatus.PASS,
                actual_value=actual_display,
                expected_value=expected_str,
                deviation=f"Normal ({dev_display})",
                result_summary=f"Anomaly check passed for {target_name}: {actual_display} is within ±{allowed_dev_pct:.1f}% of baseline {baseline_val:,.2f}.",
                detailed_message=(
                    f"Target: {target_name}\n"
                    f"Actual Observed Value: {actual_display}\n"
                    f"Fixed Baseline: {baseline_val:,.2f}\n"
                    f"Allowed Deviation: ±{allowed_dev_pct:.1f}%\n"
                    f"Observed Deviation: {dev_display}\n"
                    f"Evaluation: PASS (Within Baseline Tolerance)"
                ),
                started_at=t_start,
                completed_at=now,
                duration_ms=duration_ms,
                metadata_snapshot={
                    "actual_value": actual_val,
                    "baseline_value": baseline_val,
                    "percentage_deviation": pct_dev,
                },
            )

        # 2. Retrieve and process historical observation points
        lookback_days = int(cfg.get("lookback_days", 30))
        ignore_weekends = bool(cfg.get("ignore_weekends", False))
        min_samples = int(cfg.get("min_samples", 3))
        insufficient_action = str(cfg.get("insufficient_history_action", "warning")).strip().lower()

        raw_points = context.get("historical_points") if context else None
        clean_values: list[float] = []

        if raw_points:
            # Points can be list of (datetime, float) or list of float
            if isinstance(raw_points[0], tuple):
                typed_points: list[tuple[datetime, float]] = list(raw_points)  # type: ignore[arg-type]
                if ignore_weekends:
                    typed_points = filter_weekend_observations(typed_points)
                clean_values = [float(p[1]) for p in typed_points]
            else:
                clean_values = [float(p) for p in raw_points]

        # 2b. Previous Run ± % Change Mode
        if comparison_method in ("previous_run", "previous_period"):
            allowed_dev_pct = float(cfg.get("allowed_deviation_pct", 10.0))
            direction = str(cfg.get("direction", "both")).strip().lower()

            if not clean_values:
                # First run establishing baseline
                return CheckEvaluationResult(
                    rule_id=rule.id,
                    rule_name=rule.rule_name,
                    validation_type=rule.validation_type,
                    target_type=rule.target_type,
                    status=ValidationStatus.PASS,
                    actual_value=actual_display,
                    expected_value=f"Initial run recorded (±{allowed_dev_pct:.1f}%)",
                    deviation="Baseline established",
                    result_summary=f"Initial baseline recorded: {actual_display} (subsequent runs compared within ±{allowed_dev_pct:.1f}%).",
                    detailed_message=(
                        f"Target: {target_name}\n"
                        f"First run for this rule: initial baseline established at {actual_display}.\n"
                        f"Subsequent runs will verify changes remain within ±{allowed_dev_pct:.1f}%."
                    ),
                    started_at=t_start,
                    completed_at=now,
                    duration_ms=duration_ms,
                    metadata_snapshot={"actual_value": actual_val, "baseline_value": actual_val},
                )

            prev_val = clean_values[-1]
            diff, pct_dev = compute_percentage_deviation(actual_val, prev_val)
            expected_str = f"Previous {prev_val:,.2f} (±{allowed_dev_pct:.1f}%)"

            if direction == "increase" and diff < 0:
                is_anomaly = False
            elif direction == "decrease" and diff > 0:
                is_anomaly = False
            else:
                is_anomaly = pct_dev > allowed_dev_pct

            diff_sign = "+" if diff > 0 else ""
            dev_display = f"{diff_sign}{diff:,.2f} ({diff_sign}{pct_dev:.2f}%) from previous run"

            if is_anomaly:
                return CheckEvaluationResult(
                    rule_id=rule.id,
                    rule_name=rule.rule_name,
                    validation_type=rule.validation_type,
                    target_type=rule.target_type,
                    status=ValidationStatus.FAIL,
                    actual_value=actual_display,
                    expected_value=expected_str,
                    deviation=dev_display,
                    result_summary=f"Anomaly detected in {target_name}: {actual_display} changed by {pct_dev:.1f}% vs previous run ({prev_val:,.2f}, allowed ±{allowed_dev_pct:.1f}%).",
                    detailed_message=(
                        f"Target: {target_name}\n"
                        f"Actual Value: {actual_display}\n"
                        f"Previous Run Value: {prev_val:,.2f}\n"
                        f"Allowed Change: ±{allowed_dev_pct:.1f}%\n"
                        f"Observed Change: {dev_display}\n"
                        f"Evaluation: FAIL (Run-over-Run Anomaly)"
                    ),
                    started_at=t_start,
                    completed_at=now,
                    duration_ms=duration_ms,
                    metadata_snapshot={
                        "actual_value": actual_val,
                        "previous_value": prev_val,
                        "percentage_deviation": pct_dev,
                    },
                )
            return CheckEvaluationResult(
                rule_id=rule.id,
                rule_name=rule.rule_name,
                validation_type=rule.validation_type,
                target_type=rule.target_type,
                status=ValidationStatus.PASS,
                actual_value=actual_display,
                expected_value=expected_str,
                deviation=f"Normal ({dev_display})",
                result_summary=f"Anomaly check passed for {target_name}: {actual_display} within ±{allowed_dev_pct:.1f}% of previous run.",
                detailed_message=(
                    f"Target: {target_name}\n"
                    f"Actual Value: {actual_display}\n"
                    f"Previous Run Value: {prev_val:,.2f}\n"
                    f"Allowed Change: ±{allowed_dev_pct:.1f}%\n"
                    f"Observed Change: {dev_display}\n"
                    f"Evaluation: PASS (Normal Run-over-Run Variance)"
                ),
                started_at=t_start,
                completed_at=now,
                duration_ms=duration_ms,
                metadata_snapshot={
                    "actual_value": actual_val,
                    "previous_value": prev_val,
                    "percentage_deviation": pct_dev,
                },
            )

        # 3. Check sample count vs min_samples requirement for Median / Z-Score
        if len(clean_values) < min_samples:
            if has_min or has_max:
                # User configured a floor/ceiling baseline and it passed!
                return CheckEvaluationResult(
                    rule_id=rule.id,
                    rule_name=rule.rule_name,
                    validation_type=rule.validation_type,
                    target_type=rule.target_type,
                    status=ValidationStatus.PASS,
                    actual_value=actual_display,
                    expected_value=f"Baseline satisfied (gathering history: {len(clean_values)}/{min_samples})",
                    deviation="Baseline satisfied",
                    result_summary=f"Anomaly check passed for {target_name}: {actual_display} satisfies baseline limits (history accumulating: {len(clean_values)}/{min_samples} samples).",
                    detailed_message=(
                        f"Target: {target_name}\n"
                        f"Actual Observed Value: {actual_display}\n"
                        f"Baseline Limits: Passed floor/ceiling check.\n"
                        f"Historical Observations Found: {len(clean_values)} of {min_samples} required for {comparison_method}.\n"
                        f"Evaluation: PASS (Baseline Satisfied)"
                    ),
                    started_at=t_start,
                    completed_at=now,
                    duration_ms=duration_ms,
                    metadata_snapshot={
                        "actual_value": actual_val,
                        "sample_count": len(clean_values),
                        "min_samples": min_samples,
                    },
                )

            status = ValidationStatus.ERROR if insufficient_action == "error" else ValidationStatus.WARNING
            msg = f"Insufficient history: Found {len(clean_values)} observations (minimum required is {min_samples})."
            return CheckEvaluationResult(
                rule_id=rule.id,
                rule_name=rule.rule_name,
                validation_type=rule.validation_type,
                target_type=rule.target_type,
                status=status,
                actual_value=actual_display,
                expected_value=f">= {min_samples} historical observations ({lookback_days}d)",
                deviation="Insufficient history",
                result_summary=msg,
                detailed_message=(
                    f"Target: {target_name}\n"
                    f"Actual Observed Value: {actual_display}\n"
                    f"Historical Samples Found: {len(clean_values)}\n"
                    f"Minimum Samples Required: {min_samples}\n"
                    f"Lookback Window: {lookback_days} days\n"
                    f"Action Configured: {status.value}"
                ),
                started_at=t_start,
                completed_at=now,
                duration_ms=duration_ms,
                metadata_snapshot={
                    "actual_value": actual_val,
                    "sample_count": len(clean_values),
                    "min_samples": min_samples,
                },
            )

        # 4. Statistical comparison
        stats = compute_sample_stats(clean_values)
        comparison_method = str(cfg.get("comparison_method", "z_score")).strip().lower()
        z_threshold = float(cfg.get("z_score_threshold", 2.5))
        allowed_dev_pct = float(cfg.get("allowed_deviation_pct", 10.0))
        direction = str(cfg.get("direction", "both")).strip().lower()

        if comparison_method == "z_score":
            z = compute_z_score(actual_val, stats.mean, stats.stdev)
            expected_str = f"Mean {stats.mean:,.2f} (Z <= ±{z_threshold:.1f}σ, σ={stats.stdev:,.2f})"

            if direction == "increase" and z < 0:
                is_anomaly = False
            elif direction == "decrease" and z > 0:
                is_anomaly = False
            else:
                is_anomaly = abs(z) > z_threshold

            dev_display = f"Z={z:+.2f}σ ({abs(z):.2f} std dev from mean)"
            baseline_val = stats.mean

        elif comparison_method == "median":
            diff, pct_dev = compute_percentage_deviation(actual_val, stats.median)
            expected_str = f"Median {stats.median:,.2f} (±{allowed_dev_pct}%)"

            if direction == "increase" and diff < 0:
                is_anomaly = False
            elif direction == "decrease" and diff > 0:
                is_anomaly = False
            else:
                is_anomaly = pct_dev > allowed_dev_pct

            diff_sign = "+" if diff > 0 else ""
            dev_display = f"{diff_sign}{diff:,.2f} ({diff_sign}{pct_dev:.2f}%) from median"
            baseline_val = stats.median

        elif comparison_method == "previous_period":
            prev_val = clean_values[-1]
            diff, pct_dev = compute_percentage_deviation(actual_val, prev_val)
            expected_str = f"Previous {prev_val:,.2f} (±{allowed_dev_pct}%)"

            if direction == "increase" and diff < 0:
                is_anomaly = False
            elif direction == "decrease" and diff > 0:
                is_anomaly = False
            else:
                is_anomaly = pct_dev > allowed_dev_pct

            diff_sign = "+" if diff > 0 else ""
            dev_display = f"{diff_sign}{diff:,.2f} ({diff_sign}{pct_dev:.2f}%) from previous"
            baseline_val = prev_val

        else:
            # Default to historical mean
            diff, pct_dev = compute_percentage_deviation(actual_val, stats.mean)
            expected_str = f"Mean {stats.mean:,.2f} (±{allowed_dev_pct}%)"

            if direction == "increase" and diff < 0:
                is_anomaly = False
            elif direction == "decrease" and diff > 0:
                is_anomaly = False
            else:
                is_anomaly = pct_dev > allowed_dev_pct

            diff_sign = "+" if diff > 0 else ""
            dev_display = f"{diff_sign}{diff:,.2f} ({diff_sign}{pct_dev:.2f}%) from mean"
            baseline_val = stats.mean

        if is_anomaly:
            return CheckEvaluationResult(
                rule_id=rule.id,
                rule_name=rule.rule_name,
                validation_type=rule.validation_type,
                target_type=rule.target_type,
                status=ValidationStatus.FAIL,
                actual_value=actual_display,
                expected_value=expected_str,
                deviation=dev_display,
                result_summary=f"Anomaly detected in {target_name}: {actual_display} deviates significantly ({dev_display}).",
                detailed_message=(
                    f"Target: {target_name}\n"
                    f"Actual Value: {actual_display}\n"
                    f"Expected Baseline ({comparison_method}): {expected_str}\n"
                    f"Deviation: {dev_display}\n"
                    f"Direction Monitored: {direction}\n"
                    f"Lookback Window: {lookback_days} days ({stats.sample_count} samples)\n"
                    f"Distribution Stats: Mean={stats.mean:,.2f}, Median={stats.median:,.2f}, StdDev={stats.stdev:,.2f}"
                ),
                started_at=t_start,
                completed_at=now,
                duration_ms=duration_ms,
                metadata_snapshot={
                    "actual_value": actual_val,
                    "baseline_value": baseline_val,
                    "comparison_method": comparison_method,
                    "sample_count": stats.sample_count,
                    "mean": stats.mean,
                    "median": stats.median,
                    "stdev": stats.stdev,
                },
            )

        return CheckEvaluationResult(
            rule_id=rule.id,
            rule_name=rule.rule_name,
            validation_type=rule.validation_type,
            target_type=rule.target_type,
            status=ValidationStatus.PASS,
            actual_value=actual_display,
            expected_value=expected_str,
            deviation=f"Normal ({dev_display})",
            result_summary=f"Anomaly check passed for {target_name}: {actual_display} within historical baseline.",
            detailed_message=(
                f"Target: {target_name}\n"
                f"Actual Value: {actual_display}\n"
                f"Expected Baseline ({comparison_method}): {expected_str}\n"
                f"Deviation: {dev_display}\n"
                f"Lookback Window: {lookback_days} days ({stats.sample_count} samples)\n"
                f"Distribution Stats: Mean={stats.mean:,.2f}, Median={stats.median:,.2f}, StdDev={stats.stdev:,.2f}"
            ),
            started_at=t_start,
            completed_at=now,
            duration_ms=duration_ms,
            metadata_snapshot={
                "actual_value": actual_val,
                "baseline_value": baseline_val,
                "comparison_method": comparison_method,
                "sample_count": stats.sample_count,
                "mean": stats.mean,
                "median": stats.median,
                "stdev": stats.stdev,
            },
        )
