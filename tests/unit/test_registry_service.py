"""Unit tests for RegistryService and CSV/XLSX registration import/export."""

from __future__ import annotations

import csv
from pathlib import Path

import pytest
from openpyxl import Workbook, load_workbook

from app.core.exceptions import PersistenceError, ValidationConfigError
from app.database.db import DatabaseManager
from app.integrations.file_import import TEMPLATE_COLUMNS, RegistrationInput
from app.services.registry_service import RegistryService

WS_1 = "11111111-2222-3333-4444-555555555555"
DS_1 = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
RPT_1 = "12345678-1234-1234-1234-1234567890ab"
WS_2 = "22222222-2222-3333-4444-555555555555"
DS_2 = "bbbbbbbb-bbbb-cccc-dddd-eeeeeeeeeeee"


@pytest.fixture
def service(tmp_path: Path):
    db = DatabaseManager(tmp_path / "registry.db")
    db.run_migrations()
    try:
        yield RegistryService(db)
    finally:
        db.dispose()


def test_manual_crud_validation_and_duplicate_rejection(service: RegistryService) -> None:
    created = service.create_registration(
        RegistrationInput(
            workspace_name="Bosch Analytics",
            workspace_id=WS_1,
            report_name="Employee Dashboard",
            report_id=RPT_1,
            dataset_name="HR Model",
            dataset_id=DS_1,
            is_active=True,
        )
    )
    assert created.id > 0
    assert len(service.list_registrations()) == 1

    # Invalid GUID rejected cleanly
    with pytest.raises(ValidationConfigError):
        service.create_registration(
            RegistrationInput(
                workspace_name="Bad",
                workspace_id="not-a-guid",
                report_name="Report",
                dataset_id=DS_1,
            )
        )

    # Duplicate rejected
    with pytest.raises(PersistenceError):
        service.create_registration(
            RegistrationInput(
                workspace_name="Bosch Analytics Duplicate",
                workspace_id=WS_1,
                report_name="Employee Dashboard",
                report_id=RPT_1,
                dataset_id=DS_1,
            )
        )

    updated = service.set_active(created.id, False)
    assert updated.is_active is False
    assert service.list_registrations(active_only=True) == []

    assert service.delete_registration(created.id) is True
    assert service.list_registrations() == []


def test_csv_import_preview_surfaces_row_errors_without_discarding_them(
    service: RegistryService,
    tmp_path: Path,
) -> None:
    # Pre-seed one registration to test existing-DB duplicate detection
    service.create_registration(
        RegistrationInput(
            workspace_name="Existing WS",
            workspace_id=WS_1,
            report_name="Existing Report",
            report_id=RPT_1,
            dataset_id=DS_1,
        )
    )

    csv_path = tmp_path / "import.csv"
    with csv_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(TEMPLATE_COLUMNS)
        # Row 2: Valid new row
        writer.writerow(["Finance Reports", WS_2, "Finance Overview", "", "Finance Model", DS_2, "Yes"])
        # Row 3: Duplicate of row 2 in same file
        writer.writerow(["Finance Reports Dup", WS_2, "Finance Overview", "", "Finance Model", DS_2, "True"])
        # Row 4: Invalid GUID + missing ReportName
        writer.writerow(["Bad WS", "invalid-guid", "", "", "", "also-bad", "maybe"])
        # Row 5: Duplicate of already-saved DB row
        writer.writerow(["Existing WS", WS_1, "Existing Report", RPT_1, "", DS_1, "True"])

    preview = service.preview_import(csv_path)
    assert preview.missing_columns == []
    assert len(preview.rows) == 4
    assert len(preview.valid_rows) == 1
    assert len(preview.invalid_rows) == 3

    assert preview.rows[0].is_valid is True
    assert "within this import file" in " ".join(preview.rows[1].errors).lower()
    assert len(preview.rows[2].errors) >= 3
    assert "already registered" in " ".join(preview.rows[3].errors).lower()

    saved, errors = service.commit_import([r.parsed for r in preview.valid_rows if r.parsed])
    assert saved == 1
    assert errors == []
    assert len(service.list_registrations()) == 2


def test_xlsx_import_and_blank_template_export(service: RegistryService, tmp_path: Path) -> None:
    csv_tpl = service.export_template(tmp_path / "template.csv")
    xlsx_tpl = service.export_template(tmp_path / "template.xlsx")

    assert csv_tpl.exists()
    assert xlsx_tpl.exists()

    with csv_tpl.open("r", encoding="utf-8-sig") as f:
        header = next(csv.reader(f))
    assert tuple(header) == TEMPLATE_COLUMNS

    wb = load_workbook(xlsx_tpl)
    sheet = wb.active
    xlsx_headers = tuple(cell.value for cell in sheet[1])
    wb.close()
    assert xlsx_headers == TEMPLATE_COLUMNS

    # Write a populated XLSX file and preview/import it
    import_xlsx = tmp_path / "registrations.xlsx"
    wb2 = Workbook()
    ws = wb2.active
    ws.append(list(TEMPLATE_COLUMNS))
    ws.append(["Bosch Analytics", WS_1, "Employee Dashboard", RPT_1, "HR Model", DS_1, "True"])
    ws.append(["Finance Reports", WS_2, "Finance Overview", "", "Finance Model", DS_2, "False"])
    wb2.save(import_xlsx)

    preview = service.preview_import(import_xlsx)
    assert len(preview.valid_rows) == 2
    assert len(preview.invalid_rows) == 0

    saved, errors = service.commit_import([r.parsed for r in preview.valid_rows if r.parsed])
    assert saved == 2
    assert errors == []
    assert len(service.list_registrations(active_only=True)) == 1
