"""Modal dialog for adding or editing a Power BI workspace, report, and dataset registration."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from app.integrations.file_import import RegistrationInput, validate_registration_fields
from app.services.registry_service import RegistrationRecord


class RegistrationDialog(QDialog):
    """Add or edit one Workspace / Report / Semantic Model registration."""

    def __init__(
        self,
        *,
        existing: RegistrationRecord | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._existing = existing
        self._result_input: RegistrationInput | None = None

        is_edit = existing is not None
        self.setWindowTitle("Edit Workspace / Dataset" if is_edit else "Add Workspace / Dataset")
        self.setModal(True)
        self.setMinimumWidth(520)
        self.setObjectName("ConfirmDialog")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(14)

        title = QLabel(
            "Edit Workspace & Dataset Registration"
            if is_edit
            else "Register Workspace, Report & Semantic Model"
        )
        title.setObjectName("DialogTitle")
        layout.addWidget(title)

        hint = QLabel(
            "Workspace ID and Dataset ID must be valid Power BI GUIDs. "
            "Multiple reports may share the same Dataset ID when distinguished by Report ID."
        )
        hint.setObjectName("InfoBanner")
        hint.setWordWrap(True)
        layout.addWidget(hint)

        form = QFormLayout()
        form.setSpacing(10)

        self.workspace_name_input = QLineEdit(existing.workspace_name if existing else "")
        self.workspace_name_input.setObjectName("SearchInput")
        self.workspace_name_input.setPlaceholderText("e.g. Bosch Analytics")
        form.addRow("Workspace Name *:", self.workspace_name_input)

        self.workspace_id_input = QLineEdit(existing.workspace_id if existing else "")
        self.workspace_id_input.setObjectName("SearchInput")
        self.workspace_id_input.setPlaceholderText("xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx")
        form.addRow("Workspace ID *:", self.workspace_id_input)

        self.report_name_input = QLineEdit(existing.report_name if existing else "")
        self.report_name_input.setObjectName("SearchInput")
        self.report_name_input.setPlaceholderText("e.g. Employee Dashboard")
        form.addRow("Report Name *:", self.report_name_input)

        self.report_id_input = QLineEdit(existing.report_id or "" if existing else "")
        self.report_id_input.setObjectName("SearchInput")
        self.report_id_input.setPlaceholderText("Recommended GUID (optional)")
        form.addRow("Report ID:", self.report_id_input)

        self.dataset_name_input = QLineEdit(existing.dataset_name or "" if existing else "")
        self.dataset_name_input.setObjectName("SearchInput")
        self.dataset_name_input.setPlaceholderText("Friendly semantic model name (optional)")
        form.addRow("Dataset / Model Name:", self.dataset_name_input)

        self.dataset_id_input = QLineEdit(existing.dataset_id if existing else "")
        self.dataset_id_input.setObjectName("SearchInput")
        self.dataset_id_input.setPlaceholderText("xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx")
        form.addRow("Dataset ID *:", self.dataset_id_input)

        self.active_checkbox = QCheckBox("Active (include in validation)")
        self.active_checkbox.setChecked(existing.is_active if existing else True)
        form.addRow("Status:", self.active_checkbox)

        layout.addLayout(form)

        self.error_label = QLabel("")
        self.error_label.setStyleSheet("color: #B91C1C; font-size: 12px; font-weight: 500;")
        self.error_label.setWordWrap(True)
        self.error_label.hide()
        layout.addWidget(self.error_label)

        buttons = QHBoxLayout()
        buttons.setSpacing(10)
        buttons.addStretch(1)

        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.setObjectName("SecondaryButton")
        self.cancel_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.cancel_button.clicked.connect(self.reject)
        buttons.addWidget(self.cancel_button)

        self.save_button = QPushButton("Save Registration")
        self.save_button.setObjectName("PrimaryButton")
        self.save_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.save_button.setDefault(True)
        self.save_button.clicked.connect(self._validate_and_accept)
        buttons.addWidget(self.save_button)

        layout.addLayout(buttons)

    @property
    def registration_input(self) -> RegistrationInput | None:
        return self._result_input

    def _validate_and_accept(self) -> None:
        parsed, errors = validate_registration_fields(
            workspace_name=self.workspace_name_input.text(),
            workspace_id=self.workspace_id_input.text(),
            report_name=self.report_name_input.text(),
            report_id=self.report_id_input.text(),
            dataset_name=self.dataset_name_input.text(),
            dataset_id=self.dataset_id_input.text(),
            is_active=self.active_checkbox.isChecked(),
        )
        if errors or parsed is None:
            self.error_label.setText("\n".join(f"• {err}" for err in errors))
            self.error_label.show()
            return

        self.error_label.hide()
        self._result_input = parsed
        self.accept()
