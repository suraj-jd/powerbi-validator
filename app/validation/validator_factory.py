"""Validator factory and registry for dispatching validation checks (Stage 10)."""

from __future__ import annotations

from typing import Any

from app.services.rule_service import (
    VALIDATION_TYPE_ANOMALY,
    VALIDATION_TYPE_DAX_MEASURE,
    VALIDATION_TYPE_DUPLICATE,
    VALIDATION_TYPE_LATEST_DATE,
    VALIDATION_TYPE_NULL,
    VALIDATION_TYPE_REFRESH,
    VALIDATION_TYPE_ROW_COUNT,
)
from app.validation.base import BaseValidator
from app.validation.validators.anomaly_validator import AnomalyValidator
from app.validation.validators.dax_measure_validator import DaxMeasureValidator
from app.validation.validators.duplicate_validator import DuplicateValidator
from app.validation.validators.latest_date_validator import LatestDateValidator
from app.validation.validators.null_validator import NullValidator
from app.validation.validators.refresh_validator import RefreshValidator
from app.validation.validators.row_count_validator import RowCountValidator

_VALIDATOR_REGISTRY: dict[str, BaseValidator] = {
    VALIDATION_TYPE_NULL: NullValidator(),
    VALIDATION_TYPE_DUPLICATE: DuplicateValidator(),
    VALIDATION_TYPE_LATEST_DATE: LatestDateValidator(),
    VALIDATION_TYPE_ROW_COUNT: RowCountValidator(),
    VALIDATION_TYPE_REFRESH: RefreshValidator(),
    VALIDATION_TYPE_DAX_MEASURE: DaxMeasureValidator(),
    VALIDATION_TYPE_ANOMALY: AnomalyValidator(),
}


def register_validator(validation_type: str, validator: BaseValidator) -> None:
    """Register or override a validator implementation for a validation type."""
    _VALIDATOR_REGISTRY[validation_type] = validator


def get_validator(validation_type: str) -> BaseValidator:
    """Retrieve validator instance for the given validation type."""
    validator = _VALIDATOR_REGISTRY.get(validation_type)
    if not validator:
        raise ValueError(f"No validator registered for validation type: '{validation_type}'")
    return validator


def has_validator(validation_type: str) -> bool:
    """Check if a validator is registered for a validation type."""
    return validation_type in _VALIDATOR_REGISTRY
