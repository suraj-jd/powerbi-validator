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

    # Not configured: Configure button visible, Sign In stays clickable to guide setup
    banner.apply_state(
        AuthStateSnapshot(
            status=AuthStatus.NOT_CONFIGURED,
            status_message="Configure Entra Client ID.",
            client_id_configured=False,
        )
    )
    assert banner.configure_button.isVisible()
    assert banner.sign_in_button.isEnabled()
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


def test_sign_in_click_when_unconfigured_prompts_entra_config_then_signs_in(
    qtbot,
    tmp_path: Path,
    monkeypatch,
) -> None:
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
    sign_in_called = {"count": 0}
    monkeypatch.setattr(auth_service, "sign_in_async", lambda: sign_in_called.__setitem__("count", 1))

    window = MainWindow(config=app_config, auth_service=auth_service)
    qtbot.addWidget(window)
    window.show()

    prompted_button_text: list[str] = []

    def fake_open_dialog(*, save_button_text: str = "Save Settings") -> bool:
        prompted_button_text.append(save_button_text)
        auth_service.configure_entra_app(VALID_CLIENT_ID, "organizations")
        return True

    monkeypatch.setattr(window, "_open_entra_config_dialog", fake_open_dialog)

    qtbot.mouseClick(window.home_page.auth_banner.sign_in_button, Qt.MouseButton.LeftButton)

    assert prompted_button_text == ["Save & Sign In"]
    assert sign_in_called["count"] == 1


def test_sign_in_click_uses_one_click_azure_cli_when_available(
    qtbot,
    tmp_path: Path,
    monkeypatch,
) -> None:
    from app.auth.azure_cli_auth import AzureCliAuthClient

    app_config = AppConfig()
    msal_client = MsalAuthClient(
        config=AuthConfig(client_id="", tenant_id="organizations"),
        cache_path=tmp_path / "auth" / "cache.bin",
    )
    az_client = AzureCliAuthClient(az_finder=lambda: "az.cmd")
    auth_service = AuthService(
        auth_client=msal_client,
        azure_cli_client=az_client,
        app_config=app_config,
        data_dir=tmp_path,
    )
    sign_in_called = {"count": 0}
    monkeypatch.setattr(auth_service, "sign_in_async", lambda: sign_in_called.__setitem__("count", 1))

    window = MainWindow(config=app_config, auth_service=auth_service)
    qtbot.addWidget(window)
    window.show()

    qtbot.mouseClick(window.home_page.auth_banner.sign_in_button, Qt.MouseButton.LeftButton)
    assert sign_in_called["count"] == 1


def test_interactive_login_completion_brings_window_to_front(
    qtbot,
    tmp_path: Path,
    monkeypatch,
) -> None:
    app_config = AppConfig()
    auth_client = MsalAuthClient(
        config=AuthConfig(client_id=VALID_CLIENT_ID, tenant_id="organizations"),
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

    bring_to_front_called = {"count": 0}
    monkeypatch.setattr(window, "bring_to_front", lambda: bring_to_front_called.__setitem__("count", bring_to_front_called["count"] + 1))

    # Emitting interactive_login_completed signal triggers window bring_to_front
    auth_service.interactive_login_completed.emit(True)
    assert bring_to_front_called["count"] >= 1


def test_silent_restore_does_not_trigger_interactive_completion_signal(
    qtbot,
    tmp_path: Path,
) -> None:
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

    interactive_events: list[bool] = []
    auth_service.interactive_login_completed.connect(interactive_events.append)

    # Silent session restore must not emit interactive completion signal
    auth_service.restore_session_async()
    assert len(interactive_events) == 0


def test_bring_to_front_executes_cleanly_when_normal_or_minimized(
    qtbot,
    tmp_path: Path,
) -> None:
    app_config = AppConfig()
    window = MainWindow(config=app_config)
    qtbot.addWidget(window)
    window.show()

    # Normal window
    window.bring_to_front()

    # Minimized window
    window.showMinimized()
    window.bring_to_front()
    assert not window.isMinimized()
