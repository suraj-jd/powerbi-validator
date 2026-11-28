"""Render the UI against a safe snapshot of saved data; never query Power BI.

Usage: python scripts/verify_enterprise_ui.py --source-db PATH --output PATH
Set QT_QPA_PLATFORM=offscreen for unattended visual verification.
"""

from __future__ import annotations

import argparse
from contextlib import closing
from datetime import datetime
import json
from pathlib import Path
import sqlite3
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from PySide6.QtCore import QTime
from PySide6.QtGui import QFontDatabase
from PySide6.QtWidgets import QApplication

from app.auth.msal_auth import AuthAccount, AuthStateSnapshot, AuthStatus
from app.bootstrap import create_application
from app.database.db import DatabaseManager
from app.services.compare_service import compare_validation_runs
from app.services.orchestrator_service import OrchestratorService
from app.services.registry_service import RegistryService
from app.services.rule_service import RuleService
from app.services.scheduler_service import ScheduleConfig
from app.ui.dialogs.backup_maintenance_dialog import BackupMaintenanceDialog
from app.ui.dialogs.import_sheet_dialog import ImportSheetDialog
from app.ui.dialogs.result_details_dialog import ResultDetailsDialog
from app.ui.dialogs.run_comparison_dialog import RunComparisonDialog
from app.ui.dialogs.schedule_validation_dialog import ScheduleValidationDialog
from app.ui.dialogs.sheet_rule_config_dialog import SheetRuleConfigDialog
from app.ui.dialogs.teams_alert_dialog import TeamsAlertConfigDialog
from app.ui.main_window import MainWindow


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-db", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    database_path = args.output / f"saved-data-backup-{datetime.now():%Y%m%d-%H%M%S}.db"
    sql = "SELECT (SELECT COUNT(*) FROM validation_rules), (SELECT COUNT(*) FROM validation_runs), (SELECT COUNT(*) FROM validation_results)"
    with closing(sqlite3.connect(args.source_db.resolve().as_uri() + "?mode=ro", uri=True)) as source:
        before = source.execute(sql).fetchone()
        with closing(sqlite3.connect(database_path)) as target:
            source.backup(target)
    app = create_application([])
    if not QFontDatabase.families():
        for name in ("segoeui.ttf", "segoeuib.ttf", "seguisb.ttf", "consola.ttf"):
            QFontDatabase.addApplicationFont(f"C:/Windows/Fonts/{name}")
    db = DatabaseManager(database_path)
    registry, rules = RegistryService(db), RuleService(db)
    orchestrator = OrchestratorService(db, rules, None, registry_service=registry)
    window = MainWindow(db_manager=db, db_path=database_path, registry_service=registry,
                        rule_service=rules, orchestrator_service=orchestrator)
    # Only the preview process uses a sample identity. Authentication is not saved.
    window.apply_auth_state(AuthStateSnapshot(status=AuthStatus.AUTHENTICATED, account=AuthAccount(
        home_account_id="preview", display_name="Local UI preview", username="preview@example.invalid",
        tenant_id="preview", is_personal_account=False)))
    window.home_page.scheduler_service._timer.stop()
    summary = orchestrator.get_latest_run()
    report = {"source_opened_read_only": True, "counts_before": before, "screenshots": [], "dialogs": []}
    def capture(widget, name):
        app.processEvents()
        widget.grab().save(str(args.output / f"{name}.png"))
        return {"name": name, "width": widget.width(), "height": widget.height()}
    for width, height in [(900, 600), (1366, 768), (1920, 1080)]:
        window.resize(width, height)
        window.show()
        for key in ("home", "sheet_settings", "history", "about"):
            window.navigate_to(key)
            if key == "history" and window.history_page.runs_table.rowCount():
                window.history_page.runs_table.selectRow(0)
            info = capture(window, f"{key}-{width}x{height}")
            info["requested"] = [width, height]
            report["screenshots"].append(info)
    if summary and summary.results:
        constructors = [
            ("result-details", lambda: ResultDetailsDialog(summary.results[0], window)),
            ("schedule", lambda: ScheduleValidationDialog(window.home_page.scheduler_service, len(summary.results), parent=window)),
            ("teams", lambda: TeamsAlertConfigDialog(window._teams_alert_service, parent=window)),
            ("import", lambda: ImportSheetDialog(parent=window)),
            ("backup", lambda: BackupMaintenanceDialog(db, window)),
        ]
        for check_type in ("null_check", "duplicate_check", "latest_date_check", "row_count_check", "refresh_check", "dax_measure_check", "anomaly_check"):
            constructors.append((f"check-{check_type}", lambda kind=check_type: SheetRuleConfigDialog(validation_type=kind, parent=window)))
        from app.database.repositories.run_repository import ValidationRunRepository
        from app.services.orchestrator_service import ValidationRunSummaryDTO
        with db.session_scope() as session:
            repo = ValidationRunRepository(session)
            orm_runs = repo.list_runs(limit=2)
            runs = [ValidationRunSummaryDTO.from_orm(run, repo.list_results_for_run(run.id)) for run in orm_runs]
        if len(runs) == 2:
            constructors.append(("comparison", lambda: RunComparisonDialog(compare_validation_runs(runs[1], runs[0]), parent=window)))
        for name, constructor in constructors:
            dialog = constructor()
            dialog.show()
            report["dialogs"].append(capture(dialog, name))
            dialog.reject()
            dialog.deleteLater()
            app.processEvents()
    window.close()
    db.dispose()
    with closing(sqlite3.connect(args.source_db.resolve().as_uri() + "?mode=ro", uri=True)) as source:
        report["counts_after"] = source.execute(sql).fetchone()
    assert tuple(report["counts_after"]) == tuple(before)
    (args.output / "render-verification.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report))


if __name__ == "__main__":
    main()
