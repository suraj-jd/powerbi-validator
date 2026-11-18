"""CSV / XLSX registration import preview dialog with row-level error visibility."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from app.core.exceptions import ValidationConfigError
from app.core.status import NotificationLevel, ValidationStatus
from app.integrations.file_import import (
    TEMPLATE_COLUMNS,
    ImportPreviewResult,
    RegistrationInput,
)
from app.services.registry_service import RegistryService
from app.ui.models.dict_table_model import ColumnSpec
from app.ui.widgets.data_table import DataTableWidget
from app.ui.widgets.notification_banner import NotificationBanner

_PREVIEW_COLUMNS: list[ColumnSpec] = [
    ColumnSpec(key="row", header="Row", alignment=Qt.AlignmentFlag.AlignCenter),
    ColumnSpec(
        key="status",
        header="Status",
        alignment=Qt.AlignmentFlag.AlignCenter,
        is_status=True,
    ),
    ColumnSpec(key="workspace_name", header="Workspace Name"),
    ColumnSpec(key="workspace_id", header="Workspace ID"),
    ColumnSpec(key="report_name", header="Report Name"),
    ColumnSpec(key="dataset_id", header="Dataset ID"),
    ColumnSpec(key="active", header="Active", alignment=Qt.AlignmentFlag.AlignCenter),
    ColumnSpec(key="errors", header="Validation Errors"),
]


class ImportRegistrationsDialog(QDialog):
    """Guides users through CSV/XLSX preview, error review, and confirmed import."""

    def __init__(
        self,
        registry_service: RegistryService,
        *,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._registry = registry_service
        self._preview: ImportPreviewResult | None = None
        self._confirmed_rows: list[RegistrationInput] = []

        self.setWindowTitle("Import Workspaces & Datasets from CSV / Excel")
        self.setModal(True)
        self.resize(960, 600)
        self.setMinimumSize(780, 480)
        self.setObjectName("ConfirmDialog")

        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(14)

        title = QLabel("Import Registrations (CSV / XLSX)")
        title.setObjectName("DialogTitle")
        layout.addWidget(title)

        template_hint = QLabel(
            "Required template columns: " + ", ".join(TEMPLATE_COLUMNS)
        )
        template_hint.setObjectName("InfoBanner")
        template_hint.setWordWrap(True)
        template_hint.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(template_hint)

        # File chooser & template export row
        top_actions = QHBoxLayout()
        top_actions.setSpacing(10)

        self.choose_file_button = QPushButton("Choose CSV / XLSX File...")
        self.choose_file_button.setObjectName("PrimaryButton")
        self.choose_file_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.choose_file_button.clicked.connect(self._browse_file)
        top_actions.addWidget(self.choose_file_button)

        self.export_template_button = QPushButton("Export Blank Template")
        self.export_template_button.setObjectName("SecondaryButton")
        self.export_template_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.export_template_button.clicked.connect(self._export_template)
        top_actions.addWidget(self.export_template_button)

        self.file_label = QLabel("No file selected")
        self.file_label.setObjectName("PageSubtitle")
        top_actions.addWidget(self.file_label, stretch=1)

        layout.addLayout(top_actions)

        self.banner = NotificationBanner(self)
        layout.addWidget(self.banner)

        self.preview_table = DataTableWidget(
            columns=_PREVIEW_COLUMNS,
            rows=[],
            show_search=True,
            filter_column_key="status",
            filter_options=[ValidationStatus.PASS.value, ValidationStatus.FAIL.value],
            parent=self,
        )
        self.preview_table.table_view.setColumnWidth(0, 52)
        self.preview_table.table_view.setColumnWidth(1, 76)
        self.preview_table.table_view.setColumnWidth(2, 150)
        self.preview_table.table_view.setColumnWidth(3, 190)
        self.preview_table.table_view.setColumnWidth(4, 150)
        self.preview_table.table_view.setColumnWidth(5, 190)
        self.preview_table.table_view.setColumnWidth(6, 65)
        layout.addWidget(self.preview_table, stretch=1)

        # Explicit invalid-row acknowledgement so invalid rows are NEVER silently dropped
        self.skip_invalid_checkbox = QCheckBox(
            "Skip invalid rows shown above and import valid rows only"
        )
        self.skip_invalid_checkbox.setVisible(False)
        self.skip_invalid_checkbox.toggled.connect(self._update_confirm_button_state)
        layout.addWidget(self.skip_invalid_checkbox)

        # Bottom buttons
        buttons = QHBoxLayout()
        buttons.setSpacing(10)
        buttons.addStretch(1)

        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.setObjectName("SecondaryButton")
        self.cancel_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.cancel_button.clicked.connect(self.reject)
        buttons.addWidget(self.cancel_button)

        self.confirm_button = QPushButton("Confirm & Import")
        self.confirm_button.setObjectName("PrimaryButton")
        self.confirm_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.confirm_button.setEnabled(False)
        self.confirm_button.clicked.connect(self._confirm_import)
        buttons.addWidget(self.confirm_button)

        layout.addLayout(buttons)

    @property
    def confirmed_rows(self) -> list[RegistrationInput]:
        return list(self._confirmed_rows)

    def load_file_preview(self, file_path: Path) -> ImportPreviewResult | None:
        """Parse `file_path` and populate the preview table with all valid and invalid rows."""
        try:
            preview = self._registry.preview_import(file_path)
        except ValidationConfigError as exc:
            self.banner.show_message(exc.user_message, level=NotificationLevel.ERROR, title="Import Error")
            self.preview_table.set_rows([])
            self._preview = None
            self._update_confirm_button_state()
            return None

        self._preview = preview
        self.file_label.setText(str(file_path.name))

        if preview.missing_columns:
            self.preview_table.set_rows([])
            self.skip_invalid_checkbox.setVisible(False)
            self.banner.show_message(
                "Missing required column(s): " + ", ".join(preview.missing_columns),
                level=NotificationLevel.ERROR,
                title="Invalid Header",
            )
            self._update_confirm_button_state()
            return preview

        table_rows = [
            {
                "row": item.row_number,
                "status": ValidationStatus.PASS.value if item.is_valid else ValidationStatus.FAIL.value,
                "workspace_name": item.workspace_name,
                "workspace_id": item.workspace_id,
                "report_name": item.report_name,
                "dataset_id": item.dataset_id,
                "active": item.active_raw,
                "errors": "; ".join(item.errors) if item.errors else "",
            }
            for item in preview.rows
        ]
        self.preview_table.set_rows(table_rows)

        valid_count = len(preview.valid_rows)
        invalid_count = len(preview.invalid_rows)

        if not preview.rows:
            self.skip_invalid_checkbox.setVisible(False)
            self.banner.show_message(
                "No data rows found in the selected file.",
                level=NotificationLevel.WARNING,
                title="Empty File",
            )
        elif invalid_count == 0:
            self.skip_invalid_checkbox.setVisible(False)
            self.banner.show_message(
                f"All {valid_count} row(s) passed validation and are ready to import.",
                level=NotificationLevel.SUCCESS,
                title="Preview Ready",
            )
        else:
            self.skip_invalid_checkbox.setChecked(False)
            self.skip_invalid_checkbox.setVisible(valid_count > 0)
            self.banner.show_message(
                f"Found {valid_count} valid row(s) and {invalid_count} invalid row(s). "
                "Review the errors column below before importing.",
                level=NotificationLevel.WARNING if valid_count > 0 else NotificationLevel.ERROR,
                title="Validation Issues Found",
            )

        self._update_confirm_button_state()
        return preview

    def _update_confirm_button_state(self) -> None:
        if self._preview is None or self._preview.missing_columns:
            self.confirm_button.setEnabled(False)
            return

        valid_count = len(self._preview.valid_rows)
        invalid_count = len(self._preview.invalid_rows)
        if valid_count == 0:
            self.confirm_button.setEnabled(False)
        elif invalid_count > 0:
            self.confirm_button.setEnabled(self.skip_invalid_checkbox.isChecked())
        else:
            self.confirm_button.setEnabled(True)

    def _browse_file(self) -> None:
        selected, _ = QFileDialog.getOpenFileName(
            self,
            "Select Registration CSV or Excel File",
            "",
            "Registration Files (*.csv *.xlsx);;CSV Files (*.csv);;Excel Files (*.xlsx)",
        )
        if selected:
            self.load_file_preview(Path(selected))

    def _export_template(self) -> None:
        selected, _ = QFileDialog.getSaveFileName(
            self,
            "Export Blank Registration Template",
            "powerbi_registrations_template.xlsx",
            "Excel Workbook (*.xlsx);;CSV File (*.csv)",
        )
        if not selected:
            return
        try:
            saved_path = self._registry.export_template(Path(selected))
            self.banner.show_message(
                f"Blank template exported to {saved_path}",
                level=NotificationLevel.SUCCESS,
                title="Template Saved",
            )
        except ValidationConfigError as exc:
            self.banner.show_message(exc.user_message, level=NotificationLevel.ERROR, title="Export Failed")

    def _confirm_import(self) -> None:
        if self._preview is None:
            return
        self._confirmed_rows = [
            row.parsed for row in self._preview.valid_rows if row.parsed is not None
        ]
        self.accept()
