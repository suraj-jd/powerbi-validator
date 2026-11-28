"""Unit tests for Stage 14 export utilities, run comparisons, and database backup services."""

from __future__ import annotations

from datetime import datetime, timezone, timedelta
from dataclasses import replace
import csv
from pathlib import Path

import openpyxl
import pytest

from app.core.status import ValidationStatus
from app.database.db import DatabaseManager
from app.services.backup_service import (
    backup_database,
    prune_history,
    restore_database_backup,
    validate_database_backup,
)
from app.services.compare_service import compare_validation_runs
from app.services.export_service import (
    export_diagnostic_logs,
    export_run_to_csv,
    export_run_to_xlsx,
)
from app.services.orchestrator_service import (
    ValidationResultDTO,
    ValidationRunSummaryDTO,
)


def _make_sample_run(run_id: int, status: ValidationStatus, rules_status: list[ValidationStatus]) -> ValidationRunSummaryDTO:
    now = datetime(2026, 11, 19, 12, 0, 0, tzinfo=timezone.utc)
    results = []
    for i, st in enumerate(rules_status, start=1):
        results.append(
            ValidationResultDTO(
                id=i,
                validation_run_id=run_id,
                rule_id=i,
                rule_name=f"Rule {i}",
                validation_type="null_check",
                target_type="COLUMN",
                target_display=f"Table[Col{i}]",
                status=st,
                actual_value="0 blanks",
                expected_value="<= 0 blanks",
                deviation="None",
                result_summary=f"Rule {i} {st.value}",
                detailed_message=f"Secret token: eyJhbGciOi... secret_val",
                duration_ms=50,
                started_at=now,
                completed_at=now,
            )
        )

    p_cnt = sum(1 for s in rules_status if s == ValidationStatus.PASS)
    f_cnt = sum(1 for s in rules_status if s == ValidationStatus.FAIL)
    w_cnt = sum(1 for s in rules_status if s == ValidationStatus.WARNING)
    e_cnt = sum(1 for s in rules_status if s == ValidationStatus.ERROR)

    return ValidationRunSummaryDTO(
        id=run_id,
        workspace_registration_id=1,
        overall_status=status,
        passed_count=p_cnt,
        failed_count=f_cnt,
        warning_count=w_cnt,
        error_count=e_cnt,
        total_rules=len(rules_status),
        duration_ms=150,
        app_version="0.1.0",
        started_at=now,
        completed_at=now,
        results=results,
    )


# =========================================================================
# Export Service Tests
# =========================================================================

def test_export_run_to_csv(tmp_path: Path):
    run = _make_sample_run(1, ValidationStatus.FAIL, [ValidationStatus.PASS, ValidationStatus.FAIL])
    dest = tmp_path / "test_run.csv"

    out = export_run_to_csv(run, dest)
    assert out.exists()
    content = out.read_text(encoding="utf-8-sig")

    assert "# Run ID,1" in content
    assert "Rule 1,Table[Col1],COLUMN,null_check,PASS" in content
    assert "Rule 2,Table[Col2],COLUMN,null_check,FAIL" in content
    rows = list(csv.reader(content.splitlines()))
    header_index = next(i for i, row in enumerate(rows) if row and row[0] == "Result ID")
    date_column = rows[header_index].index("Validated At (UTC)")
    assert rows[header_index + 1][date_column] == "2026-11-19 12:00:00 UTC"


def test_export_run_to_xlsx(tmp_path: Path):
    run = _make_sample_run(2, ValidationStatus.PASS, [ValidationStatus.PASS, ValidationStatus.PASS])
    dest = tmp_path / "test_run.xlsx"

    out = export_run_to_xlsx(run, dest)
    assert out.exists()

    wb = openpyxl.load_workbook(out)
    assert "Validation Results" in wb.sheetnames
    ws = wb["Validation Results"]
    assert "Power BI Validation Tool" in ws["A1"].value
    # Status should be PASS
    assert ws["A8"].value == "Status" or ws["A10"].value == "Status" or any(cell.value == "Status" for cell in ws["A"])
    date_header = next(cell for row in ws for cell in row if cell.value == "Validated At (UTC)")
    assert ws.cell(date_header.row + 1, date_header.column).value == "2026-11-19 12:00:00 UTC"
    wb.close()


@pytest.mark.parametrize("tz", [None, timezone.utc, timezone(timedelta(hours=5, minutes=30))])
def test_validated_date_uses_completion_time_and_normalizes_utc(tz):
    result = _make_sample_run(1, ValidationStatus.PASS, [ValidationStatus.PASS]).results[0]
    completed = datetime(2026, 11, 28, 15, 47, 22, tzinfo=tz)
    result = replace(result, completed_at=completed)
    expected = "2026-11-28 10:17:22 UTC" if tz not in (None, timezone.utc) else "2026-11-28 15:47:22 UTC"
    assert result.validated_at_display == expected


def test_export_diagnostic_logs(tmp_path: Path):
    log_dir = tmp_path / "logs"
    log_dir.mkdir()
    sample_log = log_dir / "app.log"
    sample_log.write_text("INFO: User login successful. Token: eyJhbGciOiJIUzI1Ni... Bearer secret123", encoding="utf-8")

    dest = tmp_path / "diagnostics.txt"
    out = export_diagnostic_logs(log_dir, dest, extra_metadata={"Client ID": "12345"})

    assert out.exists()
    content = out.read_text(encoding="utf-8")
    assert "=== Power BI Validation Tool Diagnostic Report ===" in content
    assert "Bearer [REDACTED" in content or "[REDACTED]" in content


