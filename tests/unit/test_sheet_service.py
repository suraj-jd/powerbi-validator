"""Unit tests for Stage B SheetService and SheetRowDTO."""

from __future__ import annotations

import pytest

from app.database.db import DatabaseManager
from app.integrations.file_import import RegistrationInput
from app.services.registry_service import RegistryService
from app.services.rule_service import (
    RuleInput,
    RuleService,
    VALIDATION_TYPE_ANOMALY,
    VALIDATION_TYPE_DAX_MEASURE,
    VALIDATION_TYPE_DUPLICATE,
    VALIDATION_TYPE_LATEST_DATE,
    VALIDATION_TYPE_NULL,
    VALIDATION_TYPE_REFRESH,
    VALIDATION_TYPE_ROW_COUNT,
)
from app.services.sheet_service import SheetRowDTO, SheetService, generate_rule_name, infer_target_type


@pytest.fixture
def db(tmp_path) -> DatabaseManager:
    db_file = tmp_path / "test_sheet_service.db"
    manager = DatabaseManager(db_file)
    manager.run_migrations()
    yield manager
    manager.dispose()


def test_infer_target_type_and_rule_naming() -> None:
    assert infer_target_type(VALIDATION_TYPE_REFRESH) == "MODEL"
    assert infer_target_type(VALIDATION_TYPE_DAX_MEASURE) == "MEASURE"
    assert infer_target_type(VALIDATION_TYPE_NULL, column_name="Amount") == "COLUMN"
    assert infer_target_type(VALIDATION_TYPE_ANOMALY, measure_name="TotalSales") == "MEASURE"

    name_null = generate_rule_name(VALIDATION_TYPE_NULL, table_name="Sales", column_name="Amount")
    assert "Sales[Amount]" in name_null
    assert "Null / Blank Check" in name_null

    name_meas = generate_rule_name(VALIDATION_TYPE_DAX_MEASURE, measure_name="Revenue")
    assert "[Revenue]" in name_meas

    name_ref = generate_rule_name(VALIDATION_TYPE_REFRESH, report_name="Financials")
    assert "Financials" in name_ref
    assert "Refresh" in name_ref


WS_ID = "11111111-2222-3333-4444-555555555555"
DS_ID = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"


def test_sheet_service_crud_flow(db: DatabaseManager) -> None:
    sheet_service = SheetService(db=db)

    # 1. Initially empty
    rows = sheet_service.load_sheet_rows()
    assert len(rows) == 0

    # 2. Save a new row (auto-creates workspace registration and validation rule)
    new_row = SheetRowDTO(
        workspace_name="Finance Workspace",
        workspace_id=WS_ID,
        report_name="Revenue Report",
        dataset_name="Revenue Model",
        dataset_id=DS_ID,
        validation_type=VALIDATION_TYPE_NULL,
        table_name="Transactions",
        column_name="TransactionID",
        config={"allowed_blank_count": 0},
    )
    saved_row = sheet_service.save_sheet_row(new_row)
    assert saved_row.row_id is not None
    assert saved_row.workspace_registration_id is not None
    assert "Transactions[TransactionID]" in saved_row.effective_rule_name()

    # 3. Load rows
    loaded_rows = sheet_service.load_sheet_rows()
    assert len(loaded_rows) == 1
    r = loaded_rows[0]
    assert r.sr_no == 1
    assert r.workspace_name == "Finance Workspace"
    assert r.report_name == "Revenue Report"
    assert r.validation_type == VALIDATION_TYPE_NULL
    assert r.table_name == "Transactions"
    assert r.column_name == "TransactionID"
    assert "allowed blanks = 0" in r.conditions_summary

    # 4. Update the row with a new condition
    r.config = {"allowed_blank_count": 5}
    sheet_service.save_sheet_row(r)

    loaded_updated = sheet_service.load_sheet_rows()
    assert len(loaded_updated) == 1
    assert "allowed blanks = 5" in loaded_updated[0].conditions_summary

    # 5. Add a refresh check row
    refresh_row = SheetRowDTO(
        workspace_name="Finance Workspace",
        workspace_id=WS_ID,
        report_name="Revenue Report",
        dataset_name="Revenue Model",
        dataset_id=DS_ID,
        validation_type=VALIDATION_TYPE_REFRESH,
        config={"expected_status": "Completed", "max_age_hours": 24},
    )
    sheet_service.save_sheet_row(refresh_row)

    rows_all = sheet_service.load_sheet_rows()
    assert len(rows_all) == 2
    assert rows_all[0].sr_no == 1
    assert rows_all[1].sr_no == 2
    assert "age <= 24h" in rows_all[1].conditions_summary

    # 6. Delete a row
    sheet_service.delete_sheet_row(saved_row.row_id)
    remaining = sheet_service.load_sheet_rows()
    assert len(remaining) == 1
    assert remaining[0].validation_type == VALIDATION_TYPE_REFRESH

    # 7. Test export to dicts
    dicts = sheet_service.export_to_dicts(remaining)
    assert len(dicts) == 1
    assert dicts[0]["workspace_name"] == "Finance Workspace"
    assert dicts[0]["validation_type"] == VALIDATION_TYPE_REFRESH
    assert "filter_1" in dicts[0]
    assert "filter_2" in dicts[0]
    assert "filter_3" in dicts[0]
    assert "filter_4" in dicts[0]
