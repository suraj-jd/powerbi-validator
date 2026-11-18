"""UI tests for Stage 3 AuthBanner, EntraConfigDialog, and MainWindow account panel."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt

from app.auth.msal_auth import AuthAccount, AuthConfig, AuthStateSnapshot, AuthStatus, MsalAuthClient
from app.core.config import AppConfig, load_config
from app.services.auth_service import AuthService
from app.ui.dialogs.entra_config_dialog import EntraConfigDialog
from app.ui.main_window import MainWindow
from app.ui.widgets.auth_banner import AuthBanner

VALID_CLIENT_ID = "12345678-1234-1234-1234-1234567890ab"


def test_auth_banner_states_and_never_claims_false_ownership(qtbot) -> None:
    banner = AuthBanner()
    qtbot.addWidget(banner)
    banner.show()

    # Not configured: Configure button visible, Sign In disabled
    banner.apply_state(
        AuthStateSnapshot(
            status=AuthStatus.NOT_CONFIGURED,
            status_message="Configure Entra Client ID.",
            client_id_configured=False,
        )
    )
    assert banner.configure_button.isVisible()
    assert not banner.sign_in_button.isEnabled()
    assert not banner.switch_account_button.isVisible()

    # Authenticated organizational user: never falsely labelled "Workspace Owner"
    org_account = AuthAccount(
        home_account_id="oid.tid",
        display_name="John Doe",
        username="john.doe@contoso.com",
        tenant_id="aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
        is_personal_account=False,
    )
    banner.apply_state(
        AuthStateSnapshot(
            status=AuthStatus.AUTHENTICATED,
            account=org_account,
            client_id_configured=True,
        )
    )
    assert "john.doe@contoso.com" in banner.details_label.text()
    assert "Owner" not in banner.details_label.text()
    assert banner.switch_account_button.isVisible()
    assert banner.sign_out_button.isVisible()
    assert not banner.sign_in_button.isVisible()

    # Personal Microsoft account displays explicit advisory note
    personal_account = AuthAccount(
        home_account_id="oid.msa",
        display_name="Personal User",
        username="user@outlook.com",
        tenant_id="9188040d-6c67-4c5b-b112-36a304b66dad",
        is_personal_account=True,
    )
    banner.apply_state(
        AuthStateSnapshot(
            status=AuthStatus.AUTHENTICATED,
            account=personal_account,
            client_id_configured=True,
        )
    )
    assert "not guaranteed" in banner.details_label.text().lower()


def test_entra_config_dialog_validates_guid(qtbot) -> None:
    dialog = EntraConfigDialog()
    qtbot.addWidget(dialog)

    dialog.client_id_input.setText("invalid-id")
    qtbot.mouseClick(dialog.save_button, Qt.MouseButton.LeftButton)
    assert dialog.result() != EntraConfigDialog.DialogCode.Accepted
    assert not dialog.error_label.isHidden()

    dialog.client_id_input.setText(VALID_CLIENT_ID)
    dialog.tenant_id_input.setText("organizations")
    qtbot.mouseClick(dialog.save_button, Qt.MouseButton.LeftButton)
    assert dialog.result() == EntraConfigDialog.DialogCode.Accepted
    assert dialog.client_id == VALID_CLIENT_ID


def test_main_window_syncs_sidebar_account_and_persists_entra_config(qtbot, tmp_path: Path) -> None:
    app_config = AppConfig()
    auth_client = MsalAuthClient(
        config=AuthConfig(client_id="", tenant_id="organizations"),
        cache_path=tmp_path / "auth" / "cache.bin",
    )
    auth_service = AuthService(
        auth_client=auth_client,
        app_config=app_config,
        data_dir=tmp_path,
    )

    window = MainWindow(config=app_config, auth_service=auth_service)
    qtbot.addWidget(window)
    window.show()

    assert window._sidebar_user_name.text() == "Not signed in"
    assert not window._sign_out_button.isVisible()

    # Configure Entra app via service and verify non-secret persistence
    auth_service.configure_entra_app(VALID_CLIENT_ID, "contoso.onmicrosoft.com")
    reloaded = load_config(data_dir=tmp_path)
    assert reloaded.auth_client_id == VALID_CLIENT_ID
    assert reloaded.auth_tenant_id == "contoso.onmicrosoft.com"

    # Simulate authenticated snapshot updating sidebar and Home banner
    acct = AuthAccount(
        home_account_id="oid.tid",
        display_name="John Doe",
        username="john.doe@contoso.com",
        tenant_id="aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
    )
    window.apply_auth_state(
        AuthStateSnapshot(
            status=AuthStatus.AUTHENTICATED,
            account=acct,
            client_id_configured=True,
        )
    )
    assert window._avatar_label.text() == "JD"
    assert window._sidebar_user_name.text() == "John Doe"
    assert window._sidebar_user_email.text() == "john.doe@contoso.com"
    assert window._sign_out_button.isVisible()
