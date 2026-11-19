"""UI tests for Stage 8 Power BI dataset refresh monitoring dialog and widgets."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

import pytest
from PySide6.QtCore import Qt

from app.core.status import RefreshStatus
from app.database.db import DatabaseManager
from app.integrations.powerbi.models import ParsedRefreshRecord
from app.services.refresh_service import RefreshRecordDTO, RefreshService, RefreshSummaryDTO
from app.services.registry_service import RegistrationInput, RegistryService
from app.ui.dialogs.refresh_details_dialog import RefreshDetailsDialog, make_status_pill
from app.ui.pages.home_page import HomePage
from app.ui.pages.settings_page import SettingsPage

WS_ID = "11111111-2222-3333-4444-555555555555"
DS_ID = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
RPT_ID = "12345678-1234-1234-1234-1234567890ab"


@pytest.fixture
def db(tmp_path) -> DatabaseManager:
    db_file = tmp_path / "test_refresh_ui.db"
    manager = DatabaseManager(db_file)
    manager.run_migrations()
    yield manager
    manager.dispose()


@pytest.fixture
def sample_registration(db: DatabaseManager) -> int:
    registry = RegistryService(db=db)
    rec = registry.create_registration(
        RegistrationInput(
            workspace_name="Finance Workspace",
            workspace_id=WS_ID,
            report_name="Revenue Report",
            report_id=RPT_ID,
            dataset_name="Revenue Semantic Model",
            dataset_id=DS_ID,
            is_active=True,
        )
    )
    return rec.id


def test_make_status_pill_styling(qtbot) -> None:
    pill_success = make_status_pill(RefreshStatus.SUCCESS)
    assert "Completed" in pill_success.text()
    assert "#065F46" in pill_success.styleSheet()

    pill_failed = make_status_pill(RefreshStatus.FAILED)
    assert "Failed" in pill_failed.text()
    assert "#991B1B" in pill_failed.styleSheet()

    pill_in_progress = make_status_pill(RefreshStatus.IN_PROGRESS)
    assert "In Progress" in pill_in_progress.text()
    assert "#1D4ED8" in pill_in_progress.styleSheet()


def test_refresh_details_dialog_loads_persisted_records_and_displays_kpis(
    qtbot, db: DatabaseManager, sample_registration: int
) -> None:
    mock_client = MagicMock()
    service = RefreshService(db=db, refresh_client=mock_client)

    t_now = datetime.now(timezone.utc)
    # Persist two records: one successful, one in-progress
    mock_client.list_refreshes.return_value = [
        ParsedRefreshRecord(
            refresh_id="ref-run-1",
            status=RefreshStatus.IN_PROGRESS,
            start_time=t_now - timedelta(minutes=5),
            end_time=None,
            duration_ms=None,
            refresh_type="ViaApi",
            error_details=None,
            raw_status="Unknown",
        ),
        ParsedRefreshRecord(
            refresh_id="ref-run-2",
            status=RefreshStatus.SUCCESS,
            start_time=t_now - timedelta(hours=3),
            end_time=t_now - timedelta(hours=3) + timedelta(minutes=8),
            duration_ms=480_000,
            refresh_type="Scheduled",
            error_details=None,
            raw_status="Completed",
        ),
    ]
    service.fetch_and_persist_refreshes(
        workspace_registration_id=sample_registration,
        workspace_id=WS_ID,
        dataset_id=DS_ID,
    )

    dialog = RefreshDetailsDialog(
        workspace_registration_id=sample_registration,
        workspace_id=WS_ID,
        dataset_id=DS_ID,
        registration_display_name="Revenue Model",
        refresh_service=service,
    )
    qtbot.addWidget(dialog)
    dialog.show()

    # 1. Verify KPI summary cards
    assert "In Progress" in dialog.lbl_attempt_pill.text()
    assert "— (In Progress)" in dialog.lbl_attempt_duration.text()
    assert "8m 0s" in dialog.lbl_success_duration.text()
    assert "50.0% (1/2)" in dialog.lbl_rate.text()

    # 2. Verify Table rows
    assert dialog.table.rowCount() == 2
    # In-progress row duration must be '— (In Progress)', never false completed duration
    item_dur_0 = dialog.table.item(0, 3)
    assert item_dur_0 is not None
    assert item_dur_0.text() == "— (In Progress)"

    item_dur_1 = dialog.table.item(1, 3)
    assert item_dur_1 is not None
    assert item_dur_1.text() == "8m 0s"

    # 3. Test selection of row updates diagnostic box
    dialog.table.selectRow(1)
    assert "ref-run-2" in dialog.error_text.toPlainText()
    assert "No error details reported" in dialog.error_text.toPlainText()

    dialog.close()


def test_refresh_details_dialog_displays_error_diagnostics(
    qtbot, db: DatabaseManager, sample_registration: int
) -> None:
    mock_client = MagicMock()
    service = RefreshService(db=db, refresh_client=mock_client)

    t_now = datetime.now(timezone.utc)
    mock_client.list_refreshes.return_value = [
        ParsedRefreshRecord(
            refresh_id="ref-err-99",
            status=RefreshStatus.FAILED,
            start_time=t_now - timedelta(minutes=20),
            end_time=t_now - timedelta(minutes=18),
            duration_ms=120_000,
            refresh_type="Scheduled",
            error_details='{"errorCode": "ModelRefreshFailed", "message": "SQL connection timed out."}',
            raw_status="Failed",
        )
    ]
    service.fetch_and_persist_refreshes(
        workspace_registration_id=sample_registration,
        workspace_id=WS_ID,
        dataset_id=DS_ID,
    )

    dialog = RefreshDetailsDialog(
        workspace_registration_id=sample_registration,
        workspace_id=WS_ID,
        dataset_id=DS_ID,
        registration_display_name="Revenue Model",
        refresh_service=service,
    )
    qtbot.addWidget(dialog)
    dialog.show()

    assert "Failed" in dialog.lbl_attempt_pill.text()
    dialog.table.selectRow(0)
    assert "SQL connection timed out" in dialog.error_text.toPlainText()
    dialog.close()


def test_home_page_refresh_card_integration(
    qtbot, db: DatabaseManager, sample_registration: int
) -> None:
    mock_client = MagicMock()
    service = RefreshService(db=db, refresh_client=mock_client)
    registry = RegistryService(db=db)

    page = HomePage(refresh_service=service, registry_service=registry)
    qtbot.addWidget(page)
    page.show()

    # Verify Stage 8 badge
    badge = page.findChild(object, "StageBadge")
    assert badge is not None
    assert "Stage 8" in badge.text()

    # Enter registered Workspace and Dataset ID
    page.workspace_id_input.setText(WS_ID)
    page.dataset_id_input.setText(DS_ID)

    # Initial state with no refreshes
    assert page.home_reliability_rate.text() == "No History"

    # Synchronize mock refreshes
    t_now = datetime.now(timezone.utc)
    mock_client.list_refreshes.return_value = [
        ParsedRefreshRecord(
            refresh_id="ref-live-1",
            status=RefreshStatus.SUCCESS,
            start_time=t_now - timedelta(hours=1),
            end_time=t_now - timedelta(hours=1) + timedelta(minutes=4),
            duration_ms=240_000,
            refresh_type="ViaApi",
            error_details=None,
            raw_status="Completed",
        )
    ]
    service.fetch_and_persist_refreshes(
        workspace_registration_id=sample_registration,
        workspace_id=WS_ID,
        dataset_id=DS_ID,
    )

    # Update UI
    page._update_refresh_ui()
    assert "Completed" in page.home_attempt_pill.text()
    assert "4m 0s" in page.home_attempt_duration.text()
    assert "100.0% (1/1)" in page.home_reliability_rate.text()


def test_settings_page_refresh_history_action_and_column(
    qtbot, db: DatabaseManager, sample_registration: int
) -> None:
    mock_client = MagicMock()
    service = RefreshService(db=db, refresh_client=mock_client)
    registry = RegistryService(db=db)

    settings = SettingsPage(
        registry_service=registry,
        refresh_service=service,
    )
    qtbot.addWidget(settings)
    settings.show()

    # Verify badge
    badge = settings.findChild(object, "StageBadge")
    assert badge is not None
    assert "Stage" in badge.text()

    # Verify Refresh History button exists in row actions
    assert hasattr(settings, "refresh_history_button")
    assert settings.refresh_history_button.text() == "Refresh History..."

    # Verify table has Latest Refresh column
    headers = [col.header for col in settings.registry_table.source_model.columns]
    assert "Latest Refresh" in headers

    # Select row and verify row data has 'No History'
    row_data = settings.registry_table.source_model.row_at(0)
    assert row_data is not None
    assert row_data.get("refresh_status") == "No History"
