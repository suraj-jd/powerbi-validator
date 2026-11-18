"""Unit tests for Stage 7 RuleService and rule configuration logic."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.core.exceptions import PersistenceError, ValidationConfigError
from app.database.db import DatabaseManager
from app.integrations.file_import import RegistrationInput
from app.services.registry_service import RegistryService
from app.services.rule_service import (
    TARGET_TYPE_COLUMN,
    TARGET_TYPE_MEASURE,
    TARGET_TYPE_MODEL,
    VALIDATION_TYPE_ANOMALY,
    VALIDATION_TYPE_DAX_MEASURE,
    VALIDATION_TYPE_DUPLICATE,
    VALIDATION_TYPE_LATEST_DATE,
    VALIDATION_TYPE_NULL,
    VALIDATION_TYPE_REFRESH,
    VALIDATION_TYPE_ROW_COUNT,
    RuleInput,
    RuleService,
    format_rule_conditions_summary,
    validate_rule_input,
)

WS_GUID = "11111111-2222-3333-4444-555555555555"
DS_GUID = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"


@pytest.fixture
def db(tmp_path: Path):
    manager = DatabaseManager(tmp_path / "test_rules.db")
    manager.run_migrations()
    try:
        yield manager
    finally:
        manager.dispose()


@pytest.fixture
def registration_id(db: DatabaseManager) -> int:
    registry = RegistryService(db)
    rec = registry.create_registration(
        RegistrationInput(
            workspace_name="Sales Workspace",
            workspace_id=WS_GUID,
            report_name="Sales Executive",
            report_id=None,
            dataset_name="Sales Model",
            dataset_id=DS_GUID,
            is_active=True,
        )
    )
    return rec.id


def test_rule_input_validation() -> None:
    # Missing name
    errs = validate_rule_input(
        RuleInput(
            workspace_registration_id=1,
            rule_name="",
            target_type=TARGET_TYPE_COLUMN,
            validation_type=VALIDATION_TYPE_NULL,
            table_name="Orders",
            column_name="OrderID",
        )
    )
    assert any("Rule name cannot be empty" in e for e in errs)

    # Column rule missing table or column
    errs_col = validate_rule_input(
        RuleInput(
            workspace_registration_id=1,
            rule_name="Null check",
            target_type=TARGET_TYPE_COLUMN,
            validation_type=VALIDATION_TYPE_NULL,
            table_name="",
            column_name="",
        )
    )
    assert any("requires a Table Name" in e for e in errs_col)
    assert any("requires a Column Name" in e for e in errs_col)

    # Measure rule missing measure
    errs_meas = validate_rule_input(
        RuleInput(
            workspace_registration_id=1,
            rule_name="Measure check",
            target_type=TARGET_TYPE_MEASURE,
            validation_type=VALIDATION_TYPE_DAX_MEASURE,
            measure_name="",
        )
    )
    assert any("requires a Measure Name" in e for e in errs_meas)

    # Refresh rule does NOT require table or column (BRD Acceptance criteria)
    errs_refresh = validate_rule_input(
        RuleInput(
            workspace_registration_id=1,
            rule_name="Model Refresh Check",
            target_type=TARGET_TYPE_MODEL,
            validation_type=VALIDATION_TYPE_REFRESH,
        )
    )
    assert len(errs_refresh) == 0

    # Incompatible check and target type
    errs_incompat = validate_rule_input(
        RuleInput(
            workspace_registration_id=1,
            rule_name="Wrong combo",
            target_type=TARGET_TYPE_MODEL,
            validation_type=VALIDATION_TYPE_NULL,
            table_name="T",
            column_name="C",
        )
    )
    assert any("not compatible" in e for e in errs_incompat)


def test_format_rule_conditions_summary() -> None:
    assert format_rule_conditions_summary(VALIDATION_TYPE_NULL, {}) == "allowed blanks = 0"
    assert (
        format_rule_conditions_summary(
            VALIDATION_TYPE_NULL,
            {"allowed_blank_count": 5, "allowed_blank_percentage": 2.5},
        )
        == "allowed blanks = 5, max 2.5%"
    )
    assert (
        format_rule_conditions_summary(
            VALIDATION_TYPE_DUPLICATE,
            {"allowed_duplicate_count": 0, "key_columns": ["ID", "Year"]},
        )
        == "allowed dups = 0 on (ID, Year)"
    )
    assert (
        format_rule_conditions_summary(
            VALIDATION_TYPE_LATEST_DATE,
            {"max_age_hours": 12},
        )
        == "freshness <= 12h"
    )
    assert (
        format_rule_conditions_summary(
            VALIDATION_TYPE_ROW_COUNT,
            {"baseline_method": "fixed", "baseline_value": 50000, "allowed_deviation_pct": 5.0},
        )
        == "baseline 50,000 (±5.0%)"
    )
    assert (
        format_rule_conditions_summary(
            VALIDATION_TYPE_DAX_MEASURE,
            {"expected_method": "min_max", "min_value": 100, "max_value": 200},
        )
        == "range [100, 200]"
    )
    assert (
        format_rule_conditions_summary(
            VALIDATION_TYPE_REFRESH,
            {"expected_status": "Completed", "max_age_hours": 24},
        )
        == "status = Completed, age <= 24h"
    )


def test_rule_service_crud_duplicate_reorder(db: DatabaseManager, registration_id: int) -> None:
    svc = RuleService(db)

    # 1. Create rules
    r1 = svc.create_rule(
        RuleInput(
            workspace_registration_id=registration_id,
            rule_name="Customer ID Not Null",
            target_type=TARGET_TYPE_COLUMN,
            validation_type=VALIDATION_TYPE_NULL,
            table_name="Customers",
            column_name="CustomerID",
            config={"allowed_blank_count": 0},
        )
    )
    assert r1.id > 0
    assert r1.rule_name == "Customer ID Not Null"
    assert r1.target_display == "Customers[CustomerID]"
    assert r1.conditions_summary == "allowed blanks = 0"

    r2 = svc.create_rule(
        RuleInput(
            workspace_registration_id=registration_id,
            rule_name="Total Revenue Baseline",
            target_type=TARGET_TYPE_MEASURE,
            validation_type=VALIDATION_TYPE_DAX_MEASURE,
            measure_name="Total Revenue",
            config={"expected_method": "fixed", "expected_value": 1000000, "allowed_deviation_pct": 5.0},
        )
    )
    assert r2.target_display == "Total Revenue"

    r3 = svc.create_rule(
        RuleInput(
            workspace_registration_id=registration_id,
            rule_name="Daily Refresh Check",
            target_type=TARGET_TYPE_MODEL,
            validation_type=VALIDATION_TYPE_REFRESH,
            config={"expected_status": "Completed", "max_age_hours": 24},
        )
    )
    assert r3.target_display == "Semantic Model"

    rules = svc.list_rules(registration_id)
    assert len(rules) == 3

    # 2. Toggle enabled
    updated_r1 = svc.toggle_enabled(r1.id)
    assert updated_r1.enabled is False
    assert len(svc.list_rules(registration_id, enabled_only=True)) == 2

    svc.toggle_enabled(r1.id)
    assert len(svc.list_rules(registration_id, enabled_only=True)) == 3

    # 3. Duplicate rule
    dup_r2 = svc.duplicate_rule(r2.id)
    assert dup_r2.id != r2.id
    assert dup_r2.rule_name == "Total Revenue Baseline (Copy)"
    assert dup_r2.config == r2.config

    rules_after_dup = svc.list_rules(registration_id)
    assert len(rules_after_dup) == 4

    # 4. Update rule
    updated_r3 = svc.update_rule(
        r3.id,
        RuleInput(
            workspace_registration_id=registration_id,
            rule_name="Hourly Refresh Check",
            target_type=TARGET_TYPE_MODEL,
            validation_type=VALIDATION_TYPE_REFRESH,
            config={"expected_status": "Completed", "max_age_hours": 1},
        ),
    )
    assert updated_r3.rule_name == "Hourly Refresh Check"
    assert updated_r3.config["max_age_hours"] == 1

    # 5. Reorder rules
    svc.reorder_rules(registration_id, [r3.id, r1.id, r2.id, dup_r2.id])
    reordered = svc.list_rules(registration_id)
    assert [r.id for r in reordered] == [r3.id, r1.id, r2.id, dup_r2.id]

    # 6. Delete rule
    assert svc.delete_rule(dup_r2.id) is True
    assert len(svc.list_rules(registration_id)) == 3
    assert svc.get_rule(dup_r2.id) is None


def test_rules_persist_across_restarts(db: DatabaseManager, registration_id: int) -> None:
    svc1 = RuleService(db)
    r = svc1.create_rule(
        RuleInput(
            workspace_registration_id=registration_id,
            rule_name="Persisted Rule",
            target_type=TARGET_TYPE_COLUMN,
            validation_type=VALIDATION_TYPE_DUPLICATE,
            table_name="Orders",
            column_name="OrderID",
            config={"allowed_duplicate_count": 0},
        )
    )
    rule_id = r.id

    # Fresh service instance reading from DB
    svc2 = RuleService(db)
    fetched = svc2.get_rule(rule_id)
    assert fetched is not None
    assert fetched.rule_name == "Persisted Rule"
    assert fetched.table_name == "Orders"
    assert fetched.column_name == "OrderID"
