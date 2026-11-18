"""Main desktop window shell for Stage 0."""

from __future__ import annotations

import logging
from pathlib import Path

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QCloseEvent, QIcon
from PySide6.QtWidgets import (
    QButtonGroup,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QStackedWidget,
    QStatusBar,
    QVBoxLayout,
    QWidget,
)

from app import APP_NAME, APP_VERSION
from app.ui.pages.about_page import AboutPage
from app.ui.pages.history_page import HistoryPage
from app.ui.pages.home_page import HomePage
from app.ui.pages.settings_page import SettingsPage
from app.ui.theme import make_nav_icon

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
APP_ICON_PATH = PROJECT_ROOT / "assets" / "app_icon.svg"


class MainWindow(QMainWindow):
    """Primary desktop window with dark navy sidebar and page stack."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(f"{APP_NAME} v{APP_VERSION}")
        self.resize(1180, 760)
        self.setMinimumSize(900, 600)

        self._load_window_icon()

        self._pages: dict[str, QWidget] = {}
        self._nav_buttons: dict[str, QPushButton] = {}
        self._nav_group = QButtonGroup(self)
        self._nav_group.setExclusive(True)
        self._current_page_key: str = ""

        self._build_ui()
        self.navigate_to("home")

        logger.info("MainWindow initialized (%s v%s)", APP_NAME, APP_VERSION)

    def _load_window_icon(self) -> None:
        if APP_ICON_PATH.exists():
            icon = QIcon(str(APP_ICON_PATH))
            if not icon.isNull():
                self.setWindowIcon(icon)
                return
        logger.debug("App icon not found at %s; using default icon.", APP_ICON_PATH)

    def _build_ui(self) -> None:
        central = QWidget(self)
        root_layout = QHBoxLayout(central)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        sidebar = self._build_sidebar()
        root_layout.addWidget(sidebar)

        self._stack = QStackedWidget(central)
        root_layout.addWidget(self._stack, stretch=1)

        self._register_page("home", "Home", HomePage(self))
        self._register_page("settings", "Settings", SettingsPage(self))
        self._register_page("history", "History", HistoryPage(self))
        self._register_page("about", "About", AboutPage(self))

        self.setCentralWidget(central)

        status_bar = QStatusBar(self)
        self.setStatusBar(status_bar)

    def _build_sidebar(self) -> QFrame:
        sidebar = QFrame(self)
        sidebar.setObjectName("Sidebar")
        sidebar.setFixedWidth(190)

        layout = QVBoxLayout(sidebar)
        layout.setContentsMargins(14, 18, 14, 16)
        layout.setSpacing(6)

        # Compact brand header inside sidebar
        brand_title = QLabel("Power BI Validator")
        brand_title.setObjectName("SidebarBrandTitle")
        layout.addWidget(brand_title)

        brand_subtitle = QLabel(f"v{APP_VERSION}  •  Local Desktop")
        brand_subtitle.setObjectName("SidebarBrandSubtitle")
        layout.addWidget(brand_subtitle)

        layout.addSpacing(8)
        top_divider = QFrame()
        top_divider.setObjectName("SidebarDivider")
        layout.addWidget(top_divider)
        layout.addSpacing(8)

        # Navigation buttons container
        self._nav_layout = QVBoxLayout()
        self._nav_layout.setSpacing(6)
        layout.addLayout(self._nav_layout)

        layout.addStretch(1)

        bottom_divider = QFrame()
        bottom_divider.setObjectName("SidebarDivider")
        layout.addWidget(bottom_divider)
        layout.addSpacing(8)

        footer_note = QLabel("Not signed in (Stage 0)")
        footer_note.setObjectName("SidebarFooterNote")
        footer_note.setAlignment(Qt.AlignmentFlag.AlignLeft)
        layout.addWidget(footer_note)
        layout.addSpacing(4)

        self._exit_button = QPushButton("  Exit")
        self._exit_button.setObjectName("ExitButton")
        self._exit_button.setIcon(make_nav_icon("exit", color="#CBD5E1"))
        self._exit_button.setIconSize(QSize(16, 16))
        self._exit_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self._exit_button.clicked.connect(self.close)
        layout.addWidget(self._exit_button)

        return sidebar

    def _register_page(self, key: str, label: str, widget: QWidget) -> None:
        self._pages[key] = widget
        self._stack.addWidget(widget)

        button = QPushButton(f"  {label}")
        button.setObjectName("NavButton")
        button.setCheckable(True)
        button.setIcon(make_nav_icon(key, color="#E2E8F0"))
        button.setIconSize(QSize(18, 18))
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        button.clicked.connect(lambda _checked=False, target=key: self.navigate_to(target))

        self._nav_group.addButton(button)
        self._nav_layout.addWidget(button)
        self._nav_buttons[key] = button

    @property
    def current_page_key(self) -> str:
        """Return the key of the currently displayed page."""
        return self._current_page_key

    def navigate_to(self, page_key: str) -> None:
        """Switch the main stack and sidebar highlight to the requested page."""
        if page_key not in self._pages:
            raise ValueError(f"Unknown page key: {page_key!r}")

        self._stack.setCurrentWidget(self._pages[page_key])
        self._nav_buttons[page_key].setChecked(True)
        self._current_page_key = page_key

        page_label = self._nav_buttons[page_key].text().strip()
        self.statusBar().showMessage(f"Ready  |  View: {page_label}")
        logger.debug("Navigated to page: %s", page_key)

    def closeEvent(self, event: QCloseEvent) -> None:
        """Handle clean window shutdown."""
        logger.info("Closing %s gracefully.", APP_NAME)
        event.accept()
