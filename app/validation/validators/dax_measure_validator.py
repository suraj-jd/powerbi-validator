"""DAX Measure validator evaluating measures against fixed baselines or ranges (Stage 11A)."""

from __future__ import annotations

import logging
from typing import Any

from app.core.status import ValidationStatus
from app.database.models import utc_now
from app.integrations.powerbi.dax_client import (
    DaxQueryClient,
    build_measure_query,
    escape_measure_name,
)
from app.services.rule_service import RuleRecord
from app.validation.base import BaseValidator
from app.validation.models import CheckEvaluationResult
from app.validation.stats import compute_percentage_deviation

logger = logging.getLogger(__name__)


class DaxMeasureValidator(BaseValidator):
    """Validates a DAX measure scalar value against fixed baselines, ranges, or prior runs (BRD 5.3 E)."""

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

        if not rule.measure_name or not rule.measure_name.strip():
            return CheckEvaluationResult.create_error(
                rule_id=rule.id,
                rule_name=rule.rule_name,
                validation_type=rule.validation_type,
                target_type=rule.target_type,
                error_message="DAX Measure check requires a Measure Name.",
                started_at=t_start,
            )

        cfg = rule.config or {}
        filter_context = cfg.get("filter_context") or cfg.get("filter_condition")
        expected_method = str(cfg.get("expected_method", "fixed")).strip().lower()
        allowed_dev_pct = float(cfg.get("allowed_deviation_pct", 5.0))
        allowed_dev_abs = float(cfg["allowed_deviation_abs"]) if "allowed_deviation_abs" in cfg and cfg["allowed_deviation_abs"] is not None else None

        clean_measure = escape_measure_name(rule.measure_name, rule.table_name)
        query = build_measure_query(clean_measure, filter_context=filter_context)

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

        actual_display = dax_res.display_value

        if dax_res.is_blank or dax_res.scalar_value is None:
            # Measure evaluated to BLANK()
            return CheckEvaluationResult(
                rule_id=rule.id,
                rule_name=rule.rule_name,
                validation_type=rule.validation_type,
                target_type=rule.target_type,
                status=ValidationStatus.FAIL,
                actual_value="BLANK()",
                expected_value=str(cfg.get("expected_value", "Non-blank")),
                deviation="Result is BLANK()",
                result_summary=f"Measure {clean_measure} returned BLANK().",
                detailed_message=f"Query executed:\n{query}\nFilter: {filter_context or 'None'}",
                started_at=t_start,
                completed_at=now,
                duration_ms=duration_ms,
                metadata_snapshot={"scalar_value": None, "is_blank": True},
            )

        try:
            val = float(dax_res.scalar_value)
        except (ValueError, TypeError):
            # Non-numeric measure (e.g. string or boolean)
            expected_str = str(cfg.get("expected_value", ""))
            actual_str = str(dax_res.scalar_value)
            passed = actual_str.strip().lower() == expected_str.strip().lower()
            return CheckEvaluationResult(
                rule_id=rule.id,
                rule_name=rule.rule_name,
                validation_type=rule.validation_type,
                target_type=rule.target_type,
                status=ValidationStatus.PASS if passed else ValidationStatus.FAIL,
                actual_value=actual_str,
                expected_value=expected_str,
                deviation="Match" if passed else "Value mismatch",
                result_summary=f"Measure returned '{actual_str}'." if passed else f"Measure value '{actual_str}' did not match expected '{expected_str}'.",
                detailed_message=f"Measure: {clean_measure}\nQuery: {query}",
                started_at=t_start,
                completed_at=now,
                duration_ms=duration_ms,
                metadata_snapshot={"scalar_value": actual_str},
            )

        # Mode A: Range check (min_max)
        min_val = cfg.get("min_value")
        max_val = cfg.get("max_value")
        if expected_method == "min_max" or (min_val is not None or max_val is not None):
            expected_parts = []
            if min_val is not None:
                expected_parts.append(f">= {float(min_val):,.2f}")
            if max_val is not None:
                expected_parts.append(f"<= {float(max_val):,.2f}")
            expected_str = " and ".join(expected_parts) or "Any"

            if min_val is not None and val < float(min_val):
                under = float(min_val) - val
                return CheckEvaluationResult(
                    rule_id=rule.id,
                    rule_name=rule.rule_name,
                    validation_type=rule.validation_type,
                    target_type=rule.target_type,
                    status=ValidationStatus.FAIL,
                    actual_value=actual_display,
                    expected_value=expected_str,
                    deviation=f"-{under:,.2f} below min",
                    result_summary=f"Measure {clean_measure} = {val:,.2f} is below minimum {float(min_val):,.2f}.",
                    detailed_message=f"Measure: {clean_measure}\nActual: {val}\nMin: {min_val}",
                    started_at=t_start,
                    completed_at=now,
                    duration_ms=duration_ms,
                    metadata_snapshot={"value": val, "min_value": min_val, "max_value": max_val},
                )

            if max_val is not None and val > float(max_val):
                over = val - float(max_val)
                return CheckEvaluationResult(
                    rule_id=rule.id,
                    rule_name=rule.rule_name,
                    validation_type=rule.validation_type,
                    target_type=rule.target_type,
                    status=ValidationStatus.FAIL,
                    actual_value=actual_display,
                    expected_value=expected_str,
                    deviation=f"+{over:,.2f} above max",
                    result_summary=f"Measure {clean_measure} = {val:,.2f} exceeds maximum {float(max_val):,.2f}.",
                    detailed_message=f"Measure: {clean_measure}\nActual: {val}\nMax: {max_val}",
                    started_at=t_start,
                    completed_at=now,
                    duration_ms=duration_ms,
                    metadata_snapshot={"value": val, "min_value": min_val, "max_value": max_val},
                )

            return CheckEvaluationResult(
                rule_id=rule.id,
                rule_name=rule.rule_name,
                validation_type=rule.validation_type,
                target_type=rule.target_type,
                status=ValidationStatus.PASS,
                actual_value=actual_display,
                expected_value=expected_str,
                deviation="None (Within range)",
                result_summary=f"Measure {clean_measure} passed range check: {actual_display}.",
                detailed_message=f"Measure: {clean_measure}\nActual: {val}\nAllowed: {expected_str}",
                started_at=t_start,
                completed_at=now,
                duration_ms=duration_ms,
                metadata_snapshot={"value": val, "min_value": min_val, "max_value": max_val},
            )

        # Mode B: Fixed baseline or Previous Run
        baseline_val: float | None = None
        baseline_source = "fixed baseline"

        if expected_method == "previous_run":
            baseline_source = "previous run"
            if context and "previous_measure_value" in context and context["previous_measure_value"] is not None:
                try:
                    baseline_val = float(context["previous_measure_value"])
                except Exception:
                    pass
            elif cfg.get("expected_value") is not None:
                baseline_val = float(cfg["expected_value"])
        else:
            if cfg.get("expected_value") is not None:
                baseline_val = float(cfg["expected_value"])

        if baseline_val is None:
            return CheckEvaluationResult(
                rule_id=rule.id,
                rule_name=rule.rule_name,
                validation_type=rule.validation_type,
                target_type=rule.target_type,
                status=ValidationStatus.PASS,
                actual_value=actual_display,
                expected_value="Initial run baseline",
                deviation="None (Initial baseline)",
                result_summary=f"Initial run recorded: {actual_display} (baseline established).",
                detailed_message=f"No baseline configured for {clean_measure}. Value {actual_display} recorded.",
                started_at=t_start,
                completed_at=now,
                duration_ms=duration_ms,
                metadata_snapshot={"value": val, "baseline_value": val},
            )

        diff, pct_dev = compute_percentage_deviation(val, baseline_val)
        expected_str = f"{baseline_val:,.2f} (±{allowed_dev_pct}%)"
        pct_signed = round((diff / abs(baseline_val)) * 100.0, 2) if abs(baseline_val) > 1e-9 else 0.0
        diff_sign = "+" if diff > 0 else ""
        dev_display = f"{diff_sign}{diff:,.2f} ({pct_signed:+.2f}%)"

        pct_failed = pct_dev > allowed_dev_pct
        abs_failed = allowed_dev_abs is not None and abs(diff) > allowed_dev_abs

        if pct_failed or abs_failed:
            return CheckEvaluationResult(
                rule_id=rule.id,
                rule_name=rule.rule_name,
                validation_type=rule.validation_type,
                target_type=rule.target_type,
                status=ValidationStatus.FAIL,
                actual_value=actual_display,
                expected_value=expected_str,
                deviation=dev_display,
                result_summary=f"Measure {clean_measure} deviation {pct_dev:.2f}% exceeds allowed ±{allowed_dev_pct}%.",
                detailed_message=(
                    f"Measure: {clean_measure}\n"
                    f"Actual Value: {actual_display}\n"
                    f"Expected Baseline ({baseline_source}): {baseline_val:,.2f}\n"
                    f"Deviation: {dev_display}\n"
                    f"Allowed Percentage Deviation: ±{allowed_dev_pct}%\n"
                    f"Allowed Absolute Deviation: {allowed_dev_abs if allowed_dev_abs is not None else 'None'}"
                ),
                started_at=t_start,
                completed_at=now,
                duration_ms=duration_ms,
                metadata_snapshot={
                    "value": val,
                    "baseline_value": baseline_val,
                    "diff": diff,
                    "deviation_pct": pct_dev,
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
            deviation=f"{pct_dev:.2f}% deviation",
            result_summary=f"Measure {clean_measure} passed: {actual_display} within ±{allowed_dev_pct}% of {baseline_source}.",
            detailed_message=(
                f"Measure: {clean_measure}\n"
                f"Actual Value: {actual_display}\n"
                f"Expected Baseline ({baseline_source}): {baseline_val:,.2f}\n"
                f"Deviation: {dev_display}\n"
                f"Allowed Deviation: ±{allowed_dev_pct}%"
            ),
            started_at=t_start,
            completed_at=now,
            duration_ms=duration_ms,
            metadata_snapshot={
                "value": val,
                "baseline_value": baseline_val,
                "diff": diff,
                "deviation_pct": pct_dev,
                "allowed_deviation_pct": allowed_dev_pct,
            },
        )
