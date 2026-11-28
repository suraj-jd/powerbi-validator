"""Shared presentation controls for the desktop application.

These controls present service data without owning persistence or execution.
"""

from __future__ import annotations

import re

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QAbstractItemView, QBoxLayout, QCheckBox, QDialog, QFrame, QHBoxLayout, QHeaderView, QLabel,
    QMenu, QPushButton, QScrollArea, QTableWidget, QTableWidgetItem,
    QVBoxLayout, QWidget,
)

from app.ui.theme import ASSETS_DIR, COLORS, make_nav_icon
from app.ui.widgets.smooth_scroller import apply_smooth_scrolling


STATUS = {
    "PASS": ("Passed", "check", "#15803D", "#ECFDF3", "The check met its configured condition."),
    "FAIL": ("Failed", "failed", "#B91C1C", "#FEF2F2", "The data did not meet the configured condition."),
    "WARNING": ("Warning", "warning", "#B45309", "#FFFBEB", "Review the result before relying on it."),
    "ERROR": ("Execution error", "error", "#7E22CE", "#FAF5FF", "The check could not be evaluated."),
}


def mask_email_text(text: str) -> str:
    return re.sub(r"[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+", "[email hidden]", text)


def account_privacy_enabled(widget: QWidget) -> bool:
    current = widget
    while current is not None:
        value = current.property("hideAccountEmail")
        if value is not None:
            return bool(value)
        current = current.parentWidget()
    return False


def status_key(value) -> str:
    return str(getattr(value, "value", value)).upper()


def status_presentation(value):
    return STATUS.get(status_key(value), ("Not run", "history", "#64748B", "#F1F5F9", "No validation result is available."))


def style_status_label(label: QLabel, value) -> None:
    title, _, color, background, description = status_presentation(value)
    label.setText(title)
    label.setToolTip(description)
    label.setStyleSheet(
        f"color: {color}; background: {background}; border: 1px solid {background}; "
        "border-radius: 5px; padding: 5px 10px; font-size: 12px; font-weight: 600;"
    )


def action_button(text: str, icon: str = "", *, primary=False, danger=False) -> QPushButton:
    button = QPushButton(text)
    button.setObjectName("DangerButton" if danger else "PrimaryButton" if primary else "SecondaryButton")
    button.setCursor(Qt.CursorShape.PointingHandCursor)
    button.setAccessibleName(text)
    if icon:
        button.setIcon(make_nav_icon(icon, "#FFFFFF" if primary else "#B91C1C" if danger else COLORS["muted"]))
        button.setIconSize(QSize(16, 16))
    return button


def polish_button(button: QPushButton) -> None:
    """Use native SVG icons and consistent roles for existing action buttons."""
    if button.objectName() not in ("PrimaryButton", "SecondaryButton", "DangerButton"):
        return
    text = button.text().strip()
    while text and not (text[0].isalnum() or text[0] in "+("):
        text = text[1:].lstrip()
    if text:
        button.setText(text)
    button.setStyleSheet("")
    button.setMinimumHeight(34)
    button.setAccessibleName(text)
    button.setAutoDefault(False)
    if button.objectName() == "DangerButton":
        button.setDefault(False)
    if button.icon().isNull():
        words = text.lower()
        for word, icon in [("save", "save"), ("backup", "database"), ("apply", "check"), ("import", "import"),
                           ("export", "export"), ("download", "export"), ("refresh", "refresh"),
                           ("sync", "refresh"), ("run", "run"), ("delete", "delete"),
                           ("copy", "copy"), ("cancel", "close"), ("close", "close"),
                           ("configure", "settings"), ("test alert", "alerts")]:
            if word in words:
                color = "#FFFFFF" if button.objectName() == "PrimaryButton" else COLORS["muted"]
                button.setIcon(make_nav_icon(icon, color))
                break


class PageHeader(QWidget):
    def __init__(self, title: str, subtitle: str, parent=None):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        text = QVBoxLayout()
        self.title = QLabel(title)
        self.title.setObjectName("PageTitle")
        self.subtitle = QLabel(subtitle)
        self.subtitle.setObjectName("PageSubtitle")
        self.subtitle.setWordWrap(True)
        text.addWidget(self.title)
        text.addWidget(self.subtitle)
        layout.addLayout(text, 1)
        self.actions = QHBoxLayout()
        layout.addLayout(self.actions)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.layout().setDirection(QBoxLayout.Direction.TopToBottom if self.width() < 880 else QBoxLayout.Direction.LeftToRight)


