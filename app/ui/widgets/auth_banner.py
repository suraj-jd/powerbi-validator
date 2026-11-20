"""Top-of-dashboard Microsoft authentication banner matching the enterprise UI design."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from app.auth.msal_auth import AuthStateSnapshot, AuthStatus

_BANNER_PALETTES: dict[AuthStatus, dict[str, str]] = {
    AuthStatus.AUTHENTICATED: {
        "bg": "#EAFBF0",
        "border": "#A7E6BE",
        "accent": "#15803D",
        "icon": "✓",
        "headline": "Authenticated Successfully",
    },
    AuthStatus.SIGNING_IN: {
        "bg": "#EFF6FF",
        "border": "#BFDBFE",
        "accent": "#1D4ED8",
        "icon": "…",
        "headline": "Signing In with Microsoft",
    },
    AuthStatus.EXPIRED: {
        "bg": "#FFFBEB",
        "border": "#FDE68A",
        "accent": "#B45309",
        "icon": "!",
        "headline": "Session Expired: Please Sign In Again",
    },
    AuthStatus.ERROR: {
        "bg": "#FEF2F2",
        "border": "#FECACA",
        "accent": "#B91C1C",
        "icon": "!",
        "headline": "Authentication Error",
    },
    AuthStatus.NOT_CONFIGURED: {
        "bg": "#F8FAFC",
        "border": "#CBD5E1",
        "accent": "#334155",
        "icon": "i",
        "headline": "Microsoft Entra App Not Configured",
    },
    AuthStatus.SIGNED_OUT: {
        "bg": "#FFFFFF",
        "border": "#CBD5E1",
        "accent": "#1E3A8A",
        "icon": "i",
        "headline": "Not Signed In",
    },
}


class AuthBanner(QFrame):
    """Displays Microsoft authentication status, signed-in account, and auth actions.

    Never displays access tokens, refresh tokens, passwords, or false ownership claims.
    """

    sign_in_requested = Signal()
    switch_account_requested = Signal()
    sign_out_requested = Signal()
    configure_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("AuthBanner")
        self._workspace_access_label = "Not yet verified (Stage 4)"
        self._build_ui()
        self.apply_state(
            AuthStateSnapshot(
                status=AuthStatus.NOT_CONFIGURED,
                status_message="Configure a Microsoft Entra Client ID to enable sign-in.",
            )
        )

    def _build_ui(self) -> None:
        layout = QHBoxLayout(self)
        layout.setContentsMargins(18, 14, 18, 14)
        layout.setSpacing(14)

        self._status_circle = QLabel("i")
        self._status_circle.setFixedSize(34, 34)
        self._status_circle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._status_circle.setToolTip("Microsoft account connection status.")
        layout.addWidget(self._status_circle, alignment=Qt.AlignmentFlag.AlignVCenter)

        text_col = QVBoxLayout()
        text_col.setSpacing(2)

        self.headline_label = QLabel()
        self.headline_label.setWordWrap(True)
        self.headline_label.setToolTip("Microsoft sign-in status.")
        text_col.addWidget(self.headline_label)

        self.details_label = QLabel()
        self.details_label.setWordWrap(True)
        self.details_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.details_label.setToolTip("Signed-in account name and Power BI workspace access.")
        text_col.addWidget(self.details_label)

        layout.addLayout(text_col, stretch=1)

        actions_row = QHBoxLayout()
        actions_row.setSpacing(8)

        self.configure_button = QPushButton("Configure Entra App")
        self.configure_button.setObjectName("SecondaryButton")
        self.configure_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.configure_button.setToolTip("Open settings to enter your Microsoft login details.")
        self.configure_button.clicked.connect(self.configure_requested.emit)
        actions_row.addWidget(self.configure_button)

        self.sign_in_button = QPushButton("Sign In with Microsoft")
        self.sign_in_button.setObjectName("PrimaryButton")
        self.sign_in_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.sign_in_button.setToolTip("Sign in with your work or school account.")
        self.sign_in_button.clicked.connect(self.sign_in_requested.emit)
        actions_row.addWidget(self.sign_in_button)

        self.switch_account_button = QPushButton("Switch Account")
        self.switch_account_button.setObjectName("SecondaryButton")
        self.switch_account_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.switch_account_button.setToolTip("Sign in using a different work or school account.")
        self.switch_account_button.clicked.connect(self.switch_account_requested.emit)
        actions_row.addWidget(self.switch_account_button)

        self.sign_out_button = QPushButton("Sign Out")
        self.sign_out_button.setObjectName("SecondaryButton")
        self.sign_out_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.sign_out_button.setToolTip("Sign out of your active account.")
        self.sign_out_button.clicked.connect(self.sign_out_requested.emit)
        actions_row.addWidget(self.sign_out_button)

        layout.addLayout(actions_row)

    def set_workspace_access_label(self, label: str) -> None:
        """Update the displayed effective workspace permission text (populated in Stage 4+)."""
        self._workspace_access_label = label

    def apply_state(self, state: AuthStateSnapshot) -> None:
        """Update banner visuals, account text, and action buttons for the given state."""
        palette = _BANNER_PALETTES[state.status]
        accent = palette["accent"]

        self.setStyleSheet(
            f"""
            QFrame#AuthBanner {{
                background-color: {palette['bg']};
                border: 1px solid {palette['border']};
                border-radius: 12px;
            }}
            """
        )
        self._status_circle.setText(palette["icon"])
        self._status_circle.setStyleSheet(
            f"""
            QLabel {{
                background-color: {accent};
                color: #FFFFFF;
                border-radius: 17px;
                font-size: 16px;
                font-weight: 700;
            }}
            """
        )

        self.headline_label.setText(palette["headline"])
        self.headline_label.setStyleSheet(
            f"color: {accent}; font-size: 14px; font-weight: 700;"
        )

        if state.status == AuthStatus.AUTHENTICATED and state.account is not None:
            acct = state.account
            identity = (
                f"{acct.display_name} ({acct.username})"
                if acct.display_name and acct.username and acct.display_name != acct.username
                else (acct.username or acct.display_name)
            )
            access_note = (
                "Personal Microsoft account (Power BI workspace access not guaranteed)"
                if acct.is_personal_account
                else f"Workspace Access: {self._workspace_access_label}"
            )
            self.details_label.setText(f"Signed in as: {identity}  |  {access_note}")
        else:
            self.details_label.setText(state.status_message)

        self.details_label.setStyleSheet("color: #334155; font-size: 12px;")

        is_busy = state.status == AuthStatus.SIGNING_IN
        is_authenticated = state.status == AuthStatus.AUTHENTICATED
        is_configured = state.client_id_configured

        self.configure_button.setVisible(not is_authenticated)
        self.configure_button.setEnabled(not is_busy)

        self.sign_in_button.setVisible(not is_authenticated)
        self.sign_in_button.setEnabled(not is_busy)
        self.sign_in_button.setToolTip(
            "Sign in with your work or school account to load your Power BI models."
            if is_configured
            else "Click to enter your Microsoft login settings first."
        )
        self.sign_in_button.setText(
            "Signing In..."
            if is_busy
            else ("Sign In Again" if state.status == AuthStatus.EXPIRED else "Sign In with Microsoft")
        )

        self.switch_account_button.setVisible(is_authenticated)
        self.switch_account_button.setEnabled(not is_busy)

        self.sign_out_button.setVisible(is_authenticated)
        self.sign_out_button.setEnabled(not is_busy)
