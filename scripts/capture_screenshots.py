"""Script to generate showcase screenshots for documentation and README.md."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
import sys

# Ensure repository root is on Python sys.path
REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from PySide6.QtCore import QPoint, QRect, Qt
from PySide6.QtGui import QFontMetrics, QPainter, QPixmap
from PySide6.QtWidgets import QApplication, QWidget

from app.auth.msal_auth import AuthAccount, AuthStateSnapshot, AuthStatus
from app.bootstrap import bootstrap_application
from app.core.status import NotificationLevel, RefreshStatus, ValidationStatus
from app.database.models import ValidationResult, ValidationRun
from app.services.compare_service import compare_validation_runs
from app.services.sheet_service import (
    VALIDATION_TYPE_ANOMALY,
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


def apply_email_privacy_blur(pixmap: QPixmap, window: QWidget) -> QPixmap:
    """Apply a frosted privacy blur over the email portion in the banner and sidebar."""
    img = pixmap.toImage()

    # 1. Blur the email in details_label of auth_banner (only on Home page)
    if getattr(window, "_current_page_key", "") == "home":
        headline = getattr(getattr(window, "home_page", None), "auth_banner", None)
        if headline is not None and hasattr(headline, "details_label") and headline.isVisible():
            dl = headline.details_label
            pos = dl.mapTo(window, QPoint(0, 0))
            fm = QFontMetrics(dl.font())
            text = dl.text()
            if "(" in text and ")" in text:
                start_idx = text.find("(")
                end_idx = text.find(")") + 1
                prefix_w = fm.horizontalAdvance(text[:start_idx])
                email_w = fm.horizontalAdvance(text[start_idx:end_idx]) + 8
                blur_rect = QRect(pos.x() + prefix_w - 2, pos.y(), email_w, max(1, dl.height()))

                sub = img.copy(blur_rect)
                if sub.width() > 0 and sub.height() > 0:
                    small = sub.scaled(
                        max(1, sub.width() // 8),
                        max(1, sub.height() // 8),
                        Qt.AspectRatioMode.IgnoreAspectRatio,
                        Qt.TransformationMode.SmoothTransformation,
                    )
                    blurred = small.scaled(
                        sub.width(),
                        sub.height(),
                        Qt.AspectRatioMode.IgnoreAspectRatio,
                        Qt.TransformationMode.SmoothTransformation,
                    )
                    p = QPainter(img)
                    p.drawImage(blur_rect.topLeft(), blurred)
                    p.end()

    # 2. Blur the sidebar email label
    sidebar_email = getattr(window, "_sidebar_user_email", None)
    if sidebar_email is not None and sidebar_email.isVisible():
        pos = sidebar_email.mapTo(window, QPoint(0, 0))
        blur_rect = QRect(pos.x() - 2, pos.y(), sidebar_email.width() + 4, max(1, sidebar_email.height()))
        sub = img.copy(blur_rect)
        if sub.width() > 0 and sub.height() > 0:
            small = sub.scaled(
                max(1, sub.width() // 8),
                max(1, sub.height() // 8),
                Qt.AspectRatioMode.IgnoreAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            blurred = small.scaled(
                sub.width(),
                sub.height(),
                Qt.AspectRatioMode.IgnoreAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            p = QPainter(img)
            p.drawImage(blur_rect.topLeft(), blurred)
            p.end()

    return QPixmap.fromImage(img)


def main() -> None:
    demo_dir = Path("docs/screenshots/demo_data")
    import shutil
    shutil.rmtree(demo_dir, ignore_errors=True)
    demo_dir.mkdir(parents=True, exist_ok=True)

    ctx = bootstrap_application(data_dir=demo_dir, install_hooks=False, auto_restore_auth=False)
    app = ctx.qt_app
    window = ctx.window
    db = ctx.db

    out_dir = Path("docs/screenshots")
    out_dir.mkdir(parents=True, exist_ok=True)

    ws_name = "My Workspace"
    ws_id = "me"
    rep_name = "Zomato Analytics"
    rep_id = "1bd33d33-45e1-4463-a29a-8980e0d06066"
    ds_name = "Zomato"
    ds_id = "ea471a1a-5849-4ba0-b54b-5f624e83c383"

    # 1. Seed Validation Sheet rules with live Power BI testing units
    sheet_svc = SheetService(db)
    sheet_rows = [
        SheetRowDTO(
            sr_no=1,
            enabled=True,
            workspace_name=ws_name,
            workspace_id=ws_id,
            report_name=rep_name,
            report_id=rep_id,
            dataset_name=ds_name,
            dataset_id=ds_id,
            validation_type=VALIDATION_TYPE_NULL,
            table_name="Sheet1",
            column_name="Order_ID",
            config={"null_threshold_count": 0, "null_threshold_pct": 0.0},
            rule_name="Sheet1[Order_ID] Null / Blank Check",
        ),
        SheetRowDTO(
            sr_no=2,
            enabled=True,
            workspace_name=ws_name,
            workspace_id=ws_id,
            report_name=rep_name,
            report_id=rep_id,
            dataset_name=ds_name,
            dataset_id=ds_id,
            validation_type=VALIDATION_TYPE_DUPLICATE,
            table_name="Sheet1",
            column_name="Order_ID",
            config={"duplicate_threshold_count": 0},
            rule_name="Sheet1[Order_ID] Duplicate Row Check",
        ),
        SheetRowDTO(
            sr_no=3,
            enabled=True,
            workspace_name=ws_name,
            workspace_id=ws_id,
            report_name=rep_name,
            report_id=rep_id,
            dataset_name=ds_name,
            dataset_id=ds_id,
            validation_type=VALIDATION_TYPE_ROW_COUNT,
            table_name="Sheet1",
            config={"min_row_count": 10000, "max_row_count": 10000},
            rule_name="Sheet1 Row Count Check (10,000 rows)",
        ),
        SheetRowDTO(
            sr_no=4,
            enabled=True,
            workspace_name=ws_name,
            workspace_id=ws_id,
            report_name=rep_name,
            report_id=rep_id,
            dataset_name=ds_name,
            dataset_id=ds_id,
            validation_type=VALIDATION_TYPE_DAX_MEASURE,
            measure_name="Discount Utilization (%)",
            config={"expected_value_str": "49.91", "max_percentage_deviation": 10.0},
            rule_name="[Discount Utilization (%)] DAX Measure Check",
        ),
        SheetRowDTO(
            sr_no=5,
            enabled=True,
            workspace_name=ws_name,
            workspace_id=ws_id,
            report_name=rep_name,
            report_id=rep_id,
            dataset_name=ds_name,
            dataset_id=ds_id,
            validation_type=VALIDATION_TYPE_ANOMALY,
            table_name="Sheet1",
            column_name="Order_Amount",
            filter_1="'Sheet1'[Cuisine] = \"Indian\"",
            config={
                "aggregation_func": "SUM",
                "min_baseline": 100000.0,
                "max_baseline": 10000000.0,
                "comparison_method": "threshold_only",
            },
            rule_name="Sheet1[Order_Amount] Baseline & % Change Check",
        ),
        SheetRowDTO(
            sr_no=6,
            enabled=True,
            workspace_name=ws_name,
            workspace_id=ws_id,
            report_name=rep_name,
            report_id=rep_id,
            dataset_name=ds_name,
            dataset_id=ds_id,
            validation_type=VALIDATION_TYPE_LATEST_DATE,
            table_name="Sheet1",
            column_name="Order_Date",
            config={"max_age_days": 730, "disallow_future_dates": False},
            rule_name="Sheet1[Order_Date] Date Freshness Check",
        ),
        SheetRowDTO(
            sr_no=7,
            enabled=True,
            workspace_name=ws_name,
            workspace_id=ws_id,
            report_name=rep_name,
            report_id=rep_id,
            dataset_name=ds_name,
            dataset_id=ds_id,
            validation_type=VALIDATION_TYPE_REFRESH,
            config={"max_age_days": 300},
            rule_name="Power BI Dataset Scheduled Refresh SLA",
        ),
    ]
    saved_rows = sheet_svc.save_all_rows(sheet_rows)
    reg_id = saved_rows[0].workspace_registration_id

    # 2. Seed 3 Historical Runs reflecting live test outcomes
    now = datetime.now(timezone.utc)
    with db.session_scope() as session:
        # Run 1 (2 days ago): All Passed
        run1 = ValidationRun(
            workspace_registration_id=reg_id,
            overall_status="PASS",
            passed_count=7,
            failed_count=0,
            warning_count=0,
            error_count=0,
            duration_ms=1210,
            app_version="1.0.0",
            started_at=now - timedelta(days=2),
            completed_at=now - timedelta(days=2) + timedelta(seconds=1),
        )
        session.add(run1)
        session.flush()

        # Run 2 (yesterday): Baseline Run (All 7 Passed)
        run2 = ValidationRun(
            workspace_registration_id=reg_id,
            overall_status="PASS",
            passed_count=7,
            failed_count=0,
            warning_count=0,
            error_count=0,
            duration_ms=1260,
            app_version="1.0.0",
            started_at=now - timedelta(days=1),
            completed_at=now - timedelta(days=1) + timedelta(seconds=1),
        )
        session.add(run2)
        session.flush()

        # Run 3 (latest): Target Run with 6 PASS, 1 WARNING (Refresh SLA Warning)
        run3 = ValidationRun(
            workspace_registration_id=reg_id,
            overall_status="WARNING",
            passed_count=6,
            failed_count=0,
            warning_count=1,
            error_count=0,
            duration_ms=1340,
            app_version="1.0.0",
            started_at=now - timedelta(hours=1),
            completed_at=now - timedelta(hours=1) + timedelta(seconds=1),
        )
        session.add(run3)
        session.flush()

        # Seed Run 3 Results (Matches actual live test execution results)
        res3_list = [
            (saved_rows[0].row_id, "PASS", "0 blanks / 10,000 rows (0.0%)", "<= 0 blanks (0.0%)", "0.0%", "Null check passed: 0 blanks / 10,000 rows (0.0%)."),
            (saved_rows[1].row_id, "PASS", "0 duplicates / 10,000 rows (0.0%)", "<= 0 duplicates (0.0%)", "0.0%", "Duplicate check passed: 0 duplicates / 10,000 rows (0.0%) on (Order_ID)."),
            (saved_rows[2].row_id, "PASS", "10,000 rows", "10,000 rows (baseline)", "0.0%", "Table row count passed: 10,000 rows matches baseline."),
            (saved_rows[3].row_id, "PASS", "49.91", "49.91 (+/- 10.0%)", "0.0%", "Measure 'Sheet1'[Discount Utilization (%)] passed: 49.91 within target baseline."),
            (saved_rows[4].row_id, "PASS", "1,505,604.74", ">= 100,000.00 and <= 10,000,000.00", "In range", "Anomaly check passed for SUM('Sheet1'[Order_Amount]): 1,505,604.74 satisfies baseline thresholds."),
            (saved_rows[5].row_id, "PASS", "2025-01-16 00:00:00 UTC", "<= 730 days old", "Fresh", "Latest date check passed: 2025-01-16 00:00:00 UTC within SLA."),
            (saved_rows[6].row_id, "WARNING", "No refresh history", "Status = Completed, Age <= 7200h", "Warning", "No refresh history found for this dataset (personal workspace)."),
        ]
        for rid, st, act, exp, dev, summ in res3_list:
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

        # Seed Run 2 Results (All Passed)
        res2_list = [
            (saved_rows[0].row_id, "PASS", "0 blanks / 10,000 rows", "<= 0 blanks", "0.0%", "Passed"),
            (saved_rows[1].row_id, "PASS", "0 duplicates", "<= 0 duplicates", "0.0%", "Passed"),
            (saved_rows[2].row_id, "PASS", "10,000 rows", "10,000 rows", "0.0%", "Passed"),
            (saved_rows[3].row_id, "PASS", "49.88", "49.91 (+/- 10.0%)", "-0.06%", "Passed"),
            (saved_rows[4].row_id, "PASS", "1,502,300.10", ">= 100,000.00 and <= 10,000,000.00", "In range", "Passed"),
            (saved_rows[5].row_id, "PASS", "2025-01-16 00:00:00 UTC", "<= 730 days old", "Fresh", "Passed"),
            (saved_rows[6].row_id, "PASS", "Completed (Duration: 18s)", "Completed", "0s", "Passed"),
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

    window.resize(1340, 860)

    # Set authenticated user profile with anonymized generic enterprise identity
    window.apply_auth_state(
        AuthStateSnapshot(
            status=AuthStatus.AUTHENTICATED,
            account=AuthAccount(
                home_account_id="enterprise-admin-account",
                display_name="Enterprise Administrator",
                username="admin@contoso.com",
                tenant_id="contoso-tenant-guid",
            ),
            client_id_configured=True,
        )
    )

    # Synchronize Home Page
    home = window.home_page
    home.auth_banner.set_workspace_access_label("My Workspace - Contributor")
    home.reload_registered_models()

    # Update Home refresh monitoring card
    home.home_attempt_start.setText("Start: Today, 04:12:00 UTC")
    home.home_attempt_duration.setText("Duration: 15 ms")
    home.home_success_time.setText("Personal Workspace Model")
    home.home_success_age.setText("Status: Unscheduled")
    home.home_success_duration.setText("Duration: N/A")
    home.home_reliability_rate.setText("100.0%")
    home.home_reliability_detail.setText("Manual Direct Publish (Cloud Sync Active)")

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
    pm_home = apply_email_privacy_blur(window.grab(), window)
    pm_home.save(str(out_dir / "01_dashboard_home.png"))
    print("[+] Saved 01_dashboard_home.png")

    # 2. Capture Validation Sheet Page
    window.navigate_to("sheet_settings")
    window.sheet_settings_page.reload_sheet()
    app.processEvents()
    pm_sheet = apply_email_privacy_blur(window.grab(), window)
    pm_sheet.save(str(out_dir / "02_validation_sheet.png"))
    print("[+] Saved 02_validation_sheet.png")

    # 3. Capture History Page
    window.navigate_to("history")
    window.history_page.refresh_history()
    window.history_page.runs_table.selectRow(0)
    app.processEvents()
    pm_hist = apply_email_privacy_blur(window.grab(), window)
    pm_hist.save(str(out_dir / "03_history_explorer.png"))
    print("[+] Saved 03_history_explorer.png")

    # 4. Capture Run Comparison Dialog (shows Worsened Checks KPI card)
    if len(runs) >= 2:
        cmp_dto = compare_validation_runs(runs[1], runs[0])
        cmp_dialog = RunComparisonDialog(cmp_dto, all_runs=runs)
        cmp_dialog.resize(1160, 700)
        cmp_dialog.show()
        app.processEvents()
        pm_cmp = cmp_dialog.grab()
        pm_cmp.save(str(out_dir / "04_run_comparison.png"))
        cmp_dialog.close()
        print("[+] Saved 04_run_comparison.png")

    # 5. Capture Database Maintenance Dialog
    maint_dialog = BackupMaintenanceDialog(db)
    maint_dialog.resize(780, 660)
    maint_dialog.show()
    app.processEvents()
    pm_maint = maint_dialog.grab()
    pm_maint.save(str(out_dir / "05_database_maintenance.png"))
    maint_dialog.close()
    print("[+] Saved 05_database_maintenance.png")

    # 6. Capture About Page (clean professional look)
    window.navigate_to("about")
    app.processEvents()
    pm_about = apply_email_privacy_blur(window.grab(), window)
    pm_about.save(str(out_dir / "06_about_page.png"))
    print("[+] Saved 06_about_page.png")

    window.close()
    db.dispose()
    print("[+] All showcase screenshots updated successfully.")


if __name__ == "__main__":
    main()
