"""Reusable inline notification banner for info, success, warning, and error messages."""

from __future__ import annotations

from pathlib import Path
import subprocess
import sys
from typing import Callable

from PySide6.QtCore import Qt, QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton, QSizePolicy, QWidget

from app.core.status import NotificationLevel


def open_exported_file(path: Path | str) -> None:
    """Open the exported file with the OS default application."""
    resolved = Path(path).resolve()
    QDesktopServices.openUrl(QUrl.fromLocalFile(str(resolved)))


def open_file_location(path: Path | str) -> None:
    """Open the containing folder and highlight the exported file when supported."""
    resolved = Path(path).resolve()
    if sys.platform == "win32" and resolved.exists():
        subprocess.Popen(["explorer", "/select,", str(resolved)])
    else:
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(resolved.parent)))

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
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self.setMinimumHeight(38)
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

        self._actions_layout = QHBoxLayout()
        self._actions_layout.setContentsMargins(0, 0, 0, 0)
        self._actions_layout.setSpacing(6)
        layout.addLayout(self._actions_layout)

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

    def _clear_actions(self) -> None:
        while self._actions_layout.count() > 0:
            item = self._actions_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.hide()
                widget.setParent(None)
                widget.deleteLater()

    def show_export_success(
        self,
        message: str,
        file_path: Path | str,
        *,
        title: str = "Export Complete",
    ) -> None:
        """Display a success banner with Open File and Open File Location buttons."""
        target = Path(file_path).resolve()
        self.show_message(
            message,
            level=NotificationLevel.SUCCESS,
            title=title,
            actions=[
                ("Open File", lambda p=target: open_exported_file(p)),
                ("Open File Location", lambda p=target: open_file_location(p)),
            ],
        )

    def show_message(
        self,
        message: str,
        level: NotificationLevel = NotificationLevel.INFO,
        title: str | None = None,
        actions: list[tuple[str, Callable[[], None]]] | None = None,
    ) -> None:
        """Display the banner with the given severity level, message, and optional action buttons."""
        palette = _LEVEL_STYLES[level]
        self._current_level = level
        self._current_message = message

        self._level_label.setText(title.upper() if title else palette["badge"])
        self._message_label.setText(message)
        self._clear_actions()
        for label, callback in actions or []:
            btn = QPushButton(label)
            btn.setObjectName("BannerActionButton")
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.clicked.connect(lambda _=False, cb=callback: cb())
            self._actions_layout.addWidget(btn, alignment=Qt.AlignmentFlag.AlignTop)

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
                padding: 3px 8px;
                border: 1px solid {palette['border']};
                border-radius: 4px;
                background-color: #FFFFFF;
            }}
            QLabel {{
                color: {palette['fg']};
                font-size: 13px;
            }}
            QPushButton#BannerActionButton {{
                background-color: #FFFFFF;
                color: {palette['fg']};
                border: 1px solid {palette['border']};
                border-radius: 5px;
                font-size: 12px;
                font-weight: 600;
                padding: 4px 10px;
            }}
            QPushButton#BannerActionButton:hover {{
                background-color: #F8FAFC;
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
        self._clear_actions()
        self._current_message = ""
        self.hide()
        self.dismissed.emit()
