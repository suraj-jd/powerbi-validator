"""Light enterprise theme and crisp SVG icon helpers for the desktop shell."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QByteArray, Qt
from PySide6.QtGui import QIcon, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer

ASSETS_DIR = Path(__file__).resolve().parent.parent.parent / "assets"
CHEVRON_DOWN_PATH = (ASSETS_DIR / "chevron_down.svg").as_posix()
CHEVRON_ACTIVE_PATH = (ASSETS_DIR / "chevron_down_active.svg").as_posix()

APP_STYLESHEET = """
QMainWindow {
    background-color: #F4F7FB;
}

QWidget {
    font-family: "Segoe UI", "Inter", sans-serif;
    font-size: 13px;
    color: #0F172A;
}

QToolTip {
    background-color: #0F172A;
    color: #F8FAFC;
    border: 1px solid #334155;
    border-radius: 5px;
    padding: 6px 10px;
    font-size: 11px;
    font-weight: 500;
}

/* Dark Navy Sidebar */
QFrame#Sidebar {
    background-color: #13294B;
    border: none;
}

QLabel#SidebarBrandTitle {
    color: #FFFFFF;
    font-size: 13px;
    font-weight: 700;
    padding: 0px;
}

QLabel#SidebarBrandSubtitle {
    color: #94A3B8;
    font-size: 11px;
    padding: 0px;
}

QFrame#SidebarDivider {
    background-color: #243E66;
    max-height: 1px;
    min-height: 1px;
}

QPushButton#NavButton {
    background-color: transparent;
    color: #CBD5E1;
    border: none;
    border-radius: 8px;
    text-align: left;
    padding: 11px 14px;
    font-size: 13px;
    font-weight: 500;
}

QPushButton#NavButton:hover {
    background-color: #1E3A63;
    color: #FFFFFF;
}

QPushButton#NavButton:checked {
    background-color: #1668DC;
    color: #FFFFFF;
    font-weight: 600;
}

QPushButton#ExitButton {
    background-color: transparent;
    color: #CBD5E1;
    border: 1px solid #2A4670;
    border-radius: 8px;
    text-align: left;
    padding: 9px 14px;
    font-size: 13px;
    font-weight: 500;
}

QPushButton#ExitButton:hover {
    background-color: #1E3A63;
    border-color: #3B5B8C;
    color: #FFFFFF;
}

QLabel#SidebarFooterNote {
    color: #94A3B8;
    font-size: 11px;
}

/* Main Content Area */
QScrollArea#PageScrollArea {
    background-color: #F4F7FB;
    border: none;
}

QWidget#PageContainer {
    background-color: #F4F7FB;
}

QFrame#Card {
    background-color: #FFFFFF;
    border: 1px solid #E2E8F0;
    border-radius: 12px;
}

QFrame#Card QLabel {
    border: none;
    background-color: transparent;
}

QLabel#PageTitle {
    color: #0F172A;
    font-size: 22px;
    font-weight: 700;
}

QLabel#PageSubtitle {
    color: #475569;
    font-size: 13px;
}

QLabel#SectionTitle {
    color: #0F172A;
    font-size: 15px;
    font-weight: 600;
}

QLabel#BodyText {
    color: #334155;
    font-size: 13px;
    line-height: 1.5;
}

QLabel#StageBadge {
    background-color: #EBF3FF;
    color: #1668DC;
    border: 1px solid #BFDBFE;
    border-radius: 12px;
    padding: 4px 12px;
    font-size: 12px;
    font-weight: 600;
}

QLabel#InfoBanner {
    background-color: #F8FAFC;
    color: #475569;
    border: 1px solid #E2E8F0;
    border-radius: 8px;
    padding: 12px 14px;
    font-size: 12px;
}

QStatusBar {
    background-color: #FFFFFF;
    border-top: 1px solid #E2E8F0;
    color: #475569;
    font-size: 12px;
}

/* Shared Enterprise Buttons */
QPushButton#PrimaryButton {
    background-color: #1668DC;
    color: #FFFFFF;
    border: none;
    border-radius: 7px;
    padding: 8px 16px;
    font-weight: 600;
}

QPushButton#PrimaryButton:hover {
    background-color: #1357BA;
}

QPushButton#SecondaryButton {
    background-color: #FFFFFF;
    color: #334155;
    border: 1px solid #CBD5E1;
    border-radius: 7px;
    padding: 8px 16px;
    font-weight: 500;
}

QPushButton#SecondaryButton:hover {
    background-color: #F8FAFC;
    border-color: #94A3B8;
}

