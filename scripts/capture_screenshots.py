"""Script to generate showcase screenshots for documentation and README.md."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
import sys

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from app.auth.msal_auth import AuthAccount, AuthStateSnapshot, AuthStatus
from app.bootstrap import bootstrap_application
from app.core.status import NotificationLevel, RefreshStatus, ValidationStatus
from app.database.models import ValidationResult, ValidationRun
from app.services.compare_service import compare_validation_runs
from app.services.sheet_service import (
    VALIDATION_TYPE_DAX_MEASURE,
    VALIDATION_TYPE_DUPLICATE,
    VALIDATION_TYPE_LATEST_DATE,
    VALIDATION_TYPE_NULL,
    VALIDATION_TYPE_REFRESH,
    VALIDATION_TYPE_ROW_COUNT,
    SheetRowDTO,
    SheetService,
)
from app.ui.dialogs.backup_maintenance_dialog import BackupMaintenanceDialog
from app.ui.dialogs.run_comparison_dialog import RunComparisonDialog


def main() -> None:
    demo_dir = Path("docs/screenshots/demo_data")
    demo_dir.mkdir(parents=True, exist_ok=True)

    ctx = bootstrap_application(data_dir=demo_dir, install_hooks=False, auto_restore_auth=False)
    app = ctx.qt_app
    window = ctx.window
    db = ctx.db

    out_dir = Path("docs/screenshots")
    out_dir.mkdir(parents=True, exist_ok=True)

    # 1. Seed Validation Sheet rules via SheetService
    sheet_svc = SheetService(db)
    sheet_rows = [
        SheetRowDTO(
            sr_no=1,
            enabled=True,
            workspace_name="Global Enterprise Analytics",
            workspace_id="a1b2c3d4-e5f6-4a8b-9c0d-1e2f3a4b5c6d",
            report_name="Executive Sales Dashboard",
            report_id="c1c2c3c4-e5f6-4a8b-9c0d-1e2f3a4b5c6d",
            dataset_name="Sales & Financial Performance",
            dataset_id="d1d2d3d4-e5f6-4a8b-9c0d-1e2f3a4b5c6d",
            validation_type=VALIDATION_TYPE_NULL,
            table_name="Fact_SalesOrders",
            column_name="SalesOrderID",
            filter_1="'Fact_SalesOrders'[Status] = \"Shipped\"",
            config={"null_threshold_count": 0, "null_threshold_pct": 0.0},
            rule_name="Sales Orders — Primary Key Null Check",
        ),
        SheetRowDTO(
            sr_no=2,
            enabled=True,
            workspace_name="Global Enterprise Analytics",
            workspace_id="a1b2c3d4-e5f6-4a8b-9c0d-1e2f3a4b5c6d",
            report_name="Executive Sales Dashboard",
            report_id="c1c2c3c4-e5f6-4a8b-9c0d-1e2f3a4b5c6d",
            dataset_name="Sales & Financial Performance",
            dataset_id="d1d2d3d4-e5f6-4a8b-9c0d-1e2f3a4b5c6d",
            validation_type=VALIDATION_TYPE_DUPLICATE,
            table_name="Dim_Customer",
            column_name="CustomerAlternateKey",
            config={"duplicate_threshold_count": 0},
            rule_name="Customer Dimension — Unique Key Check",
        ),
        SheetRowDTO(
            sr_no=3,
            enabled=True,
            workspace_name="Global Enterprise Analytics",
            workspace_id="a1b2c3d4-e5f6-4a8b-9c0d-1e2f3a4b5c6d",
            report_name="Executive Sales Dashboard",
            report_id="c1c2c3c4-e5f6-4a8b-9c0d-1e2f3a4b5c6d",
            dataset_name="Sales & Financial Performance",
            dataset_id="d1d2d3d4-e5f6-4a8b-9c0d-1e2f3a4b5c6d",
            validation_type=VALIDATION_TYPE_LATEST_DATE,
            table_name="Fact_SalesOrders",
            column_name="OrderDate",
            filter_1="'Fact_SalesOrders'[Year] = 2024",
            config={"max_age_days": 1, "disallow_future_dates": True},
            rule_name="Order Date — Freshness SLA (24h)",
        ),
        SheetRowDTO(
            sr_no=4,
            enabled=True,
            workspace_name="Global Enterprise Analytics",
            workspace_id="a1b2c3d4-e5f6-4a8b-9c0d-1e2f3a4b5c6d",
            report_name="Executive Sales Dashboard",
            report_id="c1c2c3c4-e5f6-4a8b-9c0d-1e2f3a4b5c6d",
            dataset_name="Sales & Financial Performance",
            dataset_id="d1d2d3d4-e5f6-4a8b-9c0d-1e2f3a4b5c6d",
            validation_type=VALIDATION_TYPE_DAX_MEASURE,
            measure_name="[Net Profit Margin %]",
            filter_1="'Dates'[Year] = 2024",
            filter_2="'Geography'[Region] = \"North America\"",
            config={"expected_value_str": "0.245", "max_percentage_deviation": 5.0},
            rule_name="Net Profit Margin — Baseline DAX Check",
        ),
        SheetRowDTO(
            sr_no=5,
            enabled=True,
            workspace_name="Global Enterprise Analytics",
            workspace_id="a1b2c3d4-e5f6-4a8b-9c0d-1e2f3a4b5c6d",
            report_name="Executive Sales Dashboard",
            report_id="c1c2c3c4-e5f6-4a8b-9c0d-1e2f3a4b5c6d",
            dataset_name="Sales & Financial Performance",
            dataset_id="d1d2d3d4-e5f6-4a8b-9c0d-1e2f3a4b5c6d",
            validation_type=VALIDATION_TYPE_ROW_COUNT,
            table_name="Fact_ProductInventory",
            config={"min_row_count": 50000, "max_row_count": 2000000},
            rule_name="Product Inventory — Min Row Count SLA",
        ),
        SheetRowDTO(
            sr_no=6,
            enabled=True,
            workspace_name="Global Enterprise Analytics",
            workspace_id="a1b2c3d4-e5f6-4a8b-9c0d-1e2f3a4b5c6d",
            report_name="Executive Sales Dashboard",
            report_id="c1c2c3c4-e5f6-4a8b-9c0d-1e2f3a4b5c6d",
            dataset_name="Sales & Financial Performance",
            dataset_id="d1d2d3d4-e5f6-4a8b-9c0d-1e2f3a4b5c6d",
            validation_type=VALIDATION_TYPE_REFRESH,
            config={"max_age_days": 1},
            rule_name="Power BI Dataset Scheduled Refresh SLA",
        ),
    ]
    saved_rows = sheet_svc.save_all_rows(sheet_rows)
    reg_id = saved_rows[0].workspace_registration_id

    # 2. Seed 3 Historical Runs
    now = datetime.now(timezone.utc)
    with db.session_scope() as session:
        run1 = ValidationRun(
            workspace_registration_id=reg_id,
            overall_status="PASS",
            passed_count=6,
            failed_count=0,
            warning_count=0,
            error_count=0,
            duration_ms=842,
            app_version="1.0.0",
            started_at=now - timedelta(days=2),
            completed_at=now - timedelta(days=2) + timedelta(seconds=1),
        )
        session.add(run1)
        session.flush()

        run2 = ValidationRun(
            workspace_registration_id=reg_id,
            overall_status="PASS",
            passed_count=5,
            failed_count=0,
            warning_count=1,
            error_count=0,
            duration_ms=920,
            app_version="1.0.0",
            started_at=now - timedelta(days=1),
            completed_at=now - timedelta(days=1) + timedelta(seconds=1),
        )
        session.add(run2)
        session.flush()

        run3 = ValidationRun(
            workspace_registration_id=reg_id,
            overall_status="WARNING",
            passed_count=4,
            failed_count=1,
            warning_count=1,
            error_count=0,
            duration_ms=1150,
            app_version="1.0.0",
            started_at=now - timedelta(hours=2),
            completed_at=now - timedelta(hours=2) + timedelta(seconds=1),
        )
        session.add(run3)
        session.flush()

        # Seed Run 3 Results
        res_list = [
            (saved_rows[0].row_id, "PASS", "0 nulls (0.0%)", "<= 0 count", "0.0%", "Passed: 0 null records detected in 'Fact_SalesOrders[SalesOrderID]'."),
            (saved_rows[1].row_id, "PASS", "0 duplicate keys", "0 duplicates allowed", "0", "Passed: Primary key uniqueness intact across 85,000 customer records."),
            (saved_rows[2].row_id, "FAIL", "2026-11-17 21:00:00 (Age: 51.2h)", "Max allowed age: 24h", "+27.2h stale", "Failed SLA: Latest transaction date is 51.2 hours old (SLA threshold is 24.0 hours)."),
            (saved_rows[3].row_id, "WARNING", "0.228 (-6.9% deviation)", "0.245 (+/- 5.0%)", "-6.9%", "Warning: Measure [Net Profit Margin %] evaluated to 22.8% (expected 24.5% +/- 5.0%)."),
            (saved_rows[4].row_id, "PASS", "318,450 rows", "50,000 - 2,000,000 rows", "Within range", "Passed: Table 'Fact_ProductInventory' contains 318,450 rows."),
            (saved_rows[5].row_id, "PASS", "Completed (Duration: 2m 14s)", "Completed status within 24h", "0s", "Passed: Latest dataset refresh completed successfully in 2m 14s."),
        ]
        for rid, st, act, exp, dev, summ in res_list:
            session.add(
                ValidationResult(
                    validation_run_id=run3.id,
                    validation_rule_id=rid,
                    status=st,
                    actual_value=act,
                    expected_value=exp,
                    deviation=dev,
                    result_summary=summ,
                    started_at=run3.started_at,
                    completed_at=run3.completed_at,
                )
            )

        # Seed Run 2 Results
        res2_list = [
            (saved_rows[0].row_id, "PASS", "0 nulls", "<= 0", "0", "Passed"),
            (saved_rows[1].row_id, "PASS", "0 duplicate keys", "0", "0", "Passed"),
            (saved_rows[2].row_id, "PASS", "2026-11-19 01:00:00 (Age: 18h)", "Max age: 24h", "0", "Passed"),
            (saved_rows[3].row_id, "WARNING", "0.231 (-5.7% deviation)", "0.245", "-5.7%", "Warning"),
            (saved_rows[4].row_id, "PASS", "315,200 rows", "50,000 - 2,000,000", "Within range", "Passed"),
            (saved_rows[5].row_id, "PASS", "Completed (Duration: 2m 18s)", "Completed", "0", "Passed"),
        ]
        for rid, st, act, exp, dev, summ in res2_list:
            session.add(
                ValidationResult(
                    validation_run_id=run2.id,
                    validation_rule_id=rid,
                    status=st,
                    actual_value=act,
                    expected_value=exp,
                    deviation=dev,
                    result_summary=summ,
                    started_at=run2.started_at,
                    completed_at=run2.completed_at,
                )
            )

    window.resize(1300, 840)

    # Set authenticated user profile
    window.apply_auth_state(
        AuthStateSnapshot(
            status=AuthStatus.AUTHENTICATED,
            account=AuthAccount(
                home_account_id="oid.tid",
                display_name="Enterprise BI Engineer",
                username="bi.engineer@contoso.com",
                tenant_id="contoso-corp-tid",
            ),
            client_id_configured=True,
        )
    )

    # Synchronize Home Page
    home = window.home_page
    home.auth_banner.set_workspace_access_label("Global Enterprise Analytics — Admin")
    home.reload_registered_models()

    # Update Home refresh monitoring card
    home.home_attempt_start.setText("Start: Today, 14:15:00 UTC")
    home.home_attempt_duration.setText("Duration: 2m 14s")
    home.home_success_time.setText("Today, 14:17:14 UTC")
    home.home_success_age.setText("Age: 3.2 hours ago")
    home.home_success_duration.setText("Duration: 2m 14s")
    home.home_reliability_rate.setText("98.5%")
    home.home_reliability_detail.setText("Total: 40 (Passed: 39, Failed: 1)")

    # Load runs into history page and home dashboard
    window.history_page.refresh_history()
    runs = window.history_page._runs
    if runs:
        home._display_run_summary(runs[0])

    window.show()
    app.processEvents()

    # 1. Capture Dashboard / Home Page
    window.navigate_to("home")
    app.processEvents()
    pm_home = window.grab()
    pm_home.save(str(out_dir / "01_dashboard_home.png"))
    print("[✓] Saved 01_dashboard_home.png")

    # 2. Capture Validation Sheet Page
    window.navigate_to("sheet_settings")
    window.sheet_settings_page.reload_sheet()
    app.processEvents()
    pm_sheet = window.grab()
    pm_sheet.save(str(out_dir / "02_validation_sheet.png"))
    print("[✓] Saved 02_validation_sheet.png")

    # 3. Capture History Page
    window.navigate_to("history")
    window.history_page.refresh_history()
    window.history_page.runs_table.selectRow(0)
    app.processEvents()
    pm_hist = window.grab()
    pm_hist.save(str(out_dir / "03_history_explorer.png"))
    print("[✓] Saved 03_history_explorer.png")

    # 4. Capture Run Comparison Dialog
    if len(runs) >= 2:
        cmp_dto = compare_validation_runs(runs[1], runs[0])
        cmp_dialog = RunComparisonDialog(cmp_dto, all_runs=runs)
        cmp_dialog.resize(1120, 680)
        cmp_dialog.show()
        app.processEvents()
        pm_cmp = cmp_dialog.grab()
        pm_cmp.save(str(out_dir / "04_run_comparison.png"))
        cmp_dialog.close()
        print("[✓] Saved 04_run_comparison.png")

    # 5. Capture Database Maintenance Dialog
    maint_dialog = BackupMaintenanceDialog(db)
    maint_dialog.resize(760, 640)
    maint_dialog.show()
    app.processEvents()
    pm_maint = maint_dialog.grab()
    pm_maint.save(str(out_dir / "05_database_maintenance.png"))
    maint_dialog.close()
    print("[✓] Saved 05_database_maintenance.png")

    # 6. Capture About Page
    window.navigate_to("about")
    app.processEvents()
    pm_about = window.grab()
    pm_about.save(str(out_dir / "06_about_page.png"))
    print("[✓] Saved 06_about_page.png")

    window.close()
    db.dispose()


if __name__ == "__main__":
    main()
