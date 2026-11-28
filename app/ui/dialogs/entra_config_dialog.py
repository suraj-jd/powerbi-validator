"""Dialog for configuring non-secret Microsoft Entra ID public-client identifiers."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from app.auth.msal_auth import is_valid_guid, is_valid_tenant


from app.ui.widgets.enterprise import EnterpriseDialog

class EntraConfigDialog(EnterpriseDialog):
    """Modal form to configure Microsoft Entra Application (Client) ID and Tenant ID."""

    def __init__(
        self,
        *,
        client_id: str = "",
        tenant_id: str = "organizations",
        save_button_text: str = "Save Settings",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Configure Microsoft Entra App")
        self.setModal(True)
        self.setMinimumWidth(500)
        self.setObjectName("ConfirmDialog")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(14)

        title = QLabel("Microsoft Entra ID Public Client Settings")
        title.setObjectName("DialogTitle")
        layout.addWidget(title)

        note = QLabel(
            "Enter the Application (Client) ID and Directory (Tenant) ID from your "
            'Microsoft Entra desktop app registration (<a href="https://entra.microsoft.com">entra.microsoft.com</a>, '
            "redirect URI: <code>http://localhost</code>). No client secret or password is required."
        )
        note.setObjectName("InfoBanner")
        note.setWordWrap(True)
        note.setOpenExternalLinks(True)
        layout.addWidget(note)

        form = QFormLayout()
        form.setSpacing(10)

        self.client_id_input = QLineEdit(client_id.strip())
        self.client_id_input.setObjectName("SearchInput")
        self.client_id_input.setPlaceholderText("e.g. 12345678-1234-1234-1234-1234567890ab")
        self.client_id_input.setToolTip("Your Microsoft application ID used to connect.")
        form.addRow("Application (Client) ID:", self.client_id_input)

        self.tenant_id_input = QLineEdit(tenant_id.strip() or "organizations")
        self.tenant_id_input.setObjectName("SearchInput")
        self.tenant_id_input.setPlaceholderText("organizations or your Tenant GUID")
        self.tenant_id_input.setToolTip("Your Microsoft organization ID, or leave as 'organizations'.")
        form.addRow("Directory (Tenant) ID:", self.tenant_id_input)

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
        self.cancel_button.setToolTip("Close without saving changes.")
        self.cancel_button.clicked.connect(self.reject)
        buttons.addWidget(self.cancel_button)

        self.save_button = QPushButton(save_button_text)
        self.save_button.setObjectName("PrimaryButton")
        self.save_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.save_button.setToolTip("Save these Microsoft login settings.")
        self.save_button.setDefault(True)
        self.save_button.clicked.connect(self._validate_and_accept)
        buttons.addWidget(self.save_button)

        layout.addLayout(buttons)

    @property
    def client_id(self) -> str:
        return self.client_id_input.text().strip()

    @property
    def tenant_id(self) -> str:
        return self.tenant_id_input.text().strip() or "organizations"

    def _validate_and_accept(self) -> None:
        client_id = self.client_id
        tenant_id = self.tenant_id

        if not is_valid_guid(client_id):
            self.error_label.setText(
                "Please enter a valid Application (Client) ID in GUID format "
                "(xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx)."
            )
            self.error_label.show()
            return

        if not is_valid_tenant(tenant_id):
            self.error_label.setText(
                "Please enter a valid Tenant GUID, 'organizations', or verified tenant domain."
            )
            self.error_label.show()
            return

        self.error_label.hide()
        self.accept()
