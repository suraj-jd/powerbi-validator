"""CSV and XLSX import/export helpers for Workspace, Report, and Dataset registrations."""

from __future__ import annotations

import csv
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from openpyxl import Workbook, load_workbook
from openpyxl.styles import Font, PatternFill

from app.auth.msal_auth import is_valid_guid
from app.core.exceptions import ValidationConfigError
from app.integrations.powerbi.workspace_client import (
    MY_WORKSPACE_ID,
    is_my_workspace,
    is_valid_workspace_id,
)

TEMPLATE_COLUMNS: tuple[str, ...] = (
    "WorkspaceName",
    "WorkspaceId",
    "ReportName",
    "ReportId",
    "DatasetName",
    "DatasetId",
    "Active",
)

REQUIRED_COLUMNS: tuple[str, ...] = (
    "WorkspaceName",
    "WorkspaceId",
    "ReportName",
    "DatasetId",
)

_TRUE_STRINGS = {"true", "yes", "y", "1", "active"}
_FALSE_STRINGS = {"false", "no", "n", "0", "inactive"}


@dataclass(frozen=True, slots=True)
class RegistrationInput:
    """Validated registration payload ready to persist in SQLite."""

    workspace_name: str
    workspace_id: str
    report_name: str
    dataset_id: str
    report_id: str | None = None
    dataset_name: str | None = None
    is_active: bool = True

    @property
    def unique_key(self) -> tuple[str, str, str | None]:
        return (
            self.workspace_id.strip().lower(),
            self.dataset_id.strip().lower(),
            self.report_id.strip().lower() if self.report_id and self.report_id.strip() else None,
        )


@dataclass(slots=True)
class ImportRowPreview:
    """Row-level validation preview for CSV/XLSX registration import."""

    row_number: int
    workspace_name: str
    workspace_id: str
    report_name: str
    report_id: str
    dataset_name: str
    dataset_id: str
    active_raw: str
    parsed: RegistrationInput | None = None
    errors: list[str] = field(default_factory=list)

    @property
    def is_valid(self) -> bool:
        return len(self.errors) == 0 and self.parsed is not None


@dataclass(slots=True)
class ImportPreviewResult:
    """Complete file import preview including missing headers and per-row errors."""

    file_path: Path
    rows: list[ImportRowPreview] = field(default_factory=list)
    missing_columns: list[str] = field(default_factory=list)

    @property
    def valid_rows(self) -> list[ImportRowPreview]:
        return [r for r in self.rows if r.is_valid]

    @property
    def invalid_rows(self) -> list[ImportRowPreview]:
        return [r for r in self.rows if not r.is_valid]


def validate_registration_fields(
    *,
    workspace_name: str,
    workspace_id: str,
    report_name: str,
    dataset_id: str,
    report_id: str = "",
    dataset_name: str = "",
    is_active: bool = True,
) -> tuple[RegistrationInput | None, list[str]]:
    """Validate manual or imported registration fields and return `(parsed, errors)`."""
    errors: list[str] = []

    ws_name = workspace_name.strip()
    ws_id = workspace_id.strip()
    rpt_name = report_name.strip()
    rpt_id = report_id.strip()
    ds_name = dataset_name.strip()
    ds_id = dataset_id.strip()

    if not ws_name:
        errors.append("Workspace Name is required.")
    if not ws_id:
        errors.append("Workspace ID is required.")
    elif not is_valid_workspace_id(ws_id):
        errors.append("Workspace ID must be a valid GUID (or 'me' for My Workspace).")

    if not rpt_name:
        errors.append("Report Name is required.")

    if rpt_id and not is_valid_guid(rpt_id):
        errors.append("Report ID must be a valid GUID when provided.")

    if not ds_id:
        errors.append("Dataset ID is required.")
    elif not is_valid_guid(ds_id):
        errors.append("Dataset ID must be a valid GUID.")

    if errors:
        return None, errors

    normalized_ws_id = MY_WORKSPACE_ID if is_my_workspace(ws_id) else ws_id.lower()
    return (
        RegistrationInput(
            workspace_name=ws_name,
            workspace_id=normalized_ws_id,
            report_name=rpt_name,
            report_id=rpt_id.lower() if rpt_id else None,
            dataset_name=ds_name or None,
            dataset_id=ds_id.lower(),
            is_active=bool(is_active),
        ),
        [],
    )


def _parse_bool_cell(raw_value: Any) -> tuple[bool | None, str | None]:
    if raw_value is None or str(raw_value).strip() == "":
        return True, None
    if isinstance(raw_value, bool):
        return raw_value, None
    cleaned = str(raw_value).strip().lower()
    if cleaned in _TRUE_STRINGS:
        return True, None
    if cleaned in _FALSE_STRINGS:
        return False, None
    return None, f"Invalid Active value '{raw_value}' (use True/False or Yes/No)."


def _normalize_header_map(headers: list[str]) -> dict[str, int]:
    """Map canonical lowercase header names (ignoring spaces/underscores) to column index."""
    mapping: dict[str, int] = {}
    for idx, header in enumerate(headers):
        normalized = header.strip().lower().replace(" ", "").replace("_", "")
        if normalized and normalized not in mapping:
            mapping[normalized] = idx
    return mapping


