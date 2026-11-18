"""Main desktop window shell with sidebar navigation, account panel, and notification bar."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QCloseEvent, QIcon
from PySide6.QtWidgets import (
    QButtonGroup,
    QDialog,
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
from app.auth.msal_auth import AuthStateSnapshot, AuthStatus
from app.core.config import AppConfig
from app.core.status import NotificationLevel
from app.ui.dialogs.confirm_dialog import ConfirmDialog
from app.ui.dialogs.entra_config_dialog import EntraConfigDialog
from app.ui.pages.about_page import AboutPage
from app.ui.pages.history_page import HistoryPage
from app.ui.pages.home_page import HomePage
from app.ui.pages.settings_page import SettingsPage
from app.ui.theme import make_nav_icon
from app.ui.widgets.notification_banner import NotificationBanner

if TYPE_CHECKING:
    from app.services.auth_service import AuthService
    from app.services.powerbi_service import PowerBIService

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
APP_ICON_PATH = PROJECT_ROOT / "assets" / "app_icon.svg"


class MainWindow(QMainWindow):
    """Primary desktop window with dark navy sidebar, notification bar, and page stack."""

    def __init__(
        self,
        *,
        config: AppConfig | None = None,
        logs_dir: Path | None = None,
        db_path: Path | None = None,
        token_cache_path: Path | None = None,
        auth_service: AuthService | None = None,
        powerbi_service: PowerBIService | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._config = config or AppConfig()
        self._logs_dir = logs_dir
        self._db_path = db_path
        self._token_cache_path = token_cache_path
        self._auth_service = auth_service
        self._powerbi_service = powerbi_service

        self.setWindowTitle(f"{APP_NAME} v{APP_VERSION}")
        self.resize(self._config.window_width, self._config.window_height)
        self.setMinimumSize(900, 600)

        self._load_window_icon()

        self._pages: dict[str, QWidget] = {}
        self._nav_buttons: dict[str, QPushButton] = {}
        self._nav_group = QButtonGroup(self)
        self._nav_group.setExclusive(True)
        self._current_page_key: str = ""

        self._build_ui()
        self._connect_auth_service()
        self._connect_powerbi_service()
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

        workspace_col = QVBoxLayout()
        workspace_col.setContentsMargins(0, 0, 0, 0)
        workspace_col.setSpacing(0)

        banner_wrapper = QWidget(central)
        banner_layout = QVBoxLayout(banner_wrapper)
        banner_layout.setContentsMargins(20, 12, 20, 0)
        self.notification_banner = NotificationBanner(banner_wrapper)
        banner_layout.addWidget(self.notification_banner)
        banner_wrapper.setVisible(False)
        self._banner_wrapper = banner_wrapper

        self.notification_banner.message_requested.connect(self._show_banner_wrapper)
        self.notification_banner.dismissed.connect(self._hide_banner_wrapper)
        workspace_col.addWidget(banner_wrapper)

        self._stack = QStackedWidget(central)
        workspace_col.addWidget(self._stack, stretch=1)

        root_layout.addLayout(workspace_col, stretch=1)

        self.home_page = HomePage(self)
        self.settings_page = SettingsPage(self)
        self.history_page = HistoryPage(self)
        self.about_page = AboutPage(
            config=self._config,
            logs_dir=self._logs_dir,
            db_path=self._db_path,
            token_cache_path=self._token_cache_path,
            parent=self,
        )

        self._register_page("home", "Home", self.home_page)
        self._register_page("settings", "Settings", self.settings_page)
        self._register_page("history", "History", self.history_page)
        self._register_page("about", "About", self.about_page)

        self.setCentralWidget(central)

        status_bar = QStatusBar(self)
        self.setStatusBar(status_bar)

    def _show_banner_wrapper(self, *_args: object) -> None:
        self._banner_wrapper.setVisible(True)

    def _hide_banner_wrapper(self) -> None:
        self._banner_wrapper.setVisible(False)

    def _build_sidebar(self) -> QFrame:
        sidebar = QFrame(self)
        sidebar.setObjectName("Sidebar")
        sidebar.setFixedWidth(205)

        layout = QVBoxLayout(sidebar)
        layout.setContentsMargins(14, 18, 14, 16)
        layout.setSpacing(6)

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

        self._nav_layout = QVBoxLayout()
        self._nav_layout.setSpacing(6)
        layout.addLayout(self._nav_layout)

        layout.addStretch(1)

        bottom_divider = QFrame()
        bottom_divider.setObjectName("SidebarDivider")
        layout.addWidget(bottom_divider)
        layout.addSpacing(10)

        # Signed-in account profile summary (matching mockup bottom-left area)
        account_row = QHBoxLayout()
        account_row.setSpacing(10)

        self._avatar_label = QLabel("--")
        self._avatar_label.setFixedSize(34, 34)
        self._avatar_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._avatar_label.setStyleSheet(
            "background-color: #243E66; color: #FFFFFF; border-radius: 17px; "
            "font-weight: 700; font-size: 12px;"
        )
        account_row.addWidget(self._avatar_label)

        account_text_col = QVBoxLayout()
        account_text_col.setSpacing(1)
        self._sidebar_user_name = QLabel("Not signed in")
        self._sidebar_user_name.setStyleSheet("color: #FFFFFF; font-size: 12px; font-weight: 600;")
        account_text_col.addWidget(self._sidebar_user_name)

        self._sidebar_user_email = QLabel("Microsoft Entra ID")
        self._sidebar_user_email.setStyleSheet("color: #94A3B8; font-size: 10px;")
        account_text_col.addWidget(self._sidebar_user_email)

        account_row.addLayout(account_text_col, stretch=1)
        layout.addLayout(account_row)
        layout.addSpacing(8)

        self._sign_out_button = QPushButton("  Sign Out")
        self._sign_out_button.setObjectName("ExitButton")
        self._sign_out_button.setIcon(make_nav_icon("exit", color="#CBD5E1"))
        self._sign_out_button.setIconSize(QSize(16, 16))
        self._sign_out_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self._sign_out_button.clicked.connect(self._handle_sign_out_requested)
        self._sign_out_button.setVisible(False)
        layout.addWidget(self._sign_out_button)

        self._exit_button = QPushButton("  Exit")
        self._exit_button.setObjectName("ExitButton")
        self._exit_button.setIcon(make_nav_icon("exit", color="#CBD5E1"))
        self._exit_button.setIconSize(QSize(16, 16))
        self._exit_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self._exit_button.clicked.connect(self.close)
        layout.addWidget(self._exit_button)

        return sidebar

    def _connect_auth_service(self) -> None:
        banner = self.home_page.auth_banner
        banner.configure_requested.connect(self._open_entra_config_dialog)
        banner.sign_in_requested.connect(self._handle_sign_in_requested)
        banner.switch_account_requested.connect(self._handle_switch_account_requested)
        banner.sign_out_requested.connect(self._handle_sign_out_requested)

        if self._auth_service is not None:
            self._auth_service.state_changed.connect(self.apply_auth_state)
            self._auth_service.error_occurred.connect(
                lambda msg: self.show_notification(
                    msg,
                    level=NotificationLevel.ERROR,
                    title="Authentication",
                )
            )
            self.apply_auth_state(self._auth_service.state)
        else:
            self.apply_auth_state(
                AuthStateSnapshot(
                    status=AuthStatus.NOT_CONFIGURED,
                    status_message="Configure a Microsoft Entra Client ID to enable sign-in.",
                )
            )

    def _connect_powerbi_service(self) -> None:
        if self._powerbi_service is None:
            return

        self.home_page.load_workspaces_requested.connect(
            self._powerbi_service.list_workspaces_async
        )
        self.home_page.load_workspace_assets_requested.connect(
            self._powerbi_service.list_workspace_assets_async
        )
        self.home_page.verify_access_requested.connect(self._handle_verify_access_requested)

        self._powerbi_service.busy_changed.connect(self.home_page.set_connectivity_busy)
        self._powerbi_service.workspaces_loaded.connect(self.home_page.set_workspaces)
        self._powerbi_service.workspace_assets_loaded.connect(self.home_page.set_workspace_assets)
        self._powerbi_service.access_verified.connect(self._handle_access_verified)
        self._powerbi_service.error_occurred.connect(
            lambda msg: self.show_notification(
                msg,
                level=NotificationLevel.ERROR,
                title="Power BI Connectivity",
            )
        )

    def _handle_verify_access_requested(
        self,
        workspace_id: str,
        dataset_id: str,
        report_id: str,
    ) -> None:
        if self._powerbi_service is None:
            return
        self._powerbi_service.verify_access_async(
            workspace_id=workspace_id,
            dataset_id=dataset_id,
            report_id=report_id or None,
        )

    def _handle_access_verified(self, result: object) -> None:
        self.home_page.display_verification_result(result)  # type: ignore[arg-type]
        if self._auth_service is not None:
            self.home_page.auth_banner.apply_state(self._auth_service.state)

    def apply_auth_state(self, state: AuthStateSnapshot) -> None:
        """Synchronize the sidebar profile panel and Home auth banner with auth state."""
        self.home_page.auth_banner.apply_state(state)

        if state.status == AuthStatus.AUTHENTICATED and state.account is not None:
            acct = state.account
            self._avatar_label.setText(acct.initials)
            self._avatar_label.setStyleSheet(
                "background-color: #1668DC; color: #FFFFFF; border-radius: 17px; "
                "font-weight: 700; font-size: 12px;"
            )
            self._sidebar_user_name.setText(acct.display_name)
            self._sidebar_user_email.setText(acct.username or "Signed in")
            self._sign_out_button.setVisible(True)
        else:
            self._avatar_label.setText("--")
            self._avatar_label.setStyleSheet(
                "background-color: #243E66; color: #FFFFFF; border-radius: 17px; "
                "font-weight: 700; font-size: 12px;"
            )
            self._sidebar_user_name.setText(
                "Session expired" if state.status == AuthStatus.EXPIRED else "Not signed in"
            )
            self._sidebar_user_email.setText(
                state.account.username if state.account else "Microsoft Entra ID"
            )
            self._sign_out_button.setVisible(False)

    def _open_entra_config_dialog(self) -> None:
        dialog = EntraConfigDialog(
            client_id=self._config.effective_client_id(),
            tenant_id=self._config.effective_tenant_id(),
            parent=self,
        )
        if dialog.exec() == QDialog.DialogCode.Accepted and self._auth_service is not None:
            self._auth_service.configure_entra_app(dialog.client_id, dialog.tenant_id)
            self.show_notification(
                "Microsoft Entra public-client settings saved.",
                level=NotificationLevel.SUCCESS,
                title="Authentication",
            )

    def _handle_sign_in_requested(self) -> None:
        if self._auth_service is not None:
            self._auth_service.sign_in_async()

    def _handle_switch_account_requested(self) -> None:
        if self._auth_service is not None:
            self._auth_service.switch_account_async()

    def _handle_sign_out_requested(self) -> None:
        if self._auth_service is None:
            return
        confirmed = ConfirmDialog.ask(
            self,
            title="Sign Out of Microsoft",
            message="Sign out and clear the locally cached authentication session?",
            detail="Your saved workspace registrations, validation rules, and history will be kept.",
            confirm_text="Sign Out",
            cancel_text="Cancel",
        )
        if confirmed:
            self._auth_service.sign_out()
            self.show_notification(
                "Signed out and cleared the protected local token cache.",
                level=NotificationLevel.INFO,
                title="Signed Out",
            )

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

    def show_notification(
        self,
        message: str,
        level: NotificationLevel = NotificationLevel.INFO,
        title: str | None = None,
    ) -> None:
        """Show a message in the top-level notification banner."""
        self._banner_wrapper.setVisible(True)
        self.notification_banner.show_message(message, level=level, title=title)

    def post_notification(
        self,
        message: str,
        level: NotificationLevel = NotificationLevel.INFO,
        title: str | None = None,
    ) -> None:
        """Thread-safe method to display a notification banner from any thread."""
        self.notification_banner.post_message(message, level=level, title=title)

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
