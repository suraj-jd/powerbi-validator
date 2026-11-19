"""Unit tests for Stage 12 Validation Orchestration service and persistence."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from app.core.exceptions import ConcurrentRunError
from app.core.status import ValidationStatus
from app.database.db import DatabaseManager
from app.database.repositories.workspace_repository import WorkspaceRegistrationRepository
from app.integrations.powerbi.dax_client import DaxQueryClient, DaxQueryResult
from app.services.orchestrator_service import (
    OrchestratorService,
    calculate_overall_status,
)
from app.services.rule_service import (
    RuleInput,
    RuleService,
    VALIDATION_TYPE_NULL,
    VALIDATION_TYPE_ROW_COUNT,
)


@pytest.fixture
def test_db(tmp_path):
    db = DatabaseManager(tmp_path / "orchestrator_test.db")
    db.run_migrations()
    try:
        yield db
    finally:
        db.dispose()


@pytest.fixture
def mock_dax_client() -> DaxQueryClient:
    client = MagicMock(spec=DaxQueryClient)
    # Default success response for queries
    client.execute_raw_dax.return_value = DaxQueryResult.from_raw_rows(
        [{"[TotalRows]": 1000, "[BlankCount]": 0, "[RowCount]": 1000}], duration_ms=25
    )
    return client


def _create_registration_and_rules(db: DatabaseManager) -> tuple[int, list[int]]:
    with db.session_scope() as session:
        reg = WorkspaceRegistrationRepository(session).create(
            workspace_id="ws-123",
            workspace_name="Test Workspace",
            dataset_id="ds-456",
            dataset_name="Test Dataset",
            report_name="Test Report",
            is_active=True,
        )
        reg_id = reg.id

    rule_svc = RuleService(db)
    r1 = rule_svc.create_rule(
        RuleInput(
            workspace_registration_id=reg_id,
            rule_name="Sales Amount Not Null",
            target_type="COLUMN",
            validation_type=VALIDATION_TYPE_NULL,
            table_name="Sales",
            column_name="Amount",
            config={"allowed_blank_count": 0},
        )
    )
    r2 = rule_svc.create_rule(
        RuleInput(
            workspace_registration_id=reg_id,
            rule_name="Sales Row Count",
            target_type="COLUMN",
            validation_type=VALIDATION_TYPE_ROW_COUNT,
            table_name="Sales",
            config={"baseline_method": "fixed", "baseline_value": 1000, "allowed_deviation_pct": 5.0},
        )
    )
    return reg_id, [r1.id, r2.id]


# =========================================================================
# Status Precedence Tests
# =========================================================================

def test_calculate_overall_status_precedence():
    # FAIL beats everything
    assert calculate_overall_status([ValidationStatus.PASS, ValidationStatus.FAIL, ValidationStatus.ERROR]) == ValidationStatus.FAIL
    # ERROR beats WARNING and PASS
    assert calculate_overall_status([ValidationStatus.PASS, ValidationStatus.ERROR, ValidationStatus.WARNING]) == ValidationStatus.ERROR
    # WARNING beats PASS
    assert calculate_overall_status([ValidationStatus.PASS, ValidationStatus.WARNING]) == ValidationStatus.WARNING
    # All PASS -> PASS
    assert calculate_overall_status([ValidationStatus.PASS, ValidationStatus.PASS]) == ValidationStatus.PASS
    # Empty -> WARNING
    assert calculate_overall_status([]) == ValidationStatus.WARNING


# =========================================================================
# Orchestrator Run Tests
# =========================================================================

def test_orchestrator_runs_all_rules_and_persists(test_db, mock_dax_client):
    reg_id, rule_ids = _create_registration_and_rules(test_db)
    rule_svc = RuleService(test_db)
    orchestrator = OrchestratorService(test_db, rule_svc, mock_dax_client)

    progress_log = []

    def on_progress(cur, total, name, res):
        progress_log.append((cur, total, name, res.status if res else None))

    summary = orchestrator.run_validation(
        reg_id,
        workspace_id="ws-123",
        dataset_id="ds-456",
        on_progress=on_progress,
    )

    assert summary.workspace_registration_id == reg_id
    assert summary.overall_status == ValidationStatus.PASS
    assert summary.passed_count == 2
    assert summary.failed_count == 0
    assert summary.total_rules == 2
    assert len(summary.results) == 2
    assert len(progress_log) == 4  # 2 before-eval, 2 after-eval calls

    # Verify run persisted in SQLite
    persisted = orchestrator.get_run_summary(summary.id)
    assert persisted is not None
    assert persisted.id == summary.id
    assert persisted.overall_status == ValidationStatus.PASS
    assert len(persisted.results) == 2


def test_orchestrator_continues_on_rule_failure(test_db):
    reg_id, rule_ids = _create_registration_and_rules(test_db)
    rule_svc = RuleService(test_db)

    # Mock DAX client that fails first rule (returns 100 blanks for Null check)
    # but passes second rule (RowCount = 1000)
    client = MagicMock(spec=DaxQueryClient)
    client.execute_raw_dax.side_effect = [
        # Null check query returns 100 blanks -> FAIL
        DaxQueryResult.from_raw_rows([{"[TotalRows]": 1000, "[BlankCount]": 100}], duration_ms=20),
        # Row count query returns 1000 rows -> PASS
        DaxQueryResult.from_raw_rows([{"[RowCount]": 1000}], duration_ms=20),
    ]

    orchestrator = OrchestratorService(test_db, rule_svc, client)
    summary = orchestrator.run_validation(reg_id, workspace_id="ws-123", dataset_id="ds-456")

    # Overall should be FAIL because rule 1 failed, but rule 2 was still evaluated!
    assert summary.overall_status == ValidationStatus.FAIL
    assert summary.passed_count == 1
    assert summary.failed_count == 1
    assert len(summary.results) == 2
    assert summary.results[0].status == ValidationStatus.FAIL
    assert summary.results[1].status == ValidationStatus.PASS


def test_orchestrator_prevents_concurrent_runs(test_db, mock_dax_client):
    reg_id, _ = _create_registration_and_rules(test_db)
    rule_svc = RuleService(test_db)
    orchestrator = OrchestratorService(test_db, rule_svc, mock_dax_client)

    # Manually add to active registrations to simulate concurrency
    orchestrator._active_registrations.add(reg_id)

    with pytest.raises(ConcurrentRunError, match="already in progress"):
        orchestrator.run_validation(reg_id, workspace_id="ws-123", dataset_id="ds-456")

    # Discard lock and verify runs can execute
    orchestrator._active_registrations.discard(reg_id)
    summary = orchestrator.run_validation(reg_id, workspace_id="ws-123", dataset_id="ds-456")
    assert summary.overall_status == ValidationStatus.PASS


def test_orchestrator_cancellation_support(test_db, mock_dax_client):
    reg_id, _ = _create_registration_and_rules(test_db)
    rule_svc = RuleService(test_db)
    orchestrator = OrchestratorService(test_db, rule_svc, mock_dax_client)

    # Cancel after 1 rule
    call_count = 0

    def cancel_after_first():
        nonlocal call_count
        call_count += 1
        return call_count > 1

    summary = orchestrator.run_validation(
        reg_id,
        workspace_id="ws-123",
        dataset_id="ds-456",
        is_cancelled_fn=cancel_after_first,
    )

    # Only 1 rule should have executed before cancellation
    assert len(summary.results) == 1
    assert summary.passed_count == 1


def test_orchestrator_run_sheet_validation(test_db, mock_dax_client):
    reg_id, _ = _create_registration_and_rules(test_db)
    rule_svc = RuleService(test_db)
    orchestrator = OrchestratorService(test_db, rule_svc, mock_dax_client)

    summary = orchestrator.run_sheet_validation()

    assert summary is not None
    assert summary.total_rules == 2
    assert summary.passed_count == 2
    assert summary.overall_status == ValidationStatus.PASS
    assert len(summary.results) == 2

    # Check get_latest_run returns this completed run
    latest = orchestrator.get_latest_run()
    assert latest is not None
    assert latest.id == summary.id
    assert latest.overall_status == ValidationStatus.PASS