# =========================================================================
# Comparison Service Tests
# =========================================================================

def test_compare_validation_runs_regression_and_improvement():
    # Run 1: Rule 1 PASS, Rule 2 FAIL
    run1 = _make_sample_run(1, ValidationStatus.FAIL, [ValidationStatus.PASS, ValidationStatus.FAIL])
    # Run 2: Rule 1 FAIL (regression!), Rule 2 PASS (improvement!)
    run2 = _make_sample_run(2, ValidationStatus.FAIL, [ValidationStatus.FAIL, ValidationStatus.PASS])

    cmp = compare_validation_runs(run1, run2)
    assert cmp.run_a.id == 1
    assert cmp.run_b.id == 2
    assert cmp.regressions_count == 1
    assert cmp.improvements_count == 1
    assert cmp.unchanged_count == 0

    rule1_cmp = next(c for c in cmp.rule_comparisons if c.rule_name == "Rule 1")
    assert rule1_cmp.change_type == "REGRESSION"
    assert rule1_cmp.status_a == ValidationStatus.PASS
    assert rule1_cmp.status_b == ValidationStatus.FAIL

    rule2_cmp = next(c for c in cmp.rule_comparisons if c.rule_name == "Rule 2")
    assert rule2_cmp.change_type == "IMPROVEMENT"
    assert rule2_cmp.status_a == ValidationStatus.FAIL
    assert rule2_cmp.status_b == ValidationStatus.PASS


def test_compare_validation_runs_up_to_4_runs_and_csv_export(tmp_path: Path):
    run1 = _make_sample_run(1, ValidationStatus.FAIL, [ValidationStatus.PASS, ValidationStatus.FAIL])
    run2 = _make_sample_run(2, ValidationStatus.FAIL, [ValidationStatus.FAIL, ValidationStatus.PASS])
    run3 = _make_sample_run(3, ValidationStatus.PASS, [ValidationStatus.PASS, ValidationStatus.PASS])
    run4 = _make_sample_run(4, ValidationStatus.WARNING, [ValidationStatus.WARNING, ValidationStatus.PASS])

    # 1. 2 runs (default optional is None)
    cmp2 = compare_validation_runs(run1, run2)
    assert len(cmp2.active_runs) == 2
    assert cmp2.run_c is None
    assert cmp2.run_d is None

    # 2. 3 runs
    cmp3 = compare_validation_runs(run1, run2, run3)
    assert len(cmp3.active_runs) == 3
    assert cmp3.run_c is not None and cmp3.run_c.id == 3
    assert cmp3.run_d is None
    r1_cmp = next(c for c in cmp3.rule_comparisons if c.rule_name == "Rule 1")
    assert r1_cmp.status_c == ValidationStatus.PASS

    # 3. 4 runs
    cmp4 = compare_validation_runs(run1, run2, run3, run4)
    assert len(cmp4.active_runs) == 4
    assert cmp4.run_c.id == 3
    assert cmp4.run_d.id == 4
    r1_4 = next(c for c in cmp4.rule_comparisons if c.rule_name == "Rule 1")
    assert r1_4.status_a == ValidationStatus.PASS
    assert r1_4.status_b == ValidationStatus.FAIL
    assert r1_4.status_c == ValidationStatus.PASS
    assert r1_4.status_d == ValidationStatus.WARNING

    # 4. CSV export with 4 runs
    csv_file = tmp_path / "comp_4runs.csv"
    from app.services.compare_service import export_comparison_to_csv
    out = export_comparison_to_csv(cmp4, csv_file)
    assert out.exists()
    content = out.read_text(encoding="utf-8")
    assert "Run #1 Status,Run #2 Status,Run #3 Status,Run #4 Status" in content
    assert "Run #1 Actual,Run #2 Actual,Run #3 Actual,Run #4 Actual" in content
    assert "Run #2 Deviation" in content


# =========================================================================
# Backup & Pruning Tests
# =========================================================================

def test_database_backup_and_restore_cycle(tmp_path: Path):
    db_file = tmp_path / "original.db"
    db = DatabaseManager(db_file)
    db.run_migrations()

    # 1. Backup
    backup_file = tmp_path / "backup.db"
    backed_up = backup_database(db, backup_file)
    assert backed_up.exists()
    assert backed_up.stat().st_size > 0

    # 2. Validate
    assert validate_database_backup(backup_file) is True

    # Validate corrupted file fails
    fake_corrupt = tmp_path / "corrupt.db"
    fake_corrupt.write_text("not a sqlite database", encoding="utf-8")
    assert validate_database_backup(fake_corrupt) is False

    # 3. Restore to new target
    restored_target = tmp_path / "restored.db"
    success = restore_database_backup(backup_file, restored_target)
    assert success is True
    assert validate_database_backup(restored_target) is True

    db.dispose()


def test_prune_history(tmp_path: Path):
    db_file = tmp_path / "prune_test.db"
    db = DatabaseManager(db_file)
    db.run_migrations()

    # Prune runs older than 30 days
    pruned = prune_history(db, 30)
    assert pruned == 0  # 0 old runs in empty db

    db.dispose()
