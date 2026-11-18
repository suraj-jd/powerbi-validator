"""Unit tests for AzureCliAuthClient using mocked az CLI subprocess responses."""

from __future__ import annotations

import json
import logging
import subprocess
from pathlib import Path

import jwt
import pytest

from app.auth.azure_cli_auth import POWERBI_RESOURCE_URL, AzureCliAuthClient
from app.auth.msal_auth import AuthStatus, MsalAuthenticationError
from app.core.config import AppConfig
from app.core.logging_config import setup_logging


def _make_fake_jwt(claims: dict[str, str]) -> str:
    return jwt.encode(claims, "test-signing-key-with-at-least-32-bytes", algorithm="HS256")


def test_azure_cli_interactive_sign_in_and_no_token_in_logs(tmp_path: Path) -> None:
    log_path = setup_logging(AppConfig(log_level="DEBUG"), tmp_path / "logs", include_console=False)
    fake_token = _make_fake_jwt(
        {
            "name": "Suraj Kumar",
            "upn": "suraj@contoso.com",
            "tid": "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
            "oid": "11111111-2222-3333-4444-555555555555",
        }
    )
    executed_cmds: list[list[str]] = []

    def fake_runner(args: list[str], _timeout: float) -> subprocess.CompletedProcess[str]:
        executed_cmds.append(args)
        if "login" in args:
            return subprocess.CompletedProcess(
                args,
                0,
                stdout=json.dumps([{"tenantId": "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee", "user": {"name": "suraj@contoso.com"}}]),
                stderr="",
            )
        if "get-access-token" in args:
            return subprocess.CompletedProcess(
                args,
                0,
                stdout=json.dumps({"accessToken": fake_token, "tenant": "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"}),
                stderr="",
            )
        if "logout" in args:
            return subprocess.CompletedProcess(args, 0, stdout="", stderr="")
        return subprocess.CompletedProcess(args, 1, stdout="", stderr="unexpected")

    client = AzureCliAuthClient(
        az_finder=lambda: "az.cmd",
        command_runner=fake_runner,
    )

    state = client.sign_in_interactive()
    assert state.status == AuthStatus.AUTHENTICATED
    assert state.account is not None
    assert state.account.display_name == "Suraj Kumar"
    assert state.account.username == "suraj@contoso.com"
    assert "--allow-no-subscriptions" in executed_cmds[0]
    assert POWERBI_RESOURCE_URL in executed_cmds[1]

    token = client.get_access_token()
    assert token == fake_token

    for handler in logging.getLogger().handlers:
        handler.flush()
    assert fake_token not in log_path.read_text(encoding="utf-8")

    signed_out = client.sign_out()
    assert signed_out.status == AuthStatus.SIGNED_OUT
    assert signed_out.account is None
    assert any("logout" in cmd for cmd in executed_cmds)


def test_azure_cli_restore_session_handles_logged_in_and_logged_out() -> None:
    fake_token = _make_fake_jwt(
        {
            "name": "Jane Doe",
            "preferred_username": "jane@contoso.com",
            "tid": "tid-1",
            "oid": "oid-1",
        }
    )

    def logged_in_runner(args: list[str], _timeout: float) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(
            args,
            0,
            stdout=json.dumps({"accessToken": fake_token, "tenant": "tid-1"}),
            stderr="",
        )

    client_ok = AzureCliAuthClient(az_finder=lambda: "az.cmd", command_runner=logged_in_runner)
    restored = client_ok.restore_session()
    assert restored.status == AuthStatus.AUTHENTICATED
    assert restored.account is not None and restored.account.username == "jane@contoso.com"

    def logged_out_runner(args: list[str], _timeout: float) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(args, 1, stdout="", stderr="Please run 'az login'")

    client_out = AzureCliAuthClient(az_finder=lambda: "az.cmd", command_runner=logged_out_runner)
    restored_out = client_out.restore_session()
    assert restored_out.status == AuthStatus.SIGNED_OUT


def test_azure_cli_missing_executable_raises_clear_error() -> None:
    client = AzureCliAuthClient(az_finder=lambda: None)
    assert client.is_available is False
    with pytest.raises(MsalAuthenticationError, match="Azure CLI"):
        client.sign_in_interactive()
