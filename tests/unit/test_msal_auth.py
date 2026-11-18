"""Unit tests for MsalAuthClient using an in-memory fake PublicClientApplication."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import pytest

from app.auth.msal_auth import (
    PERSONAL_ACCOUNT_TENANT_ID,
    AuthConfig,
    AuthStatus,
    MsalAuthClient,
    MsalAuthenticationError,
    is_valid_guid,
    is_valid_tenant,
)
from app.core.config import AppConfig
from app.core.logging_config import setup_logging

VALID_CLIENT_ID = "12345678-1234-1234-1234-1234567890ab"
ORG_TENANT_ID = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"


class _FakePca:
    """Deterministic fake MSAL PublicClientApplication for unit testing."""

    def __init__(
        self,
        *,
        accounts: list[dict[str, Any]] | None = None,
        silent_result: dict[str, Any] | None = None,
        interactive_result: dict[str, Any] | None = None,
        token_cache: Any = None,
    ) -> None:
        self.accounts = list(accounts or [])
        self.silent_result = silent_result
        self.interactive_result = interactive_result
        self.token_cache = token_cache
        self.last_interactive_kwargs: dict[str, Any] = {}
        self.removed_accounts: list[dict[str, Any]] = []

    def get_accounts(self) -> list[dict[str, Any]]:
        return list(self.accounts)

    def acquire_token_silent(self, scopes: list[str], account: dict[str, Any]) -> dict[str, Any] | None:
        return self.silent_result

    def acquire_token_interactive(self, **kwargs: Any) -> dict[str, Any]:
        self.last_interactive_kwargs = dict(kwargs)
        result = self.interactive_result or {}
        if "access_token" in result:
            claims = result.get("id_token_claims") or {}
            acct = {
                "home_account_id": f"{claims.get('oid', 'oid1')}.{claims.get('tid', ORG_TENANT_ID)}",
                "username": claims.get("preferred_username", "john.doe@contoso.com"),
                "name": claims.get("name", "John Doe"),
                "realm": claims.get("tid", ORG_TENANT_ID),
            }
            self.accounts = [acct]
            if self.token_cache is not None:
                self.token_cache.has_state_changed = True
        return result

    def remove_account(self, account: dict[str, Any]) -> None:
        self.removed_accounts.append(account)
        self.accounts = [a for a in self.accounts if a != account]


def test_guid_and_tenant_validation_helpers() -> None:
    assert is_valid_guid(VALID_CLIENT_ID)
    assert not is_valid_guid("not-a-guid")
    assert is_valid_tenant("organizations")
    assert is_valid_tenant(ORG_TENANT_ID)
    assert is_valid_tenant("contoso.onmicrosoft.com")
    assert not is_valid_tenant("")


def test_unconfigured_client_rejects_sign_in(tmp_path: Path) -> None:
    client = MsalAuthClient(
        config=AuthConfig(client_id=""),
        cache_path=tmp_path / "cache.bin",
    )
    assert client.state.status == AuthStatus.NOT_CONFIGURED

    with pytest.raises(MsalAuthenticationError):
        client.sign_in_interactive()


def test_interactive_sign_in_and_no_token_in_logs(tmp_path: Path) -> None:
    log_path = setup_logging(AppConfig(log_level="DEBUG"), tmp_path / "logs", include_console=False)
    secret_token = "eyJhbGciOiJSUzI1NiJ9.eyJ1cG4iOiJqb2huIn0.verySecretPowerBiAccessToken"

    fake_pca = _FakePca(
        interactive_result={
            "access_token": secret_token,
            "id_token_claims": {
                "name": "John Doe",
                "preferred_username": "john.doe@contoso.com",
                "oid": "user-oid-1",
                "tid": ORG_TENANT_ID,
            },
        },
        silent_result={"access_token": secret_token},
    )

    client = MsalAuthClient(
        config=AuthConfig(client_id=VALID_CLIENT_ID, tenant_id=ORG_TENANT_ID),
        cache_path=tmp_path / "auth" / "cache.bin",
        pca_factory=lambda _cid, _auth, cache: setattr(fake_pca, "token_cache", cache) or fake_pca,
    )

    state = client.sign_in_interactive()
    assert state.status == AuthStatus.AUTHENTICATED
    assert state.account is not None
    assert state.account.display_name == "John Doe"
    assert state.account.username == "john.doe@contoso.com"
    assert state.account.initials == "JD"
    assert state.account.is_personal_account is False

    token = client.get_access_token()
    assert token == secret_token

    for handler in logging.getLogger().handlers:
        handler.flush()
    log_text = log_path.read_text(encoding="utf-8")
    assert secret_token not in log_text


def test_restore_session_handles_valid_and_expired_sessions(tmp_path: Path) -> None:
    cached_acct = {
        "home_account_id": f"oid-1.{ORG_TENANT_ID}",
        "username": "jane.smith@contoso.com",
        "name": "Jane Smith",
        "realm": ORG_TENANT_ID,
    }

    # 1. Valid cached session restores silently
    valid_pca = _FakePca(
        accounts=[cached_acct],
        silent_result={
            "access_token": "valid_silent_token",
            "id_token_claims": {
                "name": "Jane Smith",
                "preferred_username": "jane.smith@contoso.com",
                "tid": ORG_TENANT_ID,
            },
        },
    )
    client = MsalAuthClient(
        config=AuthConfig(client_id=VALID_CLIENT_ID),
        cache_path=tmp_path / "cache1.bin",
        pca_factory=lambda *_: valid_pca,
    )
    restored = client.restore_session()
    assert restored.status == AuthStatus.AUTHENTICATED
    assert restored.account is not None
    assert restored.account.username == "jane.smith@contoso.com"

    # 2. Expired/revoked session transitions cleanly to EXPIRED
    expired_pca = _FakePca(
        accounts=[cached_acct],
        silent_result={"error": "invalid_grant", "error_description": "AADSTS700082: refresh token expired"},
    )
    expired_client = MsalAuthClient(
        config=AuthConfig(client_id=VALID_CLIENT_ID),
        cache_path=tmp_path / "cache2.bin",
        pca_factory=lambda *_: expired_pca,
    )
    expired_state = expired_client.restore_session()
    assert expired_state.status == AuthStatus.EXPIRED

    with pytest.raises(MsalAuthenticationError) as exc_info:
        expired_client.get_access_token()
    assert exc_info.value.interaction_required is True


def test_switch_account_and_sign_out_clears_cache(tmp_path: Path) -> None:
    cache_file = tmp_path / "auth" / "cache.bin"
    fake_pca = _FakePca(
        interactive_result={
            "access_token": "new_account_token",
            "id_token_claims": {
                "name": "Personal User",
                "preferred_username": "personal@outlook.com",
                "tid": PERSONAL_ACCOUNT_TENANT_ID,
            },
        }
    )

    client = MsalAuthClient(
        config=AuthConfig(client_id=VALID_CLIENT_ID, tenant_id="common"),
        cache_path=cache_file,
        pca_factory=lambda _cid, _auth, cache: setattr(fake_pca, "token_cache", cache) or fake_pca,
    )

    switched = client.switch_account()
    assert fake_pca.last_interactive_kwargs.get("prompt") == "select_account"
    assert switched.status == AuthStatus.AUTHENTICATED
    assert switched.account is not None
    assert switched.account.is_personal_account is True
    assert cache_file.exists()

    signed_out = client.sign_out()
    assert signed_out.status == AuthStatus.SIGNED_OUT
    assert signed_out.account is None
    assert not cache_file.exists()
    assert len(fake_pca.removed_accounts) == 1
