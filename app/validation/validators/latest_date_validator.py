"""Latest date / freshness validator checking data recency and future date violations (Stage 10C)."""

from __future__ import annotations

from datetime import datetime, timezone
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


def parse_dax_datetime(raw_val: Any) -> datetime | None:
    """Robustly parse a datetime value returned by DAX."""
    if raw_val is None:
        return None
    if isinstance(raw_val, datetime):
        if raw_val.tzinfo is None:
            return raw_val.replace(tzinfo=timezone.utc)
        return raw_val

    s = str(raw_val).strip()
    if not s:
        return None

    # Handle ISO 8601 strings
    clean = s.replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(clean)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:
        pass

    # Try common formats
    formats = [
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d",
        "%m/%d/%Y %H:%M:%S",
        "%m/%d/%Y",
        "%d/%m/%Y %H:%M:%S",
        "%d/%m/%Y",
    ]
    for fmt in formats:
        try:
            dt = datetime.strptime(s, fmt)
            return dt.replace(tzinfo=timezone.utc)
        except Exception:
            continue

    return None


class LatestDateValidator(BaseValidator):
    """Validates date column recency against freshness SLA and detects future dates (BRD 5.3 C)."""

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
                error_message="Latest Date check requires both Table Name and Column Name.",
                started_at=t_start,
            )

        cfg = rule.config or {}
        max_age_hours = float(cfg.get("max_age_hours", 24.0))
        if "max_age_days" in cfg and cfg.get("max_age_days") is not None:
            max_age_hours = float(cfg["max_age_days"]) * 24.0

        allow_future = bool(cfg.get("allow_future_dates", False))
        future_tolerance = float(cfg.get("future_tolerance_hours", 1.0))
        filter_cond = cfg.get("filter_condition")

        # Allow passing custom reference timestamp for deterministic testing
        ref_time = context.get("reference_timestamp") if context else None
        if ref_time is None:
            ref_time = utc_now()
        elif ref_time.tzinfo is None:
            ref_time = ref_time.replace(tzinfo=timezone.utc)

        tbl_name = escape_table_name(rule.table_name)
        col_ref = escape_column_reference(rule.column_name, rule.table_name)

        table_expr = tbl_name
        if filter_cond and filter_cond.strip():
            table_expr = f"FILTER({tbl_name}, {filter_cond.strip()})"

        # Query max and min date and row count
        query = (
            f"EVALUATE ROW(\n"
            f'    "LatestDate", MAX({col_ref}),\n'
            f'    "EarliestDate", MIN({col_ref}),\n'
            f'    "TotalRows", COUNTROWS({table_expr})\n'
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
                expected_value=f"<= {max_age_hours}h old",
                deviation=None,
                result_summary="Empty dataset: No rows returned by query.",
                detailed_message=f"Query executed:\n{query}",
                started_at=t_start,
                completed_at=now,
                duration_ms=duration_ms,
            )

        first_row = rows[0]
        total_rows = int(first_row.get("[TotalRows]") or first_row.get("TotalRows") or 0)
        raw_latest = first_row.get("[LatestDate]") if "[LatestDate]" in first_row else first_row.get("LatestDate")
        raw_earliest = first_row.get("[EarliestDate]") if "[EarliestDate]" in first_row else first_row.get("EarliestDate")

        if total_rows == 0 or raw_latest is None:
            return CheckEvaluationResult(
                rule_id=rule.id,
                rule_name=rule.rule_name,
                validation_type=rule.validation_type,
                target_type=rule.target_type,
                status=ValidationStatus.WARNING,
                actual_value="No date values",
                expected_value=f"<= {max_age_hours}h old",
                deviation=None,
                result_summary=f"Table is empty or column '{rule.column_name}' contains only blanks.",
                detailed_message=f"Table: {rule.table_name}\nColumn: {rule.column_name}\nTotal rows: {total_rows}",
                started_at=t_start,
                completed_at=now,
                duration_ms=duration_ms,
                metadata_snapshot={"total_rows": total_rows, "latest_date": None},
            )

        latest_dt = parse_dax_datetime(raw_latest)
        if latest_dt is None:
            return CheckEvaluationResult.create_error(
                rule_id=rule.id,
                rule_name=rule.rule_name,
                validation_type=rule.validation_type,
                target_type=rule.target_type,
                error_message=f"Could not parse latest date value: '{raw_latest}'",
                started_at=t_start,
                duration_ms=duration_ms,
            )

        age_seconds = (ref_time - latest_dt).total_seconds()
        age_hours = round(age_seconds / 3600.0, 2)

        formatted_date = latest_dt.strftime("%Y-%m-%d %H:%M:%S UTC")
        actual_str = f"{formatted_date} ({age_hours:.1f}h ago)" if age_hours >= 0 else f"{formatted_date} ({abs(age_hours):.1f}h future)"
        expected_str = f"<= {max_age_hours}h old (since {ref_time.strftime('%Y-%m-%d %H:%M UTC')})"

        # 1. Check future date violation
        if not allow_future and age_hours < -future_tolerance:
            fut_h = round(abs(age_hours), 2)
            return CheckEvaluationResult(
                rule_id=rule.id,
                rule_name=rule.rule_name,
                validation_type=rule.validation_type,
                target_type=rule.target_type,
                status=ValidationStatus.FAIL,
                actual_value=actual_str,
                expected_value=expected_str,
                deviation=f"{fut_h:.1f}h in future",
                result_summary=f"Future date detected: latest date is {fut_h:.1f} hours ahead of current UTC time.",
                detailed_message=(
                    f"Table: {rule.table_name}\n"
                    f"Column: {rule.column_name}\n"
                    f"Latest Date: {formatted_date}\n"
                    f"Reference UTC Time: {ref_time.strftime('%Y-%m-%d %H:%M:%S UTC')}\n"
                    f"Future Delta: {fut_h:.1f} hours\n"
                    f"Allow Future Dates: False"
                ),
                started_at=t_start,
                completed_at=now,
                duration_ms=duration_ms,
                metadata_snapshot={
                    "latest_date": latest_dt.isoformat(),
                    "age_hours": age_hours,
                    "max_age_hours": max_age_hours,
                    "is_future": True,
                },
            )

        # 2. Check freshness SLA exceeded
        if age_hours > max_age_hours:
            over_hours = round(age_hours - max_age_hours, 2)
            return CheckEvaluationResult(
                rule_id=rule.id,
                rule_name=rule.rule_name,
                validation_type=rule.validation_type,
                target_type=rule.target_type,
                status=ValidationStatus.FAIL,
                actual_value=actual_str,
                expected_value=expected_str,
                deviation=f"+{over_hours:.1f}h over limit",
                result_summary=f"Data is stale: latest date is {age_hours:.1f}h old (exceeds {max_age_hours}h limit).",
                detailed_message=(
                    f"Table: {rule.table_name}\n"
                    f"Column: {rule.column_name}\n"
                    f"Latest Date: {formatted_date}\n"
                    f"Age: {age_hours:.1f} hours\n"
                    f"Allowed Age: {max_age_hours} hours\n"
                    f"Exceeded by: {over_hours:.1f} hours"
                ),
                started_at=t_start,
                completed_at=now,
                duration_ms=duration_ms,
                metadata_snapshot={
                    "latest_date": latest_dt.isoformat(),
                    "age_hours": age_hours,
                    "max_age_hours": max_age_hours,
                    "is_future": False,
                },
            )

        # 3. Passed
        margin_hours = round(max_age_hours - age_hours, 2)
        return CheckEvaluationResult(
            rule_id=rule.id,
            rule_name=rule.rule_name,
            validation_type=rule.validation_type,
            target_type=rule.target_type,
            status=ValidationStatus.PASS,
            actual_value=actual_str,
            expected_value=expected_str,
            deviation=f"-{margin_hours:.1f}h margin",
            result_summary=f"Latest date check passed: {actual_str}.",
            detailed_message=(
                f"Table: {rule.table_name}\n"
                f"Column: {rule.column_name}\n"
                f"Latest Date: {formatted_date}\n"
                f"Age: {age_hours:.1f} hours (SLA: <= {max_age_hours} hours)"
            ),
            started_at=t_start,
            completed_at=now,
            duration_ms=duration_ms,
            metadata_snapshot={
                "latest_date": latest_dt.isoformat(),
                "age_hours": age_hours,
                "max_age_hours": max_age_hours,
                "is_future": False,
            },
        )
