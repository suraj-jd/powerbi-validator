"""Power BI Refresh validation check evaluating model refresh SLA and status (Stage 10E)."""

from __future__ import annotations

import logging
from typing import Any

from app.core.status import ValidationStatus
from app.database.models import utc_now
from app.integrations.powerbi.dax_client import DaxQueryClient
from app.services.refresh_service import RefreshService
from app.services.rule_service import RuleRecord
from app.validation.base import BaseValidator
from app.validation.models import CheckEvaluationResult

logger = logging.getLogger(__name__)


class RefreshValidator(BaseValidator):
    """Evaluates semantic model refresh history against status and freshness SLA (BRD 5.3 G)."""

    def __init__(self, refresh_service: RefreshService | None = None) -> None:
        self._refresh_service = refresh_service

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
        svc = (context.get("refresh_service") if context else None) or self._refresh_service

        if svc is None:
            return CheckEvaluationResult.create_error(
                rule_id=rule.id,
                rule_name=rule.rule_name,
                validation_type=rule.validation_type,
                target_type=rule.target_type,
                error_message="RefreshValidator requires RefreshService in context or constructor.",
                started_at=t_start,
            )

        eval_res = svc.evaluate_refresh_rule(
            workspace_registration_id=rule.workspace_registration_id,
            config=rule.config or {},
        )

        now = utc_now()
        duration_ms = int((now - t_start).total_seconds() * 1000)

        meta: dict[str, Any] = {}
        if eval_res.refresh_record:
            rec = eval_res.refresh_record
            meta = {
                "refresh_id": rec.refresh_id,
                "status": rec.status.value,
                "refresh_type": rec.refresh_type,
                "start_time": rec.start_time.isoformat() if rec.start_time else None,
                "end_time": rec.end_time.isoformat() if rec.end_time else None,
                "duration_ms": rec.duration_ms,
                "age_hours": rec.age_hours,
            }

        return CheckEvaluationResult(
            rule_id=rule.id,
            rule_name=rule.rule_name,
            validation_type=rule.validation_type,
            target_type=rule.target_type,
            status=eval_res.status,
            actual_value=eval_res.actual_value,
            expected_value=eval_res.expected_value,
            deviation=eval_res.deviation,
            result_summary=eval_res.result_summary,
            detailed_message=eval_res.detailed_message,
            started_at=t_start,
            completed_at=now,
            duration_ms=max(1, duration_ms),
            metadata_snapshot=meta,
        )
