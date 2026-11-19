"""Base validator interface for all rule checks in the validation engine (Stage 10)."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from app.integrations.powerbi.dax_client import DaxQueryClient
from app.services.rule_service import RuleRecord
from app.validation.models import CheckEvaluationResult


class BaseValidator(ABC):
    """Abstract base class for all deterministic and anomaly validators."""

    @abstractmethod
    def validate(
        self,
        *,
        rule: RuleRecord,
        dax_client: DaxQueryClient,
        workspace_id: str,
        dataset_id: str,
        context: dict[str, Any] | None = None,
    ) -> CheckEvaluationResult:
        """Execute the validation check and return a standardized CheckEvaluationResult."""
        raise NotImplementedError
