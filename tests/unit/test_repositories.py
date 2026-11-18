"""CRUD unit tests for all Stage 2 SQLite repositories."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from app.core.exceptions import PersistenceError
from app.core.status import RefreshStatus, ValidationStatus
from app.database.db import DatabaseManager
from app.database.repositories import (
    AppSettingsRepository,
    RefreshRecordRepository,
    ValidationRuleRepository,
    ValidationRunRepository,
    WorkspaceRegistrationRepository,
)


@pytest.fixture
def db(tmp_path: Path):
    manager = DatabaseManager(tmp_path / "repo_test.db")
    manager.run_migrations()
    try:
        yield manager
    finally:
        manager.dispose()


def test_app_settings_crud_and_secret_rejection(db: DatabaseManager) -> None:
    with db.session_scope() as session:
        repo = AppSettingsRepository(session)
        repo.set("default_timezone", "Asia/Kolkata")
        repo.set("ui_density", "compact")

        assert repo.get_value("default_timezone") == "Asia/Kolkata"
        assert len(repo.list_all()) == 2

        repo.set("default_timezone", "UTC")
        assert repo.get_value("default_timezone") == "UTC"

        assert repo.delete("ui_density") is True
        assert repo.delete("nonexistent") is False
        assert repo.get_value("ui_density", "standard") == "standard"

        for forbidden_key in ("access_token", "refresh_token", "client_secret", "user_password"):
            with pytest.raises(PersistenceError):
                repo.set(forbidden_key, "never-store-in-sqlite")


def test_workspace_registration_crud_and_duplicate_rules(db: DatabaseManager) -> None:
    ws_id = "11111111-2222-3333-4444-555555555555"
    ds_id = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"

    with db.session_scope() as session:
        repo = WorkspaceRegistrationRepository(session)

        r1 = repo.create(
            workspace_name="Analytics",
            workspace_id=ws_id,
            report_name="Report A",
            report_id="99999999-1111-2222-3333-444444444444",
            dataset_name="Shared Model",
            dataset_id=ds_id,
            is_active=True,
        )
        # Second distinct report sharing the same semantic model must be allowed (BRD Rule #8)
        r2 = repo.create(
            workspace_name="Analytics",
            workspace_id=ws_id,
            report_name="Report B",
            report_id="88888888-1111-2222-3333-444444444444",
            dataset_name="Shared Model",
            dataset_id=ds_id,
            is_active=False,
        )
        # Registration without report_id is also allowed once
        r3 = repo.create(
            workspace_name="Analytics",
            workspace_id=ws_id,
            report_name="Dataset-Only Check",
            report_id=None,
            dataset_id=ds_id,
        )

        assert len(repo.list_all()) == 3
        assert len(repo.list_active()) == 2
        assert repo.find_duplicate(workspace_id=ws_id, dataset_id=ds_id, report_id=r1.report_id)

        repo.update(r2.id, report_name="Report B Updated", is_active=True)
        assert repo.get_by_id(r2.id).report_name == "Report B Updated"
        assert len(repo.list_active()) == 3

        assert repo.delete(r3.id) is True
        assert repo.get_by_id(r3.id) is None

    # Duplicate workspace + dataset + report_id must be rejected
    with pytest.raises(PersistenceError):
        with db.session_scope() as session:
            repo = WorkspaceRegistrationRepository(session)
            repo.create(
                workspace_name="Analytics",
                workspace_id=ws_id,
                report_name="Duplicate Report A",
                report_id="99999999-1111-2222-3333-444444444444",
                dataset_id=ds_id,
            )

    # Duplicate workspace + dataset with NULL report_id must also be rejected
    with db.session_scope() as session:
        WorkspaceRegistrationRepository(session).create(
            workspace_name="Analytics",
            workspace_id=ws_id,
            report_name="Null Report 1",
            report_id=None,
            dataset_id=ds_id,
        )
    with pytest.raises(PersistenceError):
        with db.session_scope() as session:
            WorkspaceRegistrationRepository(session).create(
                workspace_name="Analytics",
                workspace_id=ws_id,
                report_name="Null Report 2",
                report_id=None,
                dataset_id=ds_id,
            )


def test_validation_rules_crud_and_reordering(db: DatabaseManager) -> None:
    with db.session_scope() as session:
        ws = WorkspaceRegistrationRepository(session).create(
            workspace_name="Finance",
            workspace_id="12345678-1234-1234-1234-1234567890ab",
            report_name="Finance Overview",
            dataset_id="abcdef12-1234-1234-1234-1234567890ab",
        )
        rules = ValidationRuleRepository(session)

        r1 = rules.create(
            workspace_registration_id=ws.id,
            rule_name="Employee Name Null Check",
            target_type="COLUMN",
            table_name="Employee Master",
            column_name="Employee Name",
            validation_type="NULL_CHECK",
            config={"max_null_pct": 0.0, "treat_whitespace_as_blank": True},
            display_order=0,
        )
        r2 = rules.create(
            workspace_registration_id=ws.id,
            rule_name="Refresh Status Check",
            target_type="MODEL",
            validation_type="REFRESH_CHECK",
            config={"expected_status": "Success", "max_age_hours": 24},
            display_order=1,
            enabled=False,
        )

        all_rules = rules.list_for_registration(ws.id)
        assert [r.id for r in all_rules] == [r1.id, r2.id]
        assert len(rules.list_for_registration(ws.id, enabled_only=True)) == 1
        assert json.loads(r1.config_json)["max_null_pct"] == 0.0

        rules.update(r2.id, enabled=True, config={"expected_status": "Success", "max_age_hours": 12})
        rules.reorder([r2.id, r1.id])

        reordered = rules.list_for_registration(ws.id)
        assert [r.id for r in reordered] == [r2.id, r1.id]
        assert json.loads(reordered[0].config_json)["max_age_hours"] == 12

        assert rules.delete(r1.id) is True
        assert len(rules.list_for_registration(ws.id)) == 1


def test_validation_runs_results_and_immutable_history_when_rule_deleted(db: DatabaseManager) -> None:
    with db.session_scope() as session:
        ws = WorkspaceRegistrationRepository(session).create(
            workspace_name="HR",
            workspace_id="22222222-1234-1234-1234-1234567890ab",
            report_name="Headcount",
            dataset_id="33333333-1234-1234-1234-1234567890ab",
        )
        rule = ValidationRuleRepository(session).create(
            workspace_registration_id=ws.id,
            rule_name="Headcount DAX Anomaly",
            target_type="MEASURE",
            measure_name="Total Employees",
            validation_type="ANOMALY_CHECK",
            config={"method": "historical_median", "allowed_deviation_pct": 10},
        )
        runs = ValidationRunRepository(session)
        run = runs.create_run(workspace_registration_id=ws.id, app_version="0.1.0")
        res = runs.add_result(
            validation_run_id=run.id,
            validation_rule_id=rule.id,
            status=ValidationStatus.PASS.value,
            actual_value="450",
            expected_value="455 +/- 10%",
            deviation="-1.1%",
            result_summary="Within historical median tolerance.",
        )
        runs.complete_run(
            run.id,
            overall_status=ValidationStatus.PASS.value,
            passed_count=1,
            failed_count=0,
            warning_count=0,
            error_count=0,
            duration_ms=1420,
        )
        run_id = run.id
        rule_id = rule.id
        res_id = res.id

    # Deleting the rule later must preserve historical run results (SET NULL)
    with db.session_scope() as session:
        assert ValidationRuleRepository(session).delete(rule_id) is True

    with db.session_scope() as session:
        runs = ValidationRunRepository(session)
        stored_run = runs.get_run(run_id)
        assert stored_run is not None
        assert stored_run.passed_count == 1
        assert stored_run.duration_ms == 1420

        stored_results = runs.list_results_for_run(run_id)
        assert len(stored_results) == 1
        assert stored_results[0].id == res_id
        assert stored_results[0].validation_rule_id is None
        assert stored_results[0].actual_value == "450"


def test_refresh_records_distinguish_latest_attempt_and_latest_success(db: DatabaseManager) -> None:
    now = datetime.now(timezone.utc)
    with db.session_scope() as session:
        ws = WorkspaceRegistrationRepository(session).create(
            workspace_name="Sales",
            workspace_id="44444444-1234-1234-1234-1234567890ab",
            report_name="Sales Summary",
            dataset_id="55555555-1234-1234-1234-1234567890ab",
        )
        repo = RefreshRecordRepository(session)

        r_ok = repo.create(
            workspace_registration_id=ws.id,
            dataset_id=ws.dataset_id,
            refresh_id="req-001",
            status=RefreshStatus.SUCCESS.value,
            start_time=now - timedelta(hours=3),
            end_time=now - timedelta(hours=2, minutes=57),
            duration_ms=180_000,
            refresh_type="Scheduled",
        )
        r_fail = repo.create(
            workspace_registration_id=ws.id,
            dataset_id=ws.dataset_id,
            refresh_id="req-002",
            status=RefreshStatus.FAILED.value,
            start_time=now - timedelta(minutes=30),
            end_time=now - timedelta(minutes=29),
            duration_ms=60_000,
            refresh_type="OnDemand",
            error_details="Gateway timeout",
        )

        latest_attempt = repo.get_latest_attempt(ws.id)
        latest_success = repo.get_latest_successful(ws.id)

        assert latest_attempt is not None and latest_attempt.id == r_fail.id
        assert latest_success is not None and latest_success.id == r_ok.id
        assert repo.delete(r_fail.id) is True
        assert repo.get_latest_attempt(ws.id).id == r_ok.id