QPushButton#DangerButton {
    background-color: #DC2626;
    color: #FFFFFF;
    border: none;
    border-radius: 7px;
    padding: 8px 16px;
    font-weight: 600;
}

QPushButton#DangerButton:hover {
    background-color: #B91C1C;
}

/* Shared Inputs & Enterprise Table */
QLineEdit#SearchInput,
QLineEdit {
    background-color: #FFFFFF;
    border: 1px solid #CBD5E1;
    border-radius: 7px;
    padding: 6px 10px;
    color: #0F172A;
    min-height: 20px;
}

QLineEdit#SearchInput:focus,
QLineEdit:focus {
    border-color: #1668DC;
}

QComboBox,
QComboBox#FilterCombo {
    combobox-popup: 0;
    background-color: #FFFFFF;
    border: 1px solid #CBD5E1;
    border-radius: 7px;
    padding: 5px 28px 5px 10px;
    color: #0F172A;
    min-height: 20px;
    font-size: 12px;
}

QComboBox:hover,
QComboBox#FilterCombo:hover {
    border-color: #94A3B8;
    background-color: #F8FAFC;
}

QComboBox:focus,
QComboBox#FilterCombo:focus {
    border: 1.5px solid #1668DC;
    background-color: #FFFFFF;
}

QComboBox::drop-down {
    subcontrol-origin: padding;
    subcontrol-position: top right;
    width: 24px;
    border-left: none;
    border-top-right-radius: 7px;
    border-bottom-right-radius: 7px;
}

QComboBox::down-arrow {
    image: url("__CHEVRON_DOWN__");
    width: 10px;
    height: 10px;
}

QComboBox::down-arrow:hover,
QComboBox::down-arrow:focus {
    image: url("__CHEVRON_ACTIVE__");
}

/* Modern Dropdown Popup View */
QListView#ModernComboView,
QComboBox QAbstractItemView {
    background-color: #FFFFFF;
    border: 1px solid #CBD5E1;
    border-radius: 8px;
    padding: 4px;
    outline: none;
    font-size: 12px;
    selection-background-color: transparent;
}

QListView#ModernComboView::item,
QComboBox QAbstractItemView::item {
    padding: 6px 10px;
    min-height: 24px;
    border-radius: 5px;
    color: #0F172A;
    margin: 1px 2px;
}

QListView#ModernComboView::item:hover,
QComboBox QAbstractItemView::item:hover {
    background-color: #F1F5F9;
    color: #1668DC;
}

QListView#ModernComboView::item:selected,
QComboBox QAbstractItemView::item:selected {
    background-color: #EBF3FF;
    color: #1668DC;
    font-weight: 600;
}

/* Modern scrollbars across all tables, lists, and scroll areas */
QScrollBar:vertical {
    width: 8px;
    background: transparent;
    margin: 2px 1px 2px 1px;
    border: none;
    border-radius: 4px;
}

QScrollBar::handle:vertical {
    background: #CBD5E1;
    border-radius: 4px;
    min-height: 24px;
}

QScrollBar::handle:vertical:hover {
    background: #94A3B8;
}

QScrollBar::add-line:vertical,
QScrollBar::sub-line:vertical {
    height: 0px;
    border: none;
    background: none;
}

QScrollBar::add-page:vertical,
QScrollBar::sub-page:vertical {
    background: none;
}

QScrollBar:horizontal {
    height: 8px;
    background: transparent;
    margin: 1px 2px 1px 2px;
    border: none;
    border-radius: 4px;
}

QScrollBar::handle:horizontal {
    background: #CBD5E1;
    border-radius: 4px;
    min-width: 24px;
}

QScrollBar::handle:horizontal:hover {
    background: #94A3B8;
}

QScrollBar::add-line:horizontal,
QScrollBar::sub-line:horizontal {
    width: 0px;
    border: none;
    background: none;
}

QScrollBar::add-page:horizontal,
QScrollBar::sub-page:horizontal {
    background: none;
}

/* Slim scrollbars for dropdown popups */
QListView#ModernComboView QScrollBar:vertical,
QComboBox QAbstractItemView QScrollBar:vertical {
    width: 6px;
    background: transparent;
    margin: 4px 1px 4px 0px;
    border: none;
}

QListView#ModernComboView QScrollBar::handle:vertical,
QComboBox QAbstractItemView QScrollBar::handle:vertical {
    background: #CBD5E1;
    border-radius: 3px;
    min-height: 20px;
}

QListView#ModernComboView QScrollBar::handle:vertical:hover,
QComboBox QAbstractItemView QScrollBar::handle:vertical:hover {
    background: #94A3B8;
}

