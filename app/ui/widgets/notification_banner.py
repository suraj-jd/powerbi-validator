"""Reusable inline notification banner for info, success, warning, and error messages."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton, QWidget

from app.core.status import NotificationLevel

_LEVEL_STYLES: dict[NotificationLevel, dict[str, str]] = {
    NotificationLevel.INFO: {
        "bg": "#EFF6FF",
        "border": "#BFDBFE",
        "fg": "#1E40AF",
        "badge": "INFO",
    },
    NotificationLevel.SUCCESS: {
        "bg": "#F0FDF4",
        "border": "#BBF7D0",
        "fg": "#166534",
        "badge": "SUCCESS",
    },
    NotificationLevel.WARNING: {
        "bg": "#FFFBEB",
        "border": "#FDE68A",
        "fg": "#92400E",
        "badge": "WARNING",
    },
    NotificationLevel.ERROR: {
        "bg": "#FEF2F2",
        "border": "#FECACA",
        "fg": "#991B1B",
        "badge": "ERROR",
    },
}


class NotificationBanner(QFrame):
    """Dismissible status banner that supports thread-safe message posting."""

    message_requested = Signal(str, str, str)
    dismissed = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("NotificationBanner")
        self._current_level = NotificationLevel.INFO
        self._current_message = ""

        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 10, 12, 10)
        layout.setSpacing(10)

        self._level_label = QLabel()
        self._level_label.setObjectName("NotificationLevelTag")
        layout.addWidget(self._level_label, alignment=Qt.AlignmentFlag.AlignTop)

        self._message_label = QLabel()
        self._message_label.setWordWrap(True)
        self._message_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(self._message_label, stretch=1)

        self._dismiss_button = QPushButton("Dismiss")
        self._dismiss_button.setObjectName("BannerDismissButton")
        self._dismiss_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self._dismiss_button.clicked.connect(self.clear_message)
        layout.addWidget(self._dismiss_button, alignment=Qt.AlignmentFlag.AlignTop)

        self.message_requested.connect(self._on_message_requested)
        self.hide()

    @property
    def current_level(self) -> NotificationLevel:
        return self._current_level

    @property
    def current_message(self) -> str:
        return self._current_message

    def text(self) -> str:
        return self._current_message

    def post_message(
        self,
        message: str,
        level: NotificationLevel = NotificationLevel.INFO,
        title: str | None = None,
    ) -> None:
        """Thread-safe entry point to display a notification on the UI thread."""
        self.message_requested.emit(message, level.value, title or "")

    def _on_message_requested(self, message: str, level_value: str, title: str) -> None:
        try:
            level = NotificationLevel(level_value)
        except ValueError:
            level = NotificationLevel.INFO
        self.show_message(message, level=level, title=title or None)

    def show_message(
        self,
        message: str,
        level: NotificationLevel = NotificationLevel.INFO,
        title: str | None = None,
    ) -> None:
        """Display the banner with the given severity level and message."""
        palette = _LEVEL_STYLES[level]
        self._current_level = level
        self._current_message = message

        self._level_label.setText(title.upper() if title else palette["badge"])
        self._message_label.setText(message)

        self.setStyleSheet(
            f"""
            QFrame#NotificationBanner {{
                background-color: {palette['bg']};
                border: 1px solid {palette['border']};
                border-radius: 8px;
            }}
            QLabel#NotificationLevelTag {{
                color: {palette['fg']};
                font-size: 11px;
                font-weight: 700;
                padding: 2px 6px;
                border: 1px solid {palette['border']};
                border-radius: 4px;
                background-color: #FFFFFF;
            }}
            QLabel {{
                color: {palette['fg']};
                font-size: 13px;
            }}
            QPushButton#BannerDismissButton {{
                background-color: transparent;
                color: {palette['fg']};
                border: none;
                font-size: 12px;
                font-weight: 600;
                padding: 2px 8px;
            }}
            QPushButton#BannerDismissButton:hover {{
                text-decoration: underline;
            }}
            """
        )
        self.show()

    def clear_message(self) -> None:
        """Hide the banner and emit the dismissed signal."""
        self._current_message = ""
        self.hide()
        self.dismissed.emit()