class MetricCard(QFrame):
    def __init__(self, outcome: str, parent=None):
        super().__init__(parent)
        self.setObjectName("Card")
        title, icon, color, background, tip = status_presentation(outcome)
        self.setToolTip(tip)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        symbol = QLabel()
        symbol.setPixmap(make_nav_icon(icon, color, 24).pixmap(24, 24))
        symbol.setFixedSize(34, 34)
        symbol.setAlignment(Qt.AlignmentFlag.AlignCenter)
        symbol.setStyleSheet(f"background: {background}; border-radius: 6px;")
        layout.addWidget(symbol)
        text = QVBoxLayout()
        text.setSpacing(2)
        self.value = QLabel("0")
        self.value.setStyleSheet("font-size: 22px; font-weight: 700; color: #16243A;")
        text.addWidget(self.value)
        text.addWidget(QLabel(title))
        layout.addLayout(text, 1)


class ToggleSwitch(QCheckBox):
    """A native, keyboard-accessible checkbox with vector switch indicators."""

    def __init__(self, parent=None):
        super().__init__("Off", parent)
        self.setFixedSize(88, 28)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setAccessibleName("Enable automation")
        self.setStyleSheet(
            'QCheckBox { spacing: 8px; font-size: 12px; font-weight: 600; } '
            'QCheckBox::indicator { width: 42px; height: 24px; image: url("'
            + (ASSETS_DIR / "toggle-off.svg").as_posix() + '"); } '
            'QCheckBox::indicator:checked { image: url("'
            + (ASSETS_DIR / "toggle-on.svg").as_posix() + '"); }'
        )
        self.toggled.connect(lambda enabled: self.setText("On" if enabled else "Off"))

    def hitButton(self, position):
        return self.rect().contains(position)


class SortItem(QTableWidgetItem):
    def __lt__(self, other):
        left = self.data(Qt.ItemDataRole.UserRole + 1)
        right = other.data(Qt.ItemDataRole.UserRole + 1)
        return left < right if left is not None and right is not None else self.text().casefold() < other.text().casefold()


class ResultsTable(QTableWidget):
    """Same result columns and stable identities in Overview and History."""

    visibility_changed = Signal()
    HEADERS = ["Status", "Check name", "Validated At (UTC)", "Target", "Check type",
               "Actual value", "Expected value", "Deviation", "Duration", "Details"]

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("DataTable")
        self.setColumnCount(len(self.HEADERS))
        self.setHorizontalHeaderLabels(self.HEADERS)
        self._results = {}
        self.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.horizontalHeader().setMinimumSectionSize(70)
        self.horizontalHeader().setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.horizontalHeader().customContextMenuRequested.connect(self._column_menu)
        for index, width in enumerate([125, 230, 200, 190, 155, 150, 150, 160, 95, 80]):
            self.setColumnWidth(index, width)
        for index in (3, 4, 7, 8):
            self.setColumnHidden(index, True)
        self.verticalHeader().hide()
        self.verticalHeader().setDefaultSectionSize(34)
        self.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.setAlternatingRowColors(False)
        self.setShowGrid(False)
        self.setSortingEnabled(True)
        self.horizontalHeader().setSortIndicator(-1, Qt.SortOrder.AscendingOrder)
        self.setMinimumHeight(240)
        apply_smooth_scrolling(self)

    def _column_menu(self, position):
        menu = QMenu(self)
        for index, title in enumerate(self.HEADERS):
            action = menu.addAction(title)
            action.setCheckable(True)
            action.setChecked(not self.isColumnHidden(index))
            action.setEnabled(index not in (0, 1, 2, 9))
            action.toggled.connect(lambda checked, col=index: self.setColumnHidden(col, not checked))
        menu.exec(self.horizontalHeader().mapToGlobal(position))

    def set_results(self, results):
        from app.services.sheet_service import FRIENDLY_TEST_NAMES

        self.setSortingEnabled(False)
        self.setRowCount(len(results))
        self._results = {result.id: result for result in results}
        for row, result in enumerate(results):
            _, icon, color, _, explanation = status_presentation(result.status)
            values = [status_key(result.status), result.rule_name, result.validated_at_display,
                      result.target_display, FRIENDLY_TEST_NAMES.get(result.validation_type, result.validation_type),
                      result.actual_value or "—", result.expected_value or "—", result.deviation or "None",
                      f"{result.duration_ms} ms", "Details"]
            for col, value in enumerate(values):
                item = SortItem(value)
                item.setToolTip(value)
                if col == 0:
                    item.setData(Qt.ItemDataRole.UserRole, result.id)
                    item.setIcon(make_nav_icon(icon, color, 16))
                    item.setForeground(QColor(color))
                    font = item.font()
                    font.setBold(True)
                    item.setFont(font)
                    item.setToolTip(explanation)
                elif col == 1:
                    item.setToolTip(result.result_summary)
                elif col == 2:
                    item.setData(Qt.ItemDataRole.UserRole + 1, result.validated_at.timestamp())
                    item.setToolTip(f"Check completed: {result.validated_at_display}\nRun #{result.validation_run_id}")
                elif col == 8:
                    item.setData(Qt.ItemDataRole.UserRole + 1, result.duration_ms)
                elif col == 9:
                    item.setForeground(QColor(COLORS["primary"]))
                self.setItem(row, col, item)
        self.setSortingEnabled(True)

    def result_at(self, row):
        item = self.item(row, 0)
        return self._results.get(item.data(Qt.ItemDataRole.UserRole)) if item else None


