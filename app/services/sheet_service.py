"""Sheet data layer and orchestration service for Excel-style validation table.

Provides a flattened spreadsheet abstraction (SheetRowDTO) over Power BI
Workspace Registrations and Validation Rules, allowing non-technical users
to manage validation checks like an Excel spreadsheet.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from app.core.exceptions import PersistenceError, ValidationConfigError
from app.database.db import DatabaseManager
from app.integrations.file_import import RegistrationInput
from app.services.registry_service import RegistrationRecord, RegistryService
from app.services.rule_service import (
    RuleInput,
    RuleRecord,
    RuleService,
    TARGET_TYPE_COLUMN,
    TARGET_TYPE_MEASURE,
    TARGET_TYPE_MODEL,
    VALIDATION_TYPE_ANOMALY,
    VALIDATION_TYPE_DAX_MEASURE,
    VALIDATION_TYPE_DUPLICATE,
    VALIDATION_TYPE_LATEST_DATE,
    VALIDATION_TYPE_NULL,
    VALIDATION_TYPE_REFRESH,
    VALIDATION_TYPE_ROW_COUNT,
    VALIDATION_TYPES,
    format_rule_conditions_summary,
)

logger = logging.getLogger(__name__)

FRIENDLY_TEST_NAMES: dict[str, str] = {
    VALIDATION_TYPE_NULL: "Null / Blank Check",
    VALIDATION_TYPE_DUPLICATE: "Duplicate Check",
    VALIDATION_TYPE_LATEST_DATE: "Latest Date Freshness",
    VALIDATION_TYPE_ROW_COUNT: "Row Count Check",
    VALIDATION_TYPE_REFRESH: "Power BI Refresh SLA",
    VALIDATION_TYPE_DAX_MEASURE: "DAX Measure Check",
    VALIDATION_TYPE_ANOMALY: "Baseline & % Change Check",
}

TEST_TYPE_TOOLTIPS: dict[str, str] = {
    VALIDATION_TYPE_NULL: "Checks if a column has blank, missing, or empty values.",
    VALIDATION_TYPE_DUPLICATE: "Checks if a column has duplicate records or repeated primary keys.",
    VALIDATION_TYPE_LATEST_DATE: "Checks the most recent date in a table to ensure data was updated recently.",
    VALIDATION_TYPE_ROW_COUNT: "Checks if the total number of rows in a table meets your expected count.",
    VALIDATION_TYPE_REFRESH: "Verifies whether the Power BI dataset refreshed successfully within the allowed hours.",
    VALIDATION_TYPE_DAX_MEASURE: "Evaluates a Power BI DAX measure and compares the value against expected thresholds.",
    VALIDATION_TYPE_ANOMALY: "Checks minimum or maximum baseline limits and flags unexpected percentage changes from previous runs.",
}

TEST_NAME_TO_TYPE: dict[str, str] = {v.lower(): k for k, v in FRIENDLY_TEST_NAMES.items()}
# Also support historical aliases
TEST_NAME_TO_TYPE["historical anomaly check"] = VALIDATION_TYPE_ANOMALY
TEST_NAME_TO_TYPE["historical anomaly"] = VALIDATION_TYPE_ANOMALY
TEST_NAME_TO_TYPE["baseline & % change"] = VALIDATION_TYPE_ANOMALY
TEST_NAME_TO_TYPE["baseline & % change check"] = VALIDATION_TYPE_ANOMALY
TEST_NAME_TO_TYPE["baseline check"] = VALIDATION_TYPE_ANOMALY
TEST_NAME_TO_TYPE["baseline & drift check"] = VALIDATION_TYPE_ANOMALY
# Also support raw keys
for k, v in FRIENDLY_TEST_NAMES.items():
    TEST_NAME_TO_TYPE[k.lower()] = k


def infer_target_type(
    validation_type: str,
    column_name: str | None = None,
    measure_name: str | None = None,
) -> str:
    """Infer target type (COLUMN, MEASURE, MODEL) from validation check and target fields."""
    if validation_type == VALIDATION_TYPE_REFRESH:
        return TARGET_TYPE_MODEL
    if validation_type == VALIDATION_TYPE_DAX_MEASURE:
        return TARGET_TYPE_MEASURE
    if measure_name and not column_name:
        return TARGET_TYPE_MEASURE
    return TARGET_TYPE_COLUMN


def generate_rule_name(
    validation_type: str,
    table_name: str | None = None,
    column_name: str | None = None,
    measure_name: str | None = None,
    report_name: str | None = None,
) -> str:
    """Generate a clean, intuitive rule name for non-technical users."""
    test_title = FRIENDLY_TEST_NAMES.get(validation_type, "Validation Check")
    if validation_type == VALIDATION_TYPE_REFRESH:
        target = report_name or "Semantic Model"
        return f"{target} - {test_title}"
    if measure_name:
        return f"[{measure_name}] - {test_title}"
    if table_name and column_name:
        return f"{table_name}[{column_name}] - {test_title}"
    if table_name:
        return f"{table_name} - {test_title}"
    return f"{report_name or 'Target'} - {test_title}"


@dataclass
class SheetRowDTO:
    """Flattened representation of one Excel sheet row combining workspace, dataset, and rule."""

    row_id: int | None = None  # None for newly inserted unsaved rows; maps to ValidationRule.id
    sr_no: int = 1
    enabled: bool = True
    workspace_registration_id: int | None = None
    workspace_name: str = ""
    workspace_id: str = ""
    report_name: str = ""
    report_id: str | None = None
    dataset_name: str = ""
    dataset_id: str = ""
    validation_type: str = VALIDATION_TYPE_NULL
    table_name: str | None = None
    column_name: str | None = None
    measure_name: str | None = None
    config: dict[str, Any] = field(default_factory=dict)
    rule_name: str | None = None
    filter_1: str = ""
    filter_2: str = ""
    filter_3: str = ""
    filter_4: str = ""

    def __post_init__(self) -> None:
        if not self.filter_1 and "filter_1" in self.config:
            self.filter_1 = str(self.config["filter_1"] or "")
        if not self.filter_2 and "filter_2" in self.config:
            self.filter_2 = str(self.config["filter_2"] or "")
        if not self.filter_3 and "filter_3" in self.config:
            self.filter_3 = str(self.config["filter_3"] or "")
        if not self.filter_4 and "filter_4" in self.config:
            self.filter_4 = str(self.config["filter_4"] or "")

    @property
    def target_type(self) -> str:
        return infer_target_type(self.validation_type, self.column_name, self.measure_name)

    @property
    def validation_type_display(self) -> str:
        return FRIENDLY_TEST_NAMES.get(self.validation_type, self.validation_type)

    @property
    def conditions_summary(self) -> str:
        return format_rule_conditions_summary(self.validation_type, self.config)

    @property
    def target_display(self) -> str:
        if self.validation_type == VALIDATION_TYPE_REFRESH:
            return "Semantic Model"
        if self.measure_name:
            return f"[{self.measure_name}]"
        if self.table_name and self.column_name:
            return f"{self.table_name}[{self.column_name}]"
        return self.table_name or self.column_name or "-"

    def effective_rule_name(self) -> str:
        if self.rule_name and self.rule_name.strip():
            return self.rule_name.strip()
        return generate_rule_name(
            self.validation_type,
            self.table_name,
            self.column_name,
            self.measure_name,
            self.report_name,
        )

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for table rendering, JSON, or CSV/Excel export."""
        return {
            "sr_no": self.sr_no,
            "row_id": self.row_id,
            "enabled": self.enabled,
            "workspace_registration_id": self.workspace_registration_id,
            "workspace_name": self.workspace_name,
            "workspace_id": self.workspace_id,
            "report_name": self.report_name,
            "report_id": self.report_id or "",
            "dataset_name": self.dataset_name,
            "dataset_id": self.dataset_id,
            "validation_type": self.validation_type,
            "validation_type_display": self.validation_type_display,
            "table_name": self.table_name or "",
            "column_name": self.column_name or "",
            "measure_name": self.measure_name or "",
            "filter_1": self.filter_1 or "",
            "filter_2": self.filter_2 or "",
            "filter_3": self.filter_3 or "",
            "filter_4": self.filter_4 or "",
            "target_display": self.target_display,
            "conditions_summary": self.conditions_summary,
            "rule_name": self.effective_rule_name(),
            "config": dict(self.config),
        }


