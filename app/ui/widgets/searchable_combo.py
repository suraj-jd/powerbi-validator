"""Searchable editable combo box supporting list selection and free-form manual fallback."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QComboBox, QCompleter


class SearchableComboBox(QComboBox):
    """Editable QComboBox with case-insensitive substring completion and manual entry fallback."""

    def __init__(self, parent: QComboBox | None = None) -> None:
        super().__init__(parent)
        self.setEditable(True)
        self.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)

        completer = QCompleter(self)
        completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        completer.setFilterMode(Qt.MatchFlag.MatchContains)
        self.setCompleter(completer)

        # Style line edit placeholder and colors
        line_edit = self.lineEdit()
        if line_edit is not None:
            line_edit.setClearButtonEnabled(True)

    def set_items(self, items: list[str], placeholder: str = "-- Select or type name --") -> None:
        """Populate items while preserving current manual text if possible."""
        current = self.current_text()
        self.blockSignals(True)
        self.clear()
        if placeholder:
            self.addItem(placeholder, "")
        for item in items:
            self.addItem(item, item)

        completer = self.completer()
        if completer is not None:
            completer.setModel(self.model())

        # If previous text matches an item, select it; otherwise keep previous text as manual entry
        if current:
            idx = self.findText(current, Qt.MatchFlag.MatchFixedString)
            if idx >= 0:
                self.setCurrentIndex(idx)
            else:
                self.setEditText(current)
        else:
            self.setCurrentIndex(0 if placeholder else -1)
        self.blockSignals(False)

    def current_text(self) -> str:
        """Return the trimmed current text, ignoring placeholder items."""
        data = self.currentData()
        text = self.currentText().strip()
        if text.startswith("--") and text.endswith("--"):
            return ""
        return text

    def set_manual_text(self, text: str) -> None:
        """Set custom or manual text without requiring it to be in the items list."""
        self.setEditText(text.strip())
