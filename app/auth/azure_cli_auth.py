"""Microsoft sign-in via the official Azure CLI (`az login`) for Power BI API tokens.

This provider uses Microsoft's documented Azure CLI workflow:
  - `az login --allow-no-subscriptions --output json`
  - `az account get-access-token --resource https://analysis.windows.net/powerbi/api --output json`
  - `az logout`

Raw access tokens are kept strictly in memory and never logged or written to SQLite.
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

import jwt

from app.auth.msal_auth import (
    PERSONAL_ACCOUNT_TENANT_ID,
    AuthAccount,
    AuthStateSnapshot,
    AuthStatus,
    MsalAuthenticationError,
)
from app.core.logging_config import redact_secrets

logger = logging.getLogger(__name__)

POWERBI_RESOURCE_URL = "https://analysis.windows.net/powerbi/api"

CommandRunner = Callable[[list[str], float], subprocess.CompletedProcess[str]]

_WINDOWS_AZ_CANDIDATES: tuple[Path, ...] = (
    Path(r"C:\Program Files\Microsoft SDKs\Azure\CLI2\wbin\az.cmd"),
    Path(r"C:\Program Files (x86)\Microsoft SDKs\Azure\CLI2\wbin\az.cmd"),
)


def find_az_executable() -> str | None:
    """Locate the official Azure CLI executable on PATH or standard Windows install paths."""
    for candidate_name in ("az.cmd", "az"):
        found = shutil.which(candidate_name)
        if found:
            return found

    if sys.platform == "win32":
        for path in _WINDOWS_AZ_CANDIDATES:
            if path.exists():
                return str(path)
        local_app_data = os.environ.get("LOCALAPPDATA")
        if local_app_data:
            user_az = Path(local_app_data) / "Programs" / "Microsoft SDKs" / "Azure" / "CLI2" / "wbin" / "az.cmd"
            if user_az.exists():
                return str(user_az)
    return None


def _default_run_command(args: list[str], timeout_seconds: float) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    # Use the system web browser directly and disable interactive subscription prompts on Windows
    env.setdefault("AZURE_CORE_ENABLE_BROKER_ON_WINDOWS", "false")
    env.setdefault("AZURE_CORE_LOGIN_EXPERIENCE_V2", "off")
    kwargs: dict[str, Any] = {
        "capture_output": True,
        "text": True,
        "timeout": timeout_seconds,
        "check": False,
        "env": env,
    }
    if sys.platform == "win32":
        kwargs["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    return subprocess.run(args, **kwargs)


def _extract_account_from_token_payload(
    access_token: str,
    token_json: dict[str, Any],
    login_accounts: list[dict[str, Any]] | None = None,
) -> AuthAccount:
    """Safely read non-secret display name, email/UPN, and tenant ID from JWT claims."""
    claims: dict[str, Any] = {}
    try:
        decoded = jwt.decode(access_token, options={"verify_signature": False})
        if isinstance(decoded, dict):
            claims = decoded
    except Exception:
        claims = {}

    fallback_user = ""
    fallback_tenant = str(token_json.get("tenant") or "")
    if login_accounts:
        first = login_accounts[0]
        if isinstance(first, dict):
            user_obj = first.get("user")
            if isinstance(user_obj, dict):
                fallback_user = str(user_obj.get("name") or "")
            fallback_tenant = fallback_tenant or str(first.get("tenantId") or "")

    username = str(
        claims.get("upn")
        or claims.get("preferred_username")
        or claims.get("unique_name")
        or claims.get("email")
        or fallback_user
        or ""
    ).strip()
    display_name = str(claims.get("name") or username or "Microsoft User").strip()
    tenant_id = str(claims.get("tid") or fallback_tenant or "").strip()
    oid = str(claims.get("oid") or claims.get("sub") or username or "az-user").strip()
    is_personal = tenant_id.lower() == PERSONAL_ACCOUNT_TENANT_ID

    return AuthAccount(
        home_account_id=f"{oid}.{tenant_id}" if tenant_id else oid,
        display_name=display_name,
        username=username,
        tenant_id=tenant_id,
        is_personal_account=is_personal,
    )


class AzureCliAuthClient:
    """Microsoft authentication client powered by official Azure CLI (`az login`)."""

    def __init__(
        self,
        *,
        az_finder: Callable[[], str | None] = find_az_executable,
        command_runner: CommandRunner = _default_run_command,
    ) -> None:
        self._az_finder = az_finder
        self._run = command_runner
        self._active_account: AuthAccount | None = None
        self._status = AuthStatus.SIGNED_OUT
        self._status_message = "Click 'Sign In with Microsoft' to log in via your browser."

    @property
    def is_available(self) -> bool:
        return self._az_finder() is not None

    @property
    def state(self) -> AuthStateSnapshot:
        return AuthStateSnapshot(
            status=self._status,
            account=self._active_account,
            status_message=self._status_message,
            client_id_configured=True,
            tenant_id=self._active_account.tenant_id if self._active_account else "organizations",
        )

    def _require_az(self) -> str:
        az_path = self._az_finder()
        if not az_path:
            self._status = AuthStatus.ERROR
            self._status_message = (
                "Azure CLI is not installed. Install Microsoft Azure CLI or click "
                "'Configure Entra App' to use a custom Client ID."
            )
            raise MsalAuthenticationError(
                "Azure CLI executable not found.",
                user_message=self._status_message,
            )
        return az_path

    def _fetch_powerbi_token_json(self, az_path: str) -> dict[str, Any]:
        cmd = [
            az_path,
            "account",
            "get-access-token",
            "--resource",
            POWERBI_RESOURCE_URL,
            "--output",
            "json",
        ]
        try:
            proc = self._run(cmd, 30.0)
        except subprocess.TimeoutExpired as exc:
            raise MsalAuthenticationError(
                "Azure CLI token request timed out.",
                user_message="Timed out retrieving Power BI access token from Azure CLI.",
            ) from exc

        if proc.returncode != 0:
            stderr = redact_secrets((proc.stderr or "").strip())
            stdout = redact_secrets((proc.stdout or "").strip())
            error_detail = stderr or stdout or f"exit code {proc.returncode}"
            logger.warning("Azure CLI get-access-token failed (code=%d): %s", proc.returncode, error_detail)
            raise MsalAuthenticationError(
                f"Azure CLI get-access-token failed (code={proc.returncode}): {error_detail[:300]}",
                user_message=f"Power BI token request failed: {error_detail[:200]}",
                interaction_required=True,
            )

        try:
            payload = json.loads(proc.stdout)
        except json.JSONDecodeError as exc:
            raise MsalAuthenticationError(
                "Azure CLI returned invalid JSON for access token.",
                user_message="Unexpected response from Azure CLI when requesting Power BI token.",
            ) from exc

        if not isinstance(payload, dict) or not payload.get("accessToken"):
            raise MsalAuthenticationError(
                "Azure CLI did not return an accessToken field.",
                user_message="Could not obtain a Power BI access token. Please sign in again.",
                interaction_required=True,
            )
        return payload

    def restore_session(self) -> AuthStateSnapshot:
        """Restore an existing Azure CLI Power BI session silently on app startup."""
        az_path = self._az_finder()
        if not az_path:
            self._active_account = None
            self._status = AuthStatus.SIGNED_OUT
            self._status_message = (
                "Sign in with Microsoft (via Azure CLI) or configure an Entra Client ID."
            )
            return self.state

        try:
            token_json = self._fetch_powerbi_token_json(az_path)
        except MsalAuthenticationError:
            self._active_account = None
            self._status = AuthStatus.SIGNED_OUT
            self._status_message = "Click 'Sign In with Microsoft' to log in via your browser."
            return self.state

        self._active_account = _extract_account_from_token_payload(
            str(token_json["accessToken"]),
            token_json,
        )
        self._status = AuthStatus.AUTHENTICATED
        self._status_message = self._build_authenticated_message(self._active_account)
        logger.info("Restored Azure CLI Microsoft session for %s", self._active_account.username)
        return self.state

    def sign_in_interactive(self, *, force_select_account: bool = False) -> AuthStateSnapshot:
        """Launch interactive Microsoft browser sign-in via `az login --allow-no-subscriptions`."""
        az_path = self._require_az()
        cmd = [az_path, "login", "--allow-no-subscriptions", "--output", "json"]

        logger.info(
            "Starting browser sign-in via Azure CLI (switch_account=%s)",
            force_select_account,
        )
        try:
            proc = self._run(cmd, 180.0)
        except subprocess.TimeoutExpired as exc:
            self._status = AuthStatus.ERROR
            self._status_message = "Microsoft browser sign-in timed out."
            raise MsalAuthenticationError(
                "Azure CLI login timed out.",
                user_message="Microsoft browser sign-in timed out. Please try again.",
            ) from exc

        if proc.returncode != 0:
            stderr = redact_secrets((proc.stderr or "").strip())
            self._status = AuthStatus.ERROR
            self._status_message = "Microsoft sign-in was cancelled or failed."
            logger.warning("Azure CLI login failed (code=%d): %s", proc.returncode, stderr[:200])
            raise MsalAuthenticationError(
                f"Azure CLI login failed (code={proc.returncode})",
                user_message="Microsoft browser sign-in was cancelled or could not complete.",
            )

        login_accounts: list[dict[str, Any]] = []
        try:
            parsed = json.loads(proc.stdout)
            if isinstance(parsed, list):
                login_accounts = parsed
        except json.JSONDecodeError:
            pass

        token_json = self._fetch_powerbi_token_json(az_path)
        self._active_account = _extract_account_from_token_payload(
            str(token_json["accessToken"]),
            token_json,
            login_accounts=login_accounts,
        )
        self._status = AuthStatus.AUTHENTICATED
        self._status_message = self._build_authenticated_message(self._active_account)
        logger.info("Authenticated via Azure CLI as %s", self._active_account.username)
        return self.state

    def switch_account(self) -> AuthStateSnapshot:
        """Open Microsoft browser login to sign in with another account."""
        return self.sign_in_interactive(force_select_account=True)

    def get_access_token(
        self,
        *,
        scopes: list[str] | None = None,
        allow_interactive_fallback: bool = False,
    ) -> str:
        """Return a fresh Power BI access token from the active Azure CLI session."""
        _ = scopes  # Azure CLI acquires tokens by resource URL for Power BI Service
        az_path = self._require_az()
        try:
            token_json = self._fetch_powerbi_token_json(az_path)
        except MsalAuthenticationError:
            if allow_interactive_fallback:
                self.sign_in_interactive()
                token_json = self._fetch_powerbi_token_json(az_path)
            else:
                self._status = AuthStatus.EXPIRED
                self._status_message = "Session expired or signed out. Please sign in again."
                raise

        token = str(token_json["accessToken"])
        if self._active_account is None:
            self._active_account = _extract_account_from_token_payload(token, token_json)
        self._status = AuthStatus.AUTHENTICATED
        return token

    def sign_out(self) -> AuthStateSnapshot:
        """Sign out of the Azure CLI session cleanly."""
        az_path = self._az_finder()
        if az_path:
            try:
                self._run([az_path, "logout"], 20.0)
            except Exception:
                logger.debug("Ignored error during Azure CLI logout.")

        self._active_account = None
        self._status = AuthStatus.SIGNED_OUT
        self._status_message = "Signed out of Microsoft session."
        logger.info("Signed out of Azure CLI Microsoft session.")
        return self.state

    @staticmethod
    def _build_authenticated_message(account: AuthAccount) -> str:
        if account.is_personal_account:
            return (
                "Signed in with a personal Microsoft account. "
                "Power BI workspace access typically requires an organizational Entra ID account."
            )
        return "Authenticated with Microsoft (Azure CLI). Workspace permissions will be verified per registration."
