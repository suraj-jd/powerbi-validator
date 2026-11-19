"""Duplicate check validator comparing total row count against distinct keys (Stage 10B)."""

from __future__ import annotations

import logging
from typing import Any

from app.core.status import ValidationStatus
from app.database.models import utc_now
from app.integrations.powerbi.dax_client import (
    DaxQueryClient,
    escape_column_reference,
    escape_table_name,
)
from app.services.rule_service import RuleRecord
from app.validation.base import BaseValidator
from app.validation.models import CheckEvaluationResult

logger = logging.getLogger(__name__)


class DuplicateValidator(BaseValidator):
    """Validates uniqueness of single or composite column keys (BRD 5.3 B)."""

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
                error_message="Duplicate check requires Table Name.",
                started_at=t_start,
            )

        cfg = rule.config or {}
        key_cols_raw = cfg.get("key_columns")
        if isinstance(key_cols_raw, list) and key_cols_raw:
            key_columns = [str(c).strip() for c in key_cols_raw if str(c).strip()]
        elif isinstance(key_cols_raw, str) and key_cols_raw.strip():
            key_columns = [c.strip() for c in key_cols_raw.split(",") if c.strip()]
        elif rule.column_name and rule.column_name.strip():
            key_columns = [rule.column_name.strip()]
        else:
            return CheckEvaluationResult.create_error(
                rule_id=rule.id,
                rule_name=rule.rule_name,
                validation_type=rule.validation_type,
                target_type=rule.target_type,
                error_message="Duplicate check requires Column Name or key_columns configuration.",
                started_at=t_start,
            )

        tbl_name = escape_table_name(rule.table_name)
        filter_cond = cfg.get("filter_condition")
        allowed_count = int(cfg.get("allowed_duplicate_count", 0))
        allowed_pct = float(cfg.get("allowed_duplicate_percentage", 0.0))

        # Base table expression
        table_expr = tbl_name
        if filter_cond and filter_cond.strip():
            table_expr = f"FILTER({tbl_name}, {filter_cond.strip()})"

        col_refs = [escape_column_reference(col, rule.table_name) for col in key_columns]
        summarize_cols = ", ".join(col_refs)

        # DAX query computing total rows and distinct key rows in one single roundtrip
        query = (
            f"EVALUATE ROW(\n"
            f'    "TotalRows", COUNTROWS({table_expr}),\n'
            f'    "DistinctKeys", COUNTROWS(SUMMARIZE({table_expr}, {summarize_cols}))\n'
            f")"
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
                expected_value=f"<= {allowed_count} duplicates ({allowed_pct}%)",
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
        distinct_keys = int(_get_val(["[DistinctKeys]", "DistinctKeys"]) or 0)
        duplicate_count = max(0, total_rows - distinct_keys)
        duplicate_pct = round((duplicate_count / total_rows * 100.0), 2) if total_rows > 0 else 0.0

        key_summary = ", ".join(key_columns)
        actual_str = f"{duplicate_count:,} duplicates / {total_rows:,} rows ({duplicate_pct}%)"
        expected_str = f"<= {allowed_count} duplicates ({allowed_pct}%)"

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
                result_summary=f"Table is empty; 0 duplicates on ({key_summary}).",
                detailed_message=f"Keys: {key_summary}\nTotal checked rows: 0\nDistinct keys: 0",
                started_at=t_start,
                completed_at=now,
                duration_ms=duration_ms,
                metadata_snapshot={
                    "total_rows": 0,
                    "distinct_keys": 0,
                    "duplicate_count": 0,
                    "duplicate_pct": 0.0,
                    "key_columns": key_columns,
                },
            )

        count_exceeded = duplicate_count > allowed_count
        pct_exceeded = duplicate_pct > allowed_pct

        if count_exceeded or pct_exceeded:
            dev_parts = []
            if count_exceeded:
                dev_parts.append(f"+{duplicate_count - allowed_count:,} duplicates over limit")
            if pct_exceeded:
                dev_parts.append(f"+{round(duplicate_pct - allowed_pct, 2)}% over limit")
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
                result_summary=f"Duplicate check failed: {duplicate_count:,} duplicates detected on ({key_summary}).",
                detailed_message=(
                    f"Table: {rule.table_name}\n"
                    f"Key Columns: {key_summary}\n"
                    f"Total Rows: {total_rows:,}\n"
                    f"Distinct Keys: {distinct_keys:,}\n"
                    f"Duplicate Count: {duplicate_count:,} ({duplicate_pct}%)\n"
                    f"Allowed Limit: {allowed_count} ({allowed_pct}%)\n"
                    f"Filter: {filter_cond or 'None'}"
                ),
                started_at=t_start,
                completed_at=now,
                duration_ms=duration_ms,
                metadata_snapshot={
                    "total_rows": total_rows,
                    "distinct_keys": distinct_keys,
                    "duplicate_count": duplicate_count,
                    "duplicate_pct": duplicate_pct,
                    "key_columns": key_columns,
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
            result_summary=f"Duplicate check passed: {actual_str} on ({key_summary}).",
            detailed_message=(
                f"Table: {rule.table_name}\n"
                f"Key Columns: {key_summary}\n"
                f"Total Rows: {total_rows:,}\n"
                f"Distinct Keys: {distinct_keys:,}\n"
                f"Duplicate Count: {duplicate_count:,} (Allowed: {allowed_count})"
            ),
            started_at=t_start,
            completed_at=now,
            duration_ms=duration_ms,
            metadata_snapshot={
                "total_rows": total_rows,
                "distinct_keys": distinct_keys,
                "duplicate_count": duplicate_count,
                "duplicate_pct": duplicate_pct,
                "key_columns": key_columns,
            },
        )