QListView#ModernComboView QScrollBar::add-line:vertical,
QListView#ModernComboView QScrollBar::sub-line:vertical,
QComboBox QAbstractItemView QScrollBar::add-line:vertical,
QComboBox QAbstractItemView QScrollBar::sub-line:vertical {
    height: 0px;
    border: none;
}

QTableView#EnterpriseTableView,
QTableWidget#DataTable,
QTableWidget {
    background-color: #FFFFFF;
    alternate-background-color: #F8FAFC;
    border: 1px solid #E2E8F0;
    border-radius: 8px;
    selection-background-color: #EBF3FF;
    selection-color: #0F172A;
    gridline-color: #E2E8F0;
    outline: none;
}

QTableView#EnterpriseTableView::item,
QTableWidget::item {
    padding: 6px 10px;
    border-bottom: 1px solid #F1F5F9;
}

QHeaderView::section {
    background-color: #F8FAFC;
    color: #334155;
    font-weight: 600;
    padding: 8px 10px;
    border: none;
    border-bottom: 1px solid #E2E8F0;
}

/* Tabs */
QTabWidget::pane {
    border: 1px solid #E2E8F0;
    border-radius: 8px;
    background-color: #FFFFFF;
    top: -1px;
}

QTabBar::tab {
    background-color: #F1F5F9;
    color: #475569;
    border: 1px solid #E2E8F0;
    border-bottom: none;
    border-top-left-radius: 6px;
    border-top-right-radius: 6px;
    padding: 8px 16px;
    margin-right: 4px;
    font-weight: 500;
}

QTabBar::tab:selected {
    background-color: #FFFFFF;
    color: #1668DC;
    font-weight: 600;
    border-color: #CBD5E1;
    border-bottom: 1px solid #FFFFFF;
}

/* Confirmation Dialog */
QDialog#ConfirmDialog {
    background-color: #FFFFFF;
}

QLabel#DialogTitle {
    color: #0F172A;
    font-size: 16px;
    font-weight: 700;
}
""".replace("__CHEVRON_DOWN__", CHEVRON_DOWN_PATH).replace("__CHEVRON_ACTIVE__", CHEVRON_ACTIVE_PATH)

_NAV_SVGS: dict[str, str] = {
    "home": (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" '
        'stroke="{color}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">'
        '<path d="M3 10.5L12 3l9 7.5"/>'
        '<path d="M5 9.5V20a1 1 0 0 0 1 1h4v-6h4v6h4a1 1 0 0 0 1-1V9.5"/>'
        "</svg>"
    ),
    "sheet_settings": (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" '
        'stroke="{color}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">'
        '<rect x="3" y="3" width="18" height="18" rx="2" ry="2"/>'
        '<line x1="3" y1="9" x2="21" y2="9"/>'
        '<line x1="3" y1="15" x2="21" y2="15"/>'
        '<line x1="9" y1="3" x2="9" y2="21"/>'
        '<line x1="15" y1="3" x2="15" y2="21"/>'
        "</svg>"
    ),
    "settings": (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" '
        'stroke="{color}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">'
        '<circle cx="12" cy="12" r="3"/>'
        '<path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06'
        "a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 1 1-4 0v-.09"
        "A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06"
        "a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 1 1 0-4h.09"
        "A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06"
        "a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 1 1 4 0v.09"
        "a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06"
        'a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 1 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z"/>'
        "</svg>"
    ),
    "history": (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" '
        'stroke="{color}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">'
        '<circle cx="12" cy="12" r="9"/>'
        '<polyline points="12 7 12 12 15.5 14"/>'
        "</svg>"
    ),
    "about": (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" '
        'stroke="{color}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">'
        '<circle cx="12" cy="12" r="9"/>'
        '<line x1="12" y1="16" x2="12" y2="12"/>'
        '<line x1="12" y1="8" x2="12.01" y2="8"/>'
        "</svg>"
    ),
    "exit": (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" '
        'stroke="{color}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">'
        '<path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"/>'
        '<polyline points="16 17 21 12 16 7"/>'
        '<line x1="21" y1="12" x2="9" y2="12"/>'
        "</svg>"
    ),
}


def make_nav_icon(name: str, color: str = "#E2E8F0", size: int = 18) -> QIcon:
    """Render a crisp vector QIcon from an embedded SVG template."""
    svg_template = _NAV_SVGS.get(name)
    if not svg_template:
        return QIcon()

    svg_bytes = QByteArray(svg_template.format(color=color).encode("utf-8"))
    renderer = QSvgRenderer(svg_bytes)
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    renderer.render(painter)
    painter.end()
    return QIcon(pixmap)
