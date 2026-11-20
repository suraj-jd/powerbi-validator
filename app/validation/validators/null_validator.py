"""Null and Blank validator checking columns for missing or empty values (Stage 10A)."""

from __future__ import annotations

import logging
from typing import Any

from app.core.status import ValidationStatus
from app.database.models import utc_now
from app.integrations.powerbi.dax_client import (
    DaxQueryClient,
    build_table_expression,
    escape_column_reference,
    escape_table_name,
    extract_rule_filters,
)
from app.services.rule_service import RuleRecord
from app.validation.base import BaseValidator
from app.validation.models import CheckEvaluationResult

logger = logging.getLogger(__name__)


class NullValidator(BaseValidator):
    """Checks column null/blank count and percentage against configured thresholds (BRD 5.3 A)."""

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

        if not rule.table_name or not rule.column_name:
            return CheckEvaluationResult.create_error(
                rule_id=rule.id,
                rule_name=rule.rule_name,
                validation_type=rule.validation_type,
                target_type=rule.target_type,
                error_message="Null check requires both Table Name and Column Name.",
                started_at=t_start,
            )

        tbl_name = escape_table_name(rule.table_name)
        col_ref = escape_column_reference(rule.column_name, rule.table_name)

        cfg = rule.config or {}
        allowed_count = int(cfg.get("allowed_blank_count", 0))
        allowed_pct = float(cfg.get("allowed_blank_percentage", 0.0))
        include_empty = cfg.get("include_empty_string", True)
        include_whitespace = cfg.get("include_whitespace", False)
        filter_cond = cfg.get("filter_condition")

        # Build conditions for blank check
        cond_parts = [f"ISBLANK({col_ref})"]
        if include_empty:
            cond_parts.append(f'{col_ref} = ""')
        if include_whitespace:
            cond_parts.append(f'TRIM({col_ref}) = ""')
        is_blank_expr = " || ".join(cond_parts)

        # Base table expression with filters applied
        filters = extract_rule_filters(cfg)
        table_expr = build_table_expression(rule.table_name, filters)

        # DAX query returning both TotalRows and BlankCount in one roundtrip
        query = (
            f'EVALUATE ROW(\n'
            f'    "TotalRows", COUNTROWS({table_expr}),\n'
            f'    "BlankCount", COUNTROWS(FILTER({table_expr}, {is_blank_expr}))\n'
            f')'
        )

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
                expected_value=f"<= {allowed_count} blanks ({allowed_pct}%)",
                deviation=None,
                result_summary="Empty dataset: No rows returned by query.",
                detailed_message=f"Query executed:\n{query}",
                started_at=t_start,
                completed_at=now,
                duration_ms=duration_ms,
            )

        first_row = rows[0]
        def _get_val(keys: list[str]) -> Any:
            for k in keys:
                if k in first_row and first_row[k] is not None:
                    return first_row[k]
                for rk, rv in first_row.items():
                    if rk.strip().strip("[]").lower() == k.strip().strip("[]").lower() and rv is not None:
                        return rv
            return None

        total_rows = int(_get_val(["[TotalRows]", "TotalRows"]) or 0)
        blank_count = int(_get_val(["[BlankCount]", "BlankCount"]) or 0)

        blank_pct = round((blank_count / total_rows * 100.0), 2) if total_rows > 0 else 0.0

        actual_str = f"{blank_count:,} blanks / {total_rows:,} rows ({blank_pct}%)"
        expected_str = f"<= {allowed_count} blanks ({allowed_pct}%)"

        if total_rows == 0:
            return CheckEvaluationResult(
                rule_id=rule.id,
                rule_name=rule.rule_name,
                validation_type=rule.validation_type,
                target_type=rule.target_type,
                status=ValidationStatus.PASS,
                actual_value=actual_str,
                expected_value=expected_str,
                deviation="None (Empty table)",
                result_summary="Table is empty; 0 blanks detected.",
                detailed_message=f"Total checked rows: 0\nBlank count: 0",
                started_at=t_start,
                completed_at=now,
                duration_ms=duration_ms,
                metadata_snapshot={"total_rows": 0, "blank_count": 0, "blank_pct": 0.0},
            )

        # Check violation
        count_exceeded = blank_count > allowed_count
        pct_exceeded = blank_pct > allowed_pct

        if count_exceeded or pct_exceeded:
            dev_parts = []
            if count_exceeded:
                dev_parts.append(f"+{blank_count - allowed_count:,} blanks over limit")
            if pct_exceeded:
                dev_parts.append(f"+{round(blank_pct - allowed_pct, 2)}% over limit")
            deviation_str = ", ".join(dev_parts)

            return CheckEvaluationResult(
                rule_id=rule.id,
                rule_name=rule.rule_name,
                validation_type=rule.validation_type,
                target_type=rule.target_type,
                status=ValidationStatus.FAIL,
                actual_value=actual_str,
                expected_value=expected_str,
                deviation=deviation_str,
                result_summary=f"Column '{rule.column_name}' exceeded allowed blanks ({actual_str}).",
                detailed_message=(
                    f"Table: {rule.table_name}\nColumn: {rule.column_name}\n"
                    f"Blank count: {blank_count:,}\nTotal rows: {total_rows:,}\n"
                    f"Blank percentage: {blank_pct}%\nAllowed limit: {allowed_count} ({allowed_pct}%)\n"
                    f"Filter: {filter_cond or 'None'}"
                ),
                started_at=t_start,
                completed_at=now,
                duration_ms=duration_ms,
                metadata_snapshot={
                    "total_rows": total_rows,
                    "blank_count": blank_count,
                    "blank_pct": blank_pct,
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
            deviation="None (Within threshold)",
            result_summary=f"Null check passed: {actual_str}.",
            detailed_message=f"Checked {total_rows:,} rows in {tbl_name}; found {blank_count:,} blanks (allowed: {allowed_count}).",
            started_at=t_start,
            completed_at=now,
            duration_ms=duration_ms,
            metadata_snapshot={
                "total_rows": total_rows,
                "blank_count": blank_count,
                "blank_pct": blank_pct,
            },
        )
