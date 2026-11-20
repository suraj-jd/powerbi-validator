"""Application service managing row-based validation rule configuration."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any

from app.core.exceptions import PersistenceError, ValidationConfigError
from app.database.db import DatabaseManager
from app.database.models import ValidationRule
from app.database.repositories import ValidationRuleRepository

logger = logging.getLogger(__name__)

# Canonical validation types (BRD 5.3)
VALIDATION_TYPE_NULL = "null_check"
VALIDATION_TYPE_DUPLICATE = "duplicate_check"
VALIDATION_TYPE_LATEST_DATE = "latest_date_check"
VALIDATION_TYPE_ROW_COUNT = "row_count_check"
VALIDATION_TYPE_DAX_MEASURE = "dax_measure_check"
VALIDATION_TYPE_ANOMALY = "anomaly_check"
VALIDATION_TYPE_REFRESH = "refresh_check"

VALIDATION_TYPES: dict[str, str] = {
    VALIDATION_TYPE_NULL: "Null / Blank Check",
    VALIDATION_TYPE_DUPLICATE: "Duplicate Check",
    VALIDATION_TYPE_LATEST_DATE: "Latest Date Check",
    VALIDATION_TYPE_ROW_COUNT: "Row Count Check",
    VALIDATION_TYPE_DAX_MEASURE: "DAX Measure Check",
    VALIDATION_TYPE_ANOMALY: "Baseline & % Change Check",
    VALIDATION_TYPE_REFRESH: "Power BI Refresh Check",
}

# Target Types (BRD 5.2)
TARGET_TYPE_COLUMN = "COLUMN"
TARGET_TYPE_MEASURE = "MEASURE"
TARGET_TYPE_MODEL = "MODEL"

TARGET_TYPES: dict[str, str] = {
    TARGET_TYPE_COLUMN: "Table Column",
    TARGET_TYPE_MEASURE: "DAX Measure",
    TARGET_TYPE_MODEL: "Model / Refresh",
}

# Mapping of target types to compatible validation types
COMPATIBLE_CHECKS: dict[str, list[str]] = {
    TARGET_TYPE_COLUMN: [
        VALIDATION_TYPE_NULL,
        VALIDATION_TYPE_DUPLICATE,
        VALIDATION_TYPE_LATEST_DATE,
        VALIDATION_TYPE_ROW_COUNT,
        VALIDATION_TYPE_ANOMALY,
    ],
    TARGET_TYPE_MEASURE: [
        VALIDATION_TYPE_DAX_MEASURE,
        VALIDATION_TYPE_ANOMALY,
    ],
    TARGET_TYPE_MODEL: [
        VALIDATION_TYPE_REFRESH,
    ],
}


@dataclass(frozen=True, slots=True)
class RuleRecord:
    """Detached immutable representation of one validation rule."""

    id: int
    workspace_registration_id: int
    rule_name: str
    enabled: bool
    target_type: str
    table_name: str | None
    column_name: str | None
    measure_name: str | None
    validation_type: str
    config: dict[str, Any]
    display_order: int

    @property
    def validation_type_display(self) -> str:
        return VALIDATION_TYPES.get(self.validation_type, self.validation_type)

    @property
    def target_type_display(self) -> str:
        return TARGET_TYPES.get(self.target_type, self.target_type)

    @property
    def target_display(self) -> str:
        if self.target_type == TARGET_TYPE_MODEL:
            return "Semantic Model"
        if self.target_type == TARGET_TYPE_MEASURE:
            return self.measure_name or "-"
        if self.table_name and self.column_name:
            return f"{self.table_name}[{self.column_name}]"
        return self.table_name or self.column_name or "-"

    @property
    def conditions_summary(self) -> str:
        return format_rule_conditions_summary(self.validation_type, self.config)

    @classmethod
    def from_orm(cls, model: ValidationRule) -> RuleRecord:
        try:
            cfg = json.loads(model.config_json or "{}")
            if not isinstance(cfg, dict):
                cfg = {}
        except Exception:
            cfg = {}

        return cls(
            id=model.id,
            workspace_registration_id=model.workspace_registration_id,
            rule_name=model.rule_name,
            enabled=model.enabled,
            target_type=model.target_type,
            table_name=model.table_name,
            column_name=model.column_name,
            measure_name=model.measure_name,
            validation_type=model.validation_type,
            config=cfg,
            display_order=model.display_order,
        )


@dataclass
class RuleInput:
    """Input payload for creating or updating a validation rule."""

    workspace_registration_id: int
    rule_name: str
    target_type: str
    validation_type: str
    enabled: bool = True
    table_name: str | None = None
    column_name: str | None = None
    measure_name: str | None = None
    config: dict[str, Any] = field(default_factory=dict)
    display_order: int = 0


def validate_rule_input(data: RuleInput) -> list[str]:
    """Validate rule input fields against business rules (BRD 5.2, 5.3)."""
    errors: list[str] = []

    if not data.workspace_registration_id or data.workspace_registration_id <= 0:
        errors.append("A valid workspace registration must be selected.")

    rule_name = (data.rule_name or "").strip()
    if not rule_name:
        errors.append("Rule name cannot be empty.")
    elif len(rule_name) > 255:
        errors.append("Rule name cannot exceed 255 characters.")

    target_type = (data.target_type or "").strip().upper()
    if target_type not in TARGET_TYPES:
        errors.append(f"Invalid target type '{target_type}'. Must be COLUMN, MEASURE, or MODEL.")

    val_type = (data.validation_type or "").strip()
    if val_type not in VALIDATION_TYPES:
        errors.append(f"Invalid validation type '{val_type}'.")

    # Validate compatibility between target type and validation check
    allowed_checks = COMPATIBLE_CHECKS.get(target_type, [])
    if val_type and allowed_checks and val_type not in allowed_checks:
        display_target = TARGET_TYPES.get(target_type, target_type)
        display_check = VALIDATION_TYPES.get(val_type, val_type)
        errors.append(f"{display_check} is not compatible with target type {display_target}.")

    # Field requirements per rule type (BRD Acceptance criteria)
    tbl = (data.table_name or "").strip()
    col = (data.column_name or "").strip()
    meas = (data.measure_name or "").strip()

    if val_type in (VALIDATION_TYPE_NULL, VALIDATION_TYPE_DUPLICATE, VALIDATION_TYPE_LATEST_DATE):
        if not tbl:
            errors.append(f"{VALIDATION_TYPES[val_type]} requires a Table Name.")
        if not col:
            errors.append(f"{VALIDATION_TYPES[val_type]} requires a Column Name.")

    elif val_type == VALIDATION_TYPE_ROW_COUNT:
        if not tbl:
            errors.append("Row Count Check requires a Table Name.")

    elif val_type == VALIDATION_TYPE_DAX_MEASURE:
        if not meas:
            errors.append("DAX Measure Check requires a Measure Name.")

    elif val_type == VALIDATION_TYPE_ANOMALY:
        if target_type == TARGET_TYPE_MEASURE:
            if not meas:
                errors.append("Anomaly Check on Measure requires a Measure Name.")
        else:
            if not tbl or not col:
                errors.append("Anomaly Check on Column requires Table Name and Column Name.")

    elif val_type == VALIDATION_TYPE_REFRESH:
        # Refresh checks apply to the semantic model; table/column are NOT required
        pass

    return errors


def format_rule_conditions_summary(validation_type: str, config: dict[str, Any]) -> str:
    """Format human-readable summary of rule conditions for table display."""
    if not config:
        if validation_type == VALIDATION_TYPE_NULL:
            return "allowed blanks = 0"
        if validation_type == VALIDATION_TYPE_DUPLICATE:
            return "allowed dups = 0"
        if validation_type == VALIDATION_TYPE_REFRESH:
            return "status = Completed"
        return "default settings"

    try:
        if validation_type == VALIDATION_TYPE_NULL:
            allowed_cnt = config.get("allowed_blank_count", 0)
            allowed_pct = config.get("allowed_blank_percentage")
            parts = [f"allowed blanks = {allowed_cnt}"]
            if allowed_pct is not None and float(allowed_pct) > 0:
                parts.append(f"max {allowed_pct}%")
            return ", ".join(parts)

        if validation_type == VALIDATION_TYPE_DUPLICATE:
            allowed_dups = config.get("allowed_duplicate_count", 0)
            keys = config.get("key_columns")
            summary = f"allowed dups = {allowed_dups}"
            if keys and isinstance(keys, list) and len(keys) > 1:
                summary += f" on ({', '.join(keys)})"
            return summary

        if validation_type == VALIDATION_TYPE_LATEST_DATE:
            max_age = config.get("max_age_hours", 24)
            return f"freshness <= {max_age}h"

        if validation_type == VALIDATION_TYPE_ROW_COUNT:
            method = config.get("baseline_method", "fixed")
            dev = config.get("allowed_deviation_pct", 5.0)
            if method == "fixed" and config.get("baseline_value") is not None:
                val = config.get("baseline_value")
                return f"baseline {val:,} (±{dev}%)" if isinstance(val, (int, float)) else f"baseline {val} (±{dev}%)"
            return f"method: {method} (±{dev}%)"

        if validation_type == VALIDATION_TYPE_DAX_MEASURE:
            method = config.get("expected_method", "fixed")
            dev = config.get("allowed_deviation_pct", 5.0)
            if method == "fixed" and config.get("expected_value") is not None:
                return f"expected {config['expected_value']} (±{dev}%)"
            if method == "min_max":
                mn = config.get("min_value", "-∞")
                mx = config.get("max_value", "+∞")
                return f"range [{mn}, {mx}]"
            return f"method: {method} (±{dev}%)"

        if validation_type == VALIDATION_TYPE_ANOMALY:
            lookback = config.get("lookback_days", 30)
            method = config.get("comparison_method", "z_score")
            dev = config.get("allowed_deviation_pct", 10.0)
            return f"lookback {lookback}d, dev <= {dev}% ({method})"

        if validation_type == VALIDATION_TYPE_REFRESH:
            expected = config.get("expected_status", "Completed")
            max_age = config.get("max_age_hours")
            definition = config.get("definition", "latest_attempt")
            res = f"status = {expected}"
            if max_age:
                res += f", age <= {max_age}h"
            if definition == "latest_success":
                res += " (latest success)"
            elif definition == "latest_completed":
                res += " (latest completed)"
            return res

    except Exception:
        pass

    return "configured"


class RuleService:
    """Service coordinating validation rule CRUD and SQLite persistence."""

    def __init__(self, db: DatabaseManager) -> None:
        self._db = db

    def list_rules(
        self,
        workspace_registration_id: int,
        *,
        enabled_only: bool = False,
    ) -> list[RuleRecord]:
        with self._db.session_scope() as session:
            repo = ValidationRuleRepository(session)
            models = repo.list_for_registration(
                workspace_registration_id,
                enabled_only=enabled_only,
            )
            return [RuleRecord.from_orm(m) for m in models]

    def get_rule(self, rule_id: int) -> RuleRecord | None:
        with self._db.session_scope() as session:
            repo = ValidationRuleRepository(session)
            model = repo.get_by_id(rule_id)
            return RuleRecord.from_orm(model) if model is not None else None

    def create_rule(self, data: RuleInput) -> RuleRecord:
        errors = validate_rule_input(data)
        if errors:
            raise ValidationConfigError("; ".join(errors))

        with self._db.session_scope() as session:
            repo = ValidationRuleRepository(session)
            # Compute default display_order as next position
            existing = repo.list_for_registration(data.workspace_registration_id)
            next_order = len(existing)

            model = repo.create(
                workspace_registration_id=data.workspace_registration_id,
                rule_name=data.rule_name,
                enabled=data.enabled,
                target_type=data.target_type,
                table_name=data.table_name,
                column_name=data.column_name,
                measure_name=data.measure_name,
                validation_type=data.validation_type,
                config=data.config,
                display_order=data.display_order if data.display_order > 0 else next_order,
            )
            return RuleRecord.from_orm(model)

    def update_rule(self, rule_id: int, data: RuleInput) -> RuleRecord:
        errors = validate_rule_input(data)
        if errors:
            raise ValidationConfigError("; ".join(errors))

        with self._db.session_scope() as session:
            repo = ValidationRuleRepository(session)
            model = repo.update(
                rule_id,
                rule_name=data.rule_name,
                enabled=data.enabled,
                target_type=data.target_type,
                table_name=data.table_name,
                column_name=data.column_name,
                measure_name=data.measure_name,
                validation_type=data.validation_type,
                config=data.config,
            )
            return RuleRecord.from_orm(model)

    def duplicate_rule(self, rule_id: int) -> RuleRecord:
        """Duplicate an existing rule with its full configuration (BRD 5.2)."""
        with self._db.session_scope() as session:
            repo = ValidationRuleRepository(session)
            existing = repo.get_by_id(rule_id)
            if existing is None:
                raise PersistenceError(f"Cannot duplicate: Rule {rule_id} not found.")

            try:
                cfg = json.loads(existing.config_json or "{}")
            except Exception:
                cfg = {}

            # Create duplicate
            new_rule = repo.create(
                workspace_registration_id=existing.workspace_registration_id,
                rule_name=f"{existing.rule_name} (Copy)",
                enabled=existing.enabled,
                target_type=existing.target_type,
                table_name=existing.table_name,
                column_name=existing.column_name,
                measure_name=existing.measure_name,
                validation_type=existing.validation_type,
                config=cfg,
                display_order=existing.display_order + 1,
            )
            # Re-index all rules placing the new copy directly after existing
            all_existing = repo.list_for_registration(existing.workspace_registration_id)
            ordered_ids: list[int] = []
            for r in all_existing:
                if r.id == new_rule.id:
                    continue
                ordered_ids.append(r.id)
                if r.id == existing.id:
                    ordered_ids.append(new_rule.id)
            repo.reorder(ordered_ids)
            return RuleRecord.from_orm(new_rule)

    def delete_rule(self, rule_id: int) -> bool:
        with self._db.session_scope() as session:
            repo = ValidationRuleRepository(session)
            rule = repo.get_by_id(rule_id)
            if rule is None:
                return False
            ws_id = rule.workspace_registration_id
            deleted = repo.delete(rule_id)
            if deleted:
                # Re-index remaining rules
                remaining = repo.list_for_registration(ws_id)
                repo.reorder([r.id for r in remaining])
            return deleted

    def toggle_enabled(self, rule_id: int) -> RuleRecord:
        with self._db.session_scope() as session:
            repo = ValidationRuleRepository(session)
            rule = repo.get_by_id(rule_id)
            if rule is None:
                raise PersistenceError(f"Rule {rule_id} not found.")
            updated = repo.update(rule_id, enabled=not rule.enabled)
            return RuleRecord.from_orm(updated)

    def reorder_rules(self, workspace_registration_id: int, ordered_rule_ids: list[int]) -> None:
        """Reorder rules for a registration and persist positions in SQLite."""
        with self._db.session_scope() as session:
            repo = ValidationRuleRepository(session)
            repo.reorder(ordered_rule_ids)