class SheetService:
    """Service providing tabular Excel sheet operations over local SQLite storage."""

    def __init__(
        self,
        db: DatabaseManager,
        *,
        registry_service: RegistryService | None = None,
        rule_service: RuleService | None = None,
    ) -> None:
        self._db = db
        self._registry_service = registry_service or RegistryService(db=db)
        self._rule_service = rule_service or RuleService(db=db)

    def load_sheet_rows(
        self,
        *,
        workspace_registration_id: int | None = None,
    ) -> list[SheetRowDTO]:
        """Load all validation rules formatted as spreadsheet rows.

        If workspace_registration_id is provided, loads only rules for that registration.
        Otherwise loads rules across all registered Power BI workspaces and models.
        """
        rows: list[SheetRowDTO] = []
        sr_counter = 1

        registrations = (
            [self._registry_service.get_registration(workspace_registration_id)]
            if workspace_registration_id is not None
            else self._registry_service.list_registrations(active_only=False)
        )

        for reg in registrations:
            if reg is None:
                continue
            rules = self._rule_service.list_rules(reg.id, enabled_only=False)
            for rule in rules:
                dto = SheetRowDTO(
                    row_id=rule.id,
                    sr_no=sr_counter,
                    enabled=rule.enabled,
                    workspace_registration_id=reg.id,
                    workspace_name=reg.workspace_name,
                    workspace_id=reg.workspace_id,
                    report_name=reg.report_name,
                    report_id=reg.report_id,
                    dataset_name=reg.dataset_name or reg.report_name,
                    dataset_id=reg.dataset_id,
                    validation_type=rule.validation_type,
                    table_name=rule.table_name,
                    column_name=rule.column_name,
                    measure_name=rule.measure_name,
                    config=dict(rule.config),
                    rule_name=rule.rule_name,
                    filter_1=str(rule.config.get("filter_1", "") or ""),
                    filter_2=str(rule.config.get("filter_2", "") or ""),
                    filter_3=str(rule.config.get("filter_3", "") or ""),
                    filter_4=str(rule.config.get("filter_4", "") or ""),
                )
                rows.append(dto)
                sr_counter += 1

        return rows

    def save_sheet_row(self, row: SheetRowDTO) -> SheetRowDTO:
        """Create or update a spreadsheet row and persist to SQLite."""
        ws_id = (row.workspace_id or "").strip()
        ds_id = (row.dataset_id or "").strip()
        ws_name = (row.workspace_name or "").strip() or f"Workspace {ws_id[:8]}"
        ds_name = (row.dataset_name or "").strip() or (row.report_name or "").strip() or f"Dataset {ds_id[:8]}"
        rpt_name = (row.report_name or "").strip() or ds_name
        rpt_id = (row.report_id or "").strip() or None

        if not ws_id:
            raise ValidationConfigError("Workspace ID is required.")
        if not ds_id:
            raise ValidationConfigError("Dataset ID is required.")

        # Resolve or create WorkspaceRegistration
        reg: RegistrationRecord | None = None
        if row.workspace_registration_id is not None:
            reg = self._registry_service.get_registration(row.workspace_registration_id)

        if reg is None:
            reg = self._registry_service.find_by_workspace_and_dataset(ws_id, ds_id)

        if reg is None:
            reg = self._registry_service.create_registration(
                RegistrationInput(
                    workspace_name=ws_name,
                    workspace_id=ws_id,
                    report_name=rpt_name,
                    report_id=rpt_id,
                    dataset_name=ds_name,
                    dataset_id=ds_id,
                    is_active=True,
                )
            )

        row.workspace_registration_id = reg.id
        row.workspace_name = reg.workspace_name
        row.report_name = reg.report_name
        row.dataset_name = reg.dataset_name or reg.report_name

        rule_name = row.effective_rule_name()
        target_type = infer_target_type(row.validation_type, row.column_name, row.measure_name)

        # Synchronize filter_1..4 into row.config for persistence
        cfg_dict = dict(row.config)
        for f_key, f_val in [
            ("filter_1", row.filter_1),
            ("filter_2", row.filter_2),
            ("filter_3", row.filter_3),
            ("filter_4", row.filter_4),
        ]:
            if f_val and str(f_val).strip():
                cfg_dict[f_key] = str(f_val).strip()
            elif f_key in cfg_dict and not str(f_val or "").strip():
                cfg_dict.pop(f_key, None)
        row.config = cfg_dict

        rule_input = RuleInput(
            workspace_registration_id=reg.id,
            rule_name=rule_name,
            enabled=row.enabled,
            target_type=target_type,
            table_name=(row.table_name or "").strip() or None,
            column_name=(row.column_name or "").strip() or None,
            measure_name=(row.measure_name or "").strip() or None,
            validation_type=row.validation_type,
            config=dict(row.config),
            display_order=row.sr_no,
        )

        if row.row_id is None:
            created_rule = self._rule_service.create_rule(rule_input)
            row.row_id = created_rule.id
            logger.info("Created new validation sheet rule %d: %s", row.row_id, rule_name)
        else:
            updated_rule = self._rule_service.update_rule(row.row_id, rule_input)
            logger.info("Updated validation sheet rule %d: %s", row.row_id, rule_name)

        return row

    def save_all_rows(self, rows: list[SheetRowDTO]) -> list[SheetRowDTO]:
        """Save a list of spreadsheet rows, assigning 1-based sequential Sr. numbers."""
        saved: list[SheetRowDTO] = []
        for idx, row in enumerate(rows, start=1):
            row.sr_no = idx
            saved.append(self.save_sheet_row(row))
        return saved

    def delete_sheet_row(self, row_id: int) -> None:
        """Delete a rule by its rule_id."""
        self._rule_service.delete_rule(row_id)
        logger.info("Deleted validation sheet rule %d", row_id)

    def export_to_dicts(self, rows: list[SheetRowDTO]) -> list[dict[str, Any]]:
        """Export rows to clean dictionaries suitable for Excel or CSV export."""
        return [row.to_dict() for row in rows]