def _read_tabular_rows(file_path: Path) -> tuple[list[str], list[tuple[int, list[Any]]]]:
    suffix = file_path.suffix.lower()
    if suffix == ".csv":
        with file_path.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = list(csv.reader(handle))
        if not reader:
            return [], []
        headers = [str(cell) for cell in reader[0]]
        data_rows = [(idx + 2, row) for idx, row in enumerate(reader[1:])]
        return headers, data_rows

    if suffix == ".xlsx":
        wb = load_workbook(filename=file_path, read_only=True, data_only=True)
        try:
            sheet = wb.active
            if sheet is None:
                return [], []
            raw_rows = list(sheet.iter_rows(values_only=True))
        finally:
            wb.close()
        if not raw_rows:
            return [], []
        headers = ["" if cell is None else str(cell) for cell in raw_rows[0]]
        data_rows = [(idx + 2, list(row)) for idx, row in enumerate(raw_rows[1:])]
        return headers, data_rows

    raise ValidationConfigError(
        f"Unsupported import file format: {suffix}",
        user_message="Only .csv and .xlsx files are supported for registration import.",
    )


def parse_registrations_file(
    file_path: Path,
    *,
    existing_keys: set[tuple[str, str, str | None]] | None = None,
) -> ImportPreviewResult:
    """Parse and validate every row in a CSV or XLSX file without discarding invalid rows."""
    path = Path(file_path)
    if not path.exists():
        raise ValidationConfigError(
            f"Import file not found: {path}",
            user_message=f"Selected file does not exist: {path.name}",
        )

    headers, raw_rows = _read_tabular_rows(path)
    header_map = _normalize_header_map(headers)

    missing_columns = [
        col for col in REQUIRED_COLUMNS if col.lower() not in header_map
    ]
    preview = ImportPreviewResult(file_path=path, missing_columns=missing_columns)
    if missing_columns:
        return preview

    def _cell(row: list[Any], canonical_name: str) -> Any:
        col_idx = header_map.get(canonical_name.lower())
        if col_idx is None or col_idx >= len(row):
            return ""
        val = row[col_idx]
        return "" if val is None else val

    seen_in_file: set[tuple[str, str, str | None]] = set()
    existing = existing_keys or set()

    for row_number, row in raw_rows:
        # Skip completely blank trailing lines
        if all(cell is None or str(cell).strip() == "" for cell in row):
            continue

        ws_name = str(_cell(row, "WorkspaceName")).strip()
        ws_id = str(_cell(row, "WorkspaceId")).strip()
        rpt_name = str(_cell(row, "ReportName")).strip()
        rpt_id = str(_cell(row, "ReportId")).strip()
        ds_name = str(_cell(row, "DatasetName")).strip()
        ds_id = str(_cell(row, "DatasetId")).strip()
        active_cell = _cell(row, "Active")
        active_raw = "" if active_cell is None else str(active_cell).strip()

        active_bool, active_error = _parse_bool_cell(active_cell)
        parsed, field_errors = validate_registration_fields(
            workspace_name=ws_name,
            workspace_id=ws_id,
            report_name=rpt_name,
            report_id=rpt_id,
            dataset_name=ds_name,
            dataset_id=ds_id,
            is_active=True if active_bool is None else active_bool,
        )

        row_errors = list(field_errors)
        if active_error:
            row_errors.append(active_error)
            parsed = None

        if parsed is not None:
            key = parsed.unique_key
            if key in seen_in_file:
                row_errors.append("Duplicate Workspace/Dataset/Report entry within this import file.")
                parsed = None
            elif key in existing:
                row_errors.append("Already registered in the local database.")
                parsed = None
            else:
                seen_in_file.add(key)

        preview.rows.append(
            ImportRowPreview(
                row_number=row_number,
                workspace_name=ws_name,
                workspace_id=ws_id,
                report_name=rpt_name,
                report_id=rpt_id,
                dataset_name=ds_name,
                dataset_id=ds_id,
                active_raw=active_raw or "True",
                parsed=parsed,
                errors=row_errors,
            )
        )

    return preview


def export_blank_template(file_path: Path) -> Path:
    """Write a blank CSV or XLSX registration template with the required header columns."""
    path = Path(file_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    suffix = path.suffix.lower()

    if suffix == ".csv":
        with path.open("w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.writer(handle)
            writer.writerow(TEMPLATE_COLUMNS)
        return path

    if suffix == ".xlsx":
        wb = Workbook()
        ws = wb.active
        ws.title = "Registrations"
        ws.append(list(TEMPLATE_COLUMNS))

        header_fill = PatternFill(start_color="13294B", end_color="13294B", fill_type="solid")
        header_font = Font(color="FFFFFF", bold=True)
        for col_idx, col_name in enumerate(TEMPLATE_COLUMNS, start=1):
            cell = ws.cell(row=1, column=col_idx)
            cell.fill = header_fill
            cell.font = header_font
            ws.column_dimensions[cell.column_letter].width = max(18, len(col_name) + 6)

        wb.save(path)
        return path

    raise ValidationConfigError(
        f"Unsupported template format: {suffix}",
        user_message="Template export supports .csv or .xlsx files.",
    )