class EnterpriseDialog(QDialog):
    """Consistent dialog sizing, scrollable forms, and explicit action buttons."""

    def showEvent(self, event):
        if not getattr(self, "_enterprise_prepared", False):
            self._enterprise_prepared = True
            # Existing dialogs own their signals. Only presentation is normalized here.
            if account_privacy_enabled(self):
                for label in self.findChildren(QLabel):
                    label.setText(mask_email_text(label.text()))
                    label.setToolTip(mask_email_text(label.toolTip()))
            for frame in self.findChildren(QFrame):
                stylesheet = frame.styleSheet()
                if re.search(r"QFrame(?=\s*\{|:hover)", stylesheet):
                    frame.setProperty("enterpriseSurface", True)
                    frame.setStyleSheet(re.sub(r"QFrame(?=\s*\{|:hover)",
                        'QFrame[enterpriseSurface="true"]', stylesheet))
            for button in self.findChildren(QPushButton):
                polish_button(button)
            root = self.layout()
            if root is not None:
                root.setAlignment(Qt.AlignmentFlag.AlignTop)
            # Transfer the complete layout through QWidget.setLayout. Qt handles
            # ownership of nested layouts; moving raw QLayoutItems is unsafe.
            if isinstance(root, QVBoxLayout):
                visibility = [(child, not child.isHidden()) for child in self.findChildren(
                    QWidget, options=Qt.FindChildOption.FindDirectChildrenOnly)]
                body = QWidget()
                body.setLayout(root)
                footer = None
                if root.count() and isinstance(root.itemAt(root.count() - 1).layout(), QHBoxLayout):
                    footer = root.takeAt(root.count() - 1).layout()
                    footer.setParent(None)
                scroll = QScrollArea()
                scroll.setWidgetResizable(True)
                scroll.setFrameShape(QFrame.Shape.NoFrame)
                scroll.setWidget(body)
                outer = QVBoxLayout(self)
                outer.setContentsMargins(0, 0, 0, 0)
                outer.addWidget(scroll)
                if footer is not None:
                    footer.setContentsMargins(16, 8, 16, 12)
                    outer.addLayout(footer)
                    self._enterprise_footer = footer
                self._enterprise_scroll = scroll
                self._enterprise_body = body
                body.show()
                scroll.show()
                for child, visible in visibility:
                    child.setVisible(visible)
            screen = self.screen()
            if screen and self.isWindow():
                available = screen.availableGeometry()
                self.setMinimumWidth(min(self.minimumWidth(), max(320, available.width() - 64)))
                self.setMinimumHeight(min(self.minimumHeight(), max(240, available.height() - 80)))
                self.resize(min(max(self.width(), 560), available.width() - 48),
                            min(max(self.sizeHint().height(), 400), available.height() - 64))
        super().showEvent(event)
