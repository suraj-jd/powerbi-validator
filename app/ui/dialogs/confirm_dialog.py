"""Reusable styled confirmation dialog."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)


class ConfirmDialog(QDialog):
    """Consistent confirmation modal for standard and destructive user actions."""

    def __init__(
        self,
        title: str,
        message: str,
        *,
        detail: str | None = None,
        confirm_text: str = "Confirm",
        cancel_text: str = "Cancel",
        destructive: bool = False,
        parent: QWidget | None = None,
        confirm_label: str | None = None,
    ) -> None:
        super().__init__(parent)
        if confirm_label:
            confirm_text = confirm_label
        self.setWindowTitle(title)
        self.setModal(True)
        self.setMinimumWidth(420)
        self.setObjectName("ConfirmDialog")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(14)

        title_label = QLabel(title)
        title_label.setObjectName("DialogTitle")
        title_label.setWordWrap(True)
        layout.addWidget(title_label)

        message_label = QLabel(message)
        message_label.setObjectName("BodyText")
        message_label.setWordWrap(True)
        layout.addWidget(message_label)

        if detail:
            detail_label = QLabel(detail)
            detail_label.setObjectName("InfoBanner")
            detail_label.setWordWrap(True)
            layout.addWidget(detail_label)

        button_row = QHBoxLayout()
        button_row.setSpacing(10)
        button_row.addStretch(1)

        self.cancel_button = QPushButton(cancel_text)
        self.cancel_button.setObjectName("SecondaryButton")
        self.cancel_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.cancel_button.clicked.connect(self.reject)
        button_row.addWidget(self.cancel_button)

        self.confirm_button = QPushButton(confirm_text)
        self.confirm_button.setObjectName("DangerButton" if destructive else "PrimaryButton")
        self.confirm_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.confirm_button.setDefault(True)
        self.confirm_button.clicked.connect(self.accept)
        button_row.addWidget(self.confirm_button)

        layout.addLayout(button_row)

    @classmethod
    def ask(
        cls,
        parent: QWidget | None,
        title: str,
        message: str,
        *,
        detail: str | None = None,
        confirm_text: str = "Confirm",
        cancel_text: str = "Cancel",
        destructive: bool = False,
    ) -> bool:
        """Display the dialog modally and return True if the user confirmed."""
        dialog = cls(
            title=title,
            message=message,
            detail=detail,
            confirm_text=confirm_text,
            cancel_text=cancel_text,
            destructive=destructive,
            parent=parent,
        )
        return dialog.exec() == QDialog.DialogCode.Accepted
