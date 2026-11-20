"""Row count validator comparing table size against fixed baseline, ranges, or previous runs (Stage 10D)."""

from __future__ import annotations

import logging
from typing import Any

from app.core.status import ValidationStatus
from app.database.models import utc_now
from app.integrations.powerbi.dax_client import (
    DaxQueryClient,
    build_table_expression,
    escape_table_name,
    extract_rule_filters,
)
from app.services.rule_service import RuleRecord
from app.validation.base import BaseValidator
from app.validation.models import CheckEvaluationResult

logger = logging.getLogger(__name__)


class RowCountValidator(BaseValidator):
    """Validates table row count against baselines, percentage deviations, or boundaries (BRD 5.3 D)."""

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

        if not rule.table_name:
            return CheckEvaluationResult.create_error(
                rule_id=rule.id,
                rule_name=rule.rule_name,
                validation_type=rule.validation_type,
                target_type=rule.target_type,
                error_message="Row Count check requires a Table Name.",
                started_at=t_start,
            )

        tbl_name = escape_table_name(rule.table_name)
        cfg = rule.config or {}
        filter_cond = cfg.get("filter_condition")
        baseline_method = str(cfg.get("baseline_method", "fixed")).strip().lower()
        allowed_dev_pct = float(cfg.get("allowed_deviation_pct", 5.0))

        filters = extract_rule_filters(cfg)
        table_expr = build_table_expression(rule.table_name, filters)

        query = f'EVALUATE ROW("RowCount", COUNTROWS({table_expr}))'

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

        rows = dax_res.raw_rows
        if not rows:
            return CheckEvaluationResult(
                rule_id=rule.id,
                rule_name=rule.rule_name,
                validation_type=rule.validation_type,
                target_type=rule.target_type,
                status=ValidationStatus.WARNING,
                actual_value="0 rows",
                expected_value="Table row count",
                deviation=None,
                result_summary="Empty dataset: No rows returned by query.",
                detailed_message=f"Query executed:\n{query}",
                started_at=t_start,
                completed_at=now,
                duration_ms=duration_ms,
            )

        first_row = rows[0]
        raw_val = first_row.get("[RowCount]")
        if raw_val is None:
            raw_val = first_row.get("RowCount")
        if raw_val is None and dax_res.scalar_value is not None:
            raw_val = dax_res.scalar_value
        if raw_val is None and first_row:
            raw_val = next(iter(first_row.values()))
        actual_count = int(raw_val or 0)
        actual_str = f"{actual_count:,} rows"

        # Mode A: Range / Min-Max check
        min_count = cfg.get("min_count")
        max_count = cfg.get("max_count")
        if baseline_method == "min_max" or (min_count is not None or max_count is not None):
            expected_parts = []
            if min_count is not None:
                expected_parts.append(f">= {int(min_count):,}")
            if max_count is not None:
                expected_parts.append(f"<= {int(max_count):,}")
            expected_str = " and ".join(expected_parts) or "Any"

            if min_count is not None and actual_count < int(min_count):
                under = int(min_count) - actual_count
                return CheckEvaluationResult(
                    rule_id=rule.id,
                    rule_name=rule.rule_name,
                    validation_type=rule.validation_type,
                    target_type=rule.target_type,
                    status=ValidationStatus.FAIL,
                    actual_value=actual_str,
                    expected_value=expected_str,
                    deviation=f"-{under:,} below minimum",
                    result_summary=f"Row count {actual_count:,} is below minimum {int(min_count):,}.",
                    detailed_message=f"Table: {rule.table_name}\nActual: {actual_count:,}\nMin: {int(min_count):,}",
                    started_at=t_start,
                    completed_at=now,
                    duration_ms=duration_ms,
                    metadata_snapshot={"actual_count": actual_count, "min_count": min_count, "max_count": max_count},
                )

            if max_count is not None and actual_count > int(max_count):
                over = actual_count - int(max_count)
                return CheckEvaluationResult(
                    rule_id=rule.id,
                    rule_name=rule.rule_name,
                    validation_type=rule.validation_type,
                    target_type=rule.target_type,
                    status=ValidationStatus.FAIL,
                    actual_value=actual_str,
                    expected_value=expected_str,
                    deviation=f"+{over:,} above maximum",
                    result_summary=f"Row count {actual_count:,} exceeds maximum {int(max_count):,}.",
                    detailed_message=f"Table: {rule.table_name}\nActual: {actual_count:,}\nMax: {int(max_count):,}",
                    started_at=t_start,
                    completed_at=now,
                    duration_ms=duration_ms,
                    metadata_snapshot={"actual_count": actual_count, "min_count": min_count, "max_count": max_count},
                )

            return CheckEvaluationResult(
                rule_id=rule.id,
                rule_name=rule.rule_name,
                validation_type=rule.validation_type,
                target_type=rule.target_type,
                status=ValidationStatus.PASS,
                actual_value=actual_str,
                expected_value=expected_str,
                deviation="None (Within range)",
                result_summary=f"Row count passed range check: {actual_str}.",
                detailed_message=f"Table: {rule.table_name}\nActual: {actual_count:,}\nAllowed: {expected_str}",
                started_at=t_start,
                completed_at=now,
                duration_ms=duration_ms,
                metadata_snapshot={"actual_count": actual_count, "min_count": min_count, "max_count": max_count},
            )

        # Mode B: Fixed baseline or Previous Run
        baseline_val: float | None = None
        baseline_source = "fixed baseline"

        if baseline_method == "previous_run":
            baseline_source = "previous run"
            if context and "previous_row_count" in context and context["previous_row_count"] is not None:
                baseline_val = float(context["previous_row_count"])
            elif cfg.get("baseline_value") is not None:
                baseline_val = float(cfg["baseline_value"])
        else:
            if cfg.get("baseline_value") is not None:
                baseline_val = float(cfg["baseline_value"])

        if baseline_val is None:
            # Initial run with no prior history or fixed baseline
            return CheckEvaluationResult(
                rule_id=rule.id,
                rule_name=rule.rule_name,
                validation_type=rule.validation_type,
                target_type=rule.target_type,
                status=ValidationStatus.PASS,
                actual_value=actual_str,
                expected_value="Initial run baseline",
                deviation="None (Initial baseline)",
                result_summary=f"Initial run recorded: {actual_str} (baseline established).",
                detailed_message=f"No prior baseline configured. Current row count {actual_count:,} recorded.",
                started_at=t_start,
                completed_at=now,
                duration_ms=duration_ms,
                metadata_snapshot={"actual_count": actual_count, "baseline_value": actual_count},
            )

        expected_str = f"{int(baseline_val):,} (±{allowed_dev_pct}%)"

        if baseline_val == 0:
            if actual_count == 0:
                dev_pct = 0.0
                passed = True
            else:
                dev_pct = 100.0
                passed = False
            diff = actual_count
        else:
            diff = actual_count - baseline_val
            dev_pct = round((abs(diff) / baseline_val) * 100.0, 2)
            pct_signed = round((diff / baseline_val) * 100.0, 2)
            passed = dev_pct <= allowed_dev_pct

        diff_sign = "+" if diff > 0 else ""
        dev_display = f"{diff_sign}{int(diff):,} ({pct_signed:+.2f}%)" if baseline_val > 0 else f"{diff_sign}{int(diff):,}"

        if not passed:
            return CheckEvaluationResult(
                rule_id=rule.id,
                rule_name=rule.rule_name,
                validation_type=rule.validation_type,
                target_type=rule.target_type,
                status=ValidationStatus.FAIL,
                actual_value=actual_str,
                expected_value=expected_str,
                deviation=dev_display,
                result_summary=f"Row count deviation {dev_pct:.2f}% exceeds allowed ±{allowed_dev_pct}%.",
                detailed_message=(
                    f"Table: {rule.table_name}\n"
                    f"Actual Rows: {actual_count:,}\n"
                    f"Expected Baseline ({baseline_source}): {int(baseline_val):,}\n"
                    f"Deviation: {dev_display}\n"
                    f"Allowed Deviation: ±{allowed_dev_pct}%"
                ),
                started_at=t_start,
                completed_at=now,
                duration_ms=duration_ms,
                metadata_snapshot={
                    "actual_count": actual_count,
                    "baseline_value": baseline_val,
                    "deviation_pct": dev_pct,
                    "allowed_deviation_pct": allowed_dev_pct,
                },
            )

        return CheckEvaluationResult(
            rule_id=rule.id,
            rule_name=rule.rule_name,
            validation_type=rule.validation_type,
            target_type=rule.target_type,
            status=ValidationStatus.PASS,
            actual_value=actual_str,
            expected_value=expected_str,
            deviation=f"{dev_pct:.2f}% deviation",
            result_summary=f"Row count passed: {actual_str} within ±{allowed_dev_pct}% of {baseline_source}.",
            detailed_message=(
                f"Table: {rule.table_name}\n"
                f"Actual Rows: {actual_count:,}\n"
                f"Expected Baseline ({baseline_source}): {int(baseline_val):,}\n"
                f"Deviation: {dev_display}\n"
                f"Allowed Deviation: ±{allowed_dev_pct}%"
            ),
            started_at=t_start,
            completed_at=now,
            duration_ms=duration_ms,
            metadata_snapshot={
                "actual_count": actual_count,
                "baseline_value": baseline_val,
                "deviation_pct": dev_pct,
                "allowed_deviation_pct": allowed_dev_pct,
            },
        )
