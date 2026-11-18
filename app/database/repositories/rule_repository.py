"""CRUD repository for row-based validation rules."""

from __future__ import annotations

import json
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.exceptions import PersistenceError
from app.database.models import ValidationRule, utc_now


class ValidationRuleRepository:
    """Repository managing `validation_rules` records."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def create(
        self,
        *,
        workspace_registration_id: int,
        rule_name: str,
        target_type: str,
        validation_type: str,
        enabled: bool = True,
        table_name: str | None = None,
        column_name: str | None = None,
        measure_name: str | None = None,
        config: dict[str, Any] | None = None,
        display_order: int = 0,
    ) -> ValidationRule:
        record = ValidationRule(
            workspace_registration_id=workspace_registration_id,
            rule_name=rule_name.strip(),
            enabled=enabled,
            target_type=target_type.strip().upper(),
            table_name=table_name.strip() if table_name and table_name.strip() else None,
            column_name=column_name.strip() if column_name and column_name.strip() else None,
            measure_name=measure_name.strip() if measure_name and measure_name.strip() else None,
            validation_type=validation_type.strip(),
            config_json=json.dumps(config or {}, sort_keys=True),
            display_order=display_order,
            created_at=utc_now(),
            updated_at=utc_now(),
        )
        self._session.add(record)
        self._session.flush()
        return record

    def get_by_id(self, rule_id: int) -> ValidationRule | None:
        return self._session.get(ValidationRule, rule_id)

    def list_for_registration(
        self,
        workspace_registration_id: int,
        *,
        enabled_only: bool = False,
    ) -> list[ValidationRule]:
        stmt = select(ValidationRule).where(
            ValidationRule.workspace_registration_id == workspace_registration_id
        )
        if enabled_only:
            stmt = stmt.where(ValidationRule.enabled.is_(True))
        stmt = stmt.order_by(ValidationRule.display_order.asc(), ValidationRule.id.asc())
        return list(self._session.scalars(stmt).all())

    def update(
        self,
        rule_id: int,
        *,
        rule_name: str | None = None,
        enabled: bool | None = None,
        target_type: str | None = None,
        table_name: str | None = ...,  # type: ignore[assignment]
        column_name: str | None = ...,  # type: ignore[assignment]
        measure_name: str | None = ...,  # type: ignore[assignment]
        validation_type: str | None = None,
        config: dict[str, Any] | None = None,
        display_order: int | None = None,
    ) -> ValidationRule:
        record = self.get_by_id(rule_id)
        if record is None:
            raise PersistenceError(f"Validation rule {rule_id} not found.")

        if rule_name is not None:
            record.rule_name = rule_name.strip()
        if enabled is not None:
            record.enabled = enabled
        if target_type is not None:
            record.target_type = target_type.strip().upper()
        if table_name is not ...:
            record.table_name = table_name.strip() if table_name and table_name.strip() else None
        if column_name is not ...:
            record.column_name = (
                column_name.strip() if column_name and column_name.strip() else None
            )
        if measure_name is not ...:
            record.measure_name = (
                measure_name.strip() if measure_name and measure_name.strip() else None
            )
        if validation_type is not None:
            record.validation_type = validation_type.strip()
        if config is not None:
            record.config_json = json.dumps(config, sort_keys=True)
        if display_order is not None:
            record.display_order = display_order
        record.updated_at = utc_now()

        self._session.flush()
        return record

    def reorder(self, ordered_rule_ids: list[int]) -> None:
        """Persist explicit rule sequence ordering."""
        for position, rule_id in enumerate(ordered_rule_ids):
            record = self.get_by_id(rule_id)
            if record is not None:
                record.display_order = position
                record.updated_at = utc_now()
        self._session.flush()

    def delete(self, rule_id: int) -> bool:
        record = self.get_by_id(rule_id)
        if record is None:
            return False
        self._session.delete(record)
        self._session.flush()
        return True
