"""Microsoft Entra ID authentication client built on MSAL PublicClientApplication."""

from __future__ import annotations

import logging
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Any

import msal

from app.auth.token_cache import ProtectedTokenCache
from app.core.exceptions import AuthenticationError

logger = logging.getLogger(__name__)

# Standard Microsoft Consumer (MSA) tenant GUID.
PERSONAL_ACCOUNT_TENANT_ID = "9188040d-6c67-4c5b-b112-36a304b66dad"

# Minimal delegated Power BI Service read scopes required by the application.
DEFAULT_POWERBI_SCOPES: tuple[str, ...] = (
    "https://analysis.windows.net/powerbi/api/Workspace.Read.All",
    "https://analysis.windows.net/powerbi/api/Dataset.Read.All",
    "https://analysis.windows.net/powerbi/api/Report.Read.All",
)

MSAL_SUCCESS_TEMPLATE = """<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>Authentication Complete - Power BI Validation Tool</title>
    <style>
        body {
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
            background: #0B1120;
            color: #F8FAFC;
            display: flex;
            align-items: center;
            justify-content: center;
            height: 100vh;
            margin: 0;
        }
        .card {
            background: #162032;
            border: 1px solid #1E293B;
            border-radius: 12px;
            padding: 36px 48px;
            text-align: center;
            box-shadow: 0 20px 40px rgba(0,0,0,0.4);
            max-width: 440px;
        }
        h2 { color: #38BDF8; margin-top: 0; font-size: 22px; }
        p { color: #94A3B8; font-size: 14px; line-height: 1.5; }
        .badge {
            display: inline-block;
            background: #0369A1;
            color: #E0F2FE;
            padding: 4px 12px;
            border-radius: 9999px;
            font-size: 12px;
            font-weight: 600;
            margin-bottom: 12px;
        }
    </style>
</head>
<body>
    <div class="card">
        <div class="badge">Authenticated</div>
        <h2>Sign-In Complete</h2>
        <p>You have signed in successfully. You are now returning to the <strong>Power BI Validation Tool</strong>.</p>
        <p style="font-size: 12px; color: #64748B;">You can safely close this browser window or tab.</p>
    </div>
    <script>
        setTimeout(function() { window.close(); }, 2500);
    </script>
</body>
</html>
"""

MSAL_ERROR_TEMPLATE = """<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>Authentication Incomplete - Power BI Validation Tool</title>
    <style>
        body {
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
            background: #0B1120;
            color: #F8FAFC;
            display: flex;
            align-items: center;
            justify-content: center;
            height: 100vh;
            margin: 0;
        }
        .card {
            background: #162032;
            border: 1px solid #EF4444;
            border-radius: 12px;
            padding: 36px 48px;
            text-align: center;
            box-shadow: 0 20px 40px rgba(0,0,0,0.4);
            max-width: 440px;
        }
        h2 { color: #F87171; margin-top: 0; font-size: 22px; }
        p { color: #94A3B8; font-size: 14px; line-height: 1.5; }
    </style>
</head>
<body>
    <div class="card">
        <h2>Sign-In Incomplete</h2>
        <p>$error: $error_description</p>
        <p style="font-size: 12px; color: #64748B;">Please return to the Power BI Validation Tool desktop application to try again.</p>
    </div>
</body>
</html>
"""

_GUID_RE = re.compile(
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
)
_NAMED_TENANTS = {"organizations", "common", "consumers"}


def is_valid_guid(value: str) -> bool:
    """Return True if `value` is a syntactically valid GUID."""
    return bool(_GUID_RE.match(value.strip()))


def is_valid_tenant(value: str) -> bool:
    """Return True if `value` is a valid tenant GUID, named authority, or domain."""
    cleaned = value.strip()
    if not cleaned:
        return False
    if cleaned.lower() in _NAMED_TENANTS or is_valid_guid(cleaned):
        return True
    # Allow verified domain names such as contoso.onmicrosoft.com
    return "." in cleaned and " " not in cleaned


class AuthStatus(StrEnum):
    """High-level authentication session states."""

    NOT_CONFIGURED = "not_configured"
    SIGNED_OUT = "signed_out"
    SIGNING_IN = "signing_in"
    AUTHENTICATED = "authenticated"
    EXPIRED = "expired"
    ERROR = "error"


@dataclass(frozen=True, slots=True)
class AuthAccount:
    """Safe, non-secret summary of the signed-in Microsoft account."""

    home_account_id: str
    display_name: str
    username: str
    tenant_id: str
    is_personal_account: bool = False

    @property
    def initials(self) -> str:
        """Compute 1–2 character avatar initials from display name or email."""
        source = (self.display_name or self.username or "?").strip()
        parts = [p for p in re.split(r"[\s._-]+", source.split("@")[0]) if p]
        if len(parts) >= 2:
            return (parts[0][0] + parts[1][0]).upper()
        if parts:
            return parts[0][:2].upper()
        return "?"


@dataclass(frozen=True, slots=True)
class AuthStateSnapshot:
    """Immutable view of the current authentication state for UI rendering."""

    status: AuthStatus
    account: AuthAccount | None = None
    status_message: str = ""
    client_id_configured: bool = False
    tenant_id: str = "organizations"


@dataclass(frozen=True, slots=True)
class AuthConfig:
    """Non-secret OAuth public-client configuration for MSAL."""

    client_id: str
    tenant_id: str = "organizations"
    scopes: tuple[str, ...] = field(default_factory=lambda: DEFAULT_POWERBI_SCOPES)

    @property
    def is_configured(self) -> bool:
        return is_valid_guid(self.client_id) and is_valid_tenant(self.tenant_id)

    @property
    def authority(self) -> str:
        return f"https://login.microsoftonline.com/{self.tenant_id.strip() or 'organizations'}"


class MsalAuthenticationError(AuthenticationError):
    """Authentication error indicating whether interactive reauthentication is required."""

    def __init__(
        self,
        message: str,
        *,
        user_message: str | None = None,
        interaction_required: bool = False,
        error_code: str | None = None,
    ) -> None:
        super().__init__(message, user_message=user_message)
        self.interaction_required = interaction_required
        self.error_code = error_code


PcaFactory = Callable[[str, str, msal.SerializableTokenCache], Any]


def _default_pca_factory(
    client_id: str,
    authority: str,
    token_cache: msal.SerializableTokenCache,
) -> msal.PublicClientApplication:
    return msal.PublicClientApplication(
        client_id=client_id,
        authority=authority,
        token_cache=token_cache,
    )


def _extract_account_info(
    msal_account: dict[str, Any] | None,
    token_result: dict[str, Any] | None = None,
) -> AuthAccount:
    claims = (token_result or {}).get("id_token_claims") or {}
    acct = msal_account or {}

    username = str(
        acct.get("username")
        or claims.get("preferred_username")
        or claims.get("upn")
        or claims.get("email")
        or ""
    ).strip()
    display_name = str(claims.get("name") or acct.get("name") or username or "Microsoft User").strip()
    tenant_id = str(acct.get("realm") or claims.get("tid") or "").strip()
    home_account_id = str(acct.get("home_account_id") or claims.get("oid") or username).strip()
    is_personal = tenant_id.lower() == PERSONAL_ACCOUNT_TENANT_ID

    return AuthAccount(
        home_account_id=home_account_id,
        display_name=display_name,
        username=username,
        tenant_id=tenant_id,
        is_personal_account=is_personal,
    )


def _is_interaction_required(result: dict[str, Any]) -> bool:
    error = str(result.get("error") or "").lower()
    suberror = str(result.get("suberror") or "").lower()
    desc = str(result.get("error_description") or "").lower()
    return any(
        marker in combined
        for combined in (error, suberror, desc)
        for marker in (
            "interaction_required",
            "login_required",
            "consent_required",
            "invalid_grant",
            "aadsts50076",
            "aadsts50079",
            "aadsts700082",
            "aadsts50173",
        )
    )


class MsalAuthClient:
    """Manages Microsoft sign-in, silent token refresh, account switching, and sign-out."""

    def __init__(
        self,
        config: AuthConfig,
        cache_path: Path,
        *,
        pca_factory: PcaFactory | None = None,
    ) -> None:
        self._config = config
        self._token_cache = ProtectedTokenCache(cache_path)
        self._pca_factory = pca_factory or _default_pca_factory
        self._pca: Any | None = None
        self._active_account: AuthAccount | None = None
        self._active_msal_account: dict[str, Any] | None = None
        self._status: AuthStatus = (
            AuthStatus.SIGNED_OUT if config.is_configured else AuthStatus.NOT_CONFIGURED
        )
        self._status_message = (
            "Sign in with Microsoft to connect to Power BI."
            if config.is_configured
            else "Configure a Microsoft Entra Client ID to enable sign-in."
        )

    @property
    def config(self) -> AuthConfig:
        return self._config

    @property
    def state(self) -> AuthStateSnapshot:
        return AuthStateSnapshot(
            status=self._status,
            account=self._active_account,
            status_message=self._status_message,
            client_id_configured=self._config.is_configured,
            tenant_id=self._config.tenant_id,
        )

    def reconfigure(self, config: AuthConfig) -> AuthStateSnapshot:
        """Update Entra Client ID / Tenant ID and reset the MSAL client handle."""
        self._config = config
        self._pca = None
        if not config.is_configured:
            self._status = AuthStatus.NOT_CONFIGURED
            self._status_message = "Configure a Microsoft Entra Client ID to enable sign-in."
        elif self._active_account is None:
            self._status = AuthStatus.SIGNED_OUT
            self._status_message = "Entra app configured. Sign in with Microsoft to continue."
        return self.state

    def _ensure_pca(self) -> Any:
        if not self._config.is_configured:
            raise MsalAuthenticationError(
                "Microsoft Entra Client ID is not configured.",
                user_message=(
                    "Microsoft Entra App Registration is not configured yet. "
                    "Click 'Configure Entra App' and enter your Application (Client) ID."
                ),
            )
        if self._pca is None:
            self._pca = self._pca_factory(
                self._config.client_id,
                self._config.authority,
                self._token_cache.msal_cache,
            )
        return self._pca

    def _select_cached_msal_account(self, pca: Any) -> dict[str, Any] | None:
        accounts = pca.get_accounts() or []
        if not accounts:
            return None
        if self._active_account is not None:
            for acct in accounts:
                if acct.get("home_account_id") == self._active_account.home_account_id:
                    return acct
        return accounts[0]

    def restore_session(self) -> AuthStateSnapshot:
        """Attempt silent session restoration from the DPAPI-protected token cache."""
        if not self._config.is_configured:
            self._status = AuthStatus.NOT_CONFIGURED
            self._status_message = "Configure a Microsoft Entra Client ID to enable sign-in."
            return self.state

        pca = self._ensure_pca()
        cached_account = self._select_cached_msal_account(pca)
        if cached_account is None:
            self._active_account = None
            self._active_msal_account = None
            self._status = AuthStatus.SIGNED_OUT
            self._status_message = "Sign in with Microsoft to connect to Power BI."
            return self.state

        result = pca.acquire_token_silent(
            scopes=list(self._config.scopes),
            account=cached_account,
        )
        self._token_cache.save()

        if result and "access_token" in result:
            self._active_msal_account = cached_account
            self._active_account = _extract_account_info(cached_account, result)
            self._status = AuthStatus.AUTHENTICATED
            self._status_message = self._build_authenticated_message(self._active_account)
            logger.info("Restored Microsoft session silently for %s", self._active_account.username)
            return self.state

        # Cached account exists, but token expired or was revoked — prompt reauth cleanly.
        self._active_msal_account = cached_account
        self._active_account = _extract_account_info(cached_account, result)
        self._status = AuthStatus.EXPIRED
        self._status_message = (
            "Your previous Microsoft session expired or requires re-authentication. "
            "Please sign in again."
        )
        logger.info("Cached Microsoft session requires interactive re-authentication.")
        return self.state

    def sign_in_interactive(self, *, force_select_account: bool = False) -> AuthStateSnapshot:
        """Launch system-browser interactive Microsoft sign-in (OAuth 2.0 + PKCE)."""
        pca = self._ensure_pca()
        kwargs: dict[str, Any] = {
            "scopes": list(self._config.scopes),
            "success_template": MSAL_SUCCESS_TEMPLATE,
            "error_template": MSAL_ERROR_TEMPLATE,
        }
        if force_select_account:
            kwargs["prompt"] = "select_account"

        logger.info(
            "Starting interactive Microsoft sign-in (select_account=%s)",
            force_select_account,
        )
        try:
            result = pca.acquire_token_interactive(**kwargs)
        except Exception as exc:
            self._status = AuthStatus.ERROR
            self._status_message = "Interactive Microsoft sign-in failed or was cancelled."
            raise MsalAuthenticationError(
                f"Interactive sign-in failed: {type(exc).__name__}",
                user_message="Interactive Microsoft sign-in failed or was cancelled.",
            ) from exc

        self._token_cache.save()

        if not result or "access_token" not in result:
            error_code = str((result or {}).get("error") or "auth_failed")
            error_desc = str(
                (result or {}).get("error_description")
                or "Microsoft sign-in did not complete."
            )
            self._status = AuthStatus.ERROR
            self._status_message = f"Sign-in failed ({error_code})."
            logger.warning("Interactive Microsoft sign-in failed with code=%s", error_code)
            raise MsalAuthenticationError(
                f"Interactive sign-in failed ({error_code}): {error_desc}",
                user_message=f"Microsoft sign-in did not succeed ({error_code}).",
                interaction_required=_is_interaction_required(result or {}),
                error_code=error_code,
            )

        # Match the newly signed-in account in cache
        accounts = pca.get_accounts() or []
        claims = result.get("id_token_claims") or {}
        preferred_username = str(claims.get("preferred_username") or "").lower()
        matched = next(
            (a for a in accounts if str(a.get("username") or "").lower() == preferred_username),
            accounts[0] if accounts else None,
        )

        self._active_msal_account = matched
        self._active_account = _extract_account_info(matched, result)
        self._status = AuthStatus.AUTHENTICATED
        self._status_message = self._build_authenticated_message(self._active_account)
        logger.info("Authenticated Microsoft user: %s", self._active_account.username)
        return self.state

    def switch_account(self) -> AuthStateSnapshot:
        """Sign in interactively while prompting Microsoft to choose a different account."""
        return self.sign_in_interactive(force_select_account=True)

    def get_access_token(
        self,
        *,
        scopes: list[str] | None = None,
        allow_interactive_fallback: bool = False,
    ) -> str:
        """Acquire a valid Power BI access token silently (or interactively if allowed).

        Raw tokens are returned to API clients in memory and NEVER logged.
        """
        pca = self._ensure_pca()
        target_scopes = list(scopes or self._config.scopes)
        account = self._active_msal_account or self._select_cached_msal_account(pca)

        if account is None:
            if allow_interactive_fallback:
                self.sign_in_interactive()
                return self.get_access_token(scopes=target_scopes, allow_interactive_fallback=False)
            self._status = AuthStatus.SIGNED_OUT
            raise MsalAuthenticationError(
                "No signed-in Microsoft account available.",
                user_message="Please sign in with Microsoft before connecting to Power BI.",
                interaction_required=True,
            )

        result = pca.acquire_token_silent(scopes=target_scopes, account=account)
        self._token_cache.save()

        if result and "access_token" in result:
            self._active_msal_account = account
            if self._active_account is None:
                self._active_account = _extract_account_info(account, result)
            self._status = AuthStatus.AUTHENTICATED
            return str(result["access_token"])

        if allow_interactive_fallback:
            self.sign_in_interactive()
            return self.get_access_token(scopes=target_scopes, allow_interactive_fallback=False)

        self._status = AuthStatus.EXPIRED
        self._status_message = "Session expired or consent required. Please sign in again."
        error_code = str((result or {}).get("error") or "interaction_required")
        raise MsalAuthenticationError(
            f"Silent token acquisition failed ({error_code}).",
            user_message="Your Microsoft session has expired or needs re-authentication. Please sign in again.",
            interaction_required=True,
            error_code=error_code,
        )

    def sign_out(self) -> AuthStateSnapshot:
        """Remove all cached accounts and wipe the local DPAPI-protected token cache."""
        if self._pca is not None:
            for account in list(self._pca.get_accounts() or []):
                try:
                    self._pca.remove_account(account)
                except Exception:
                    logger.debug("Ignored error removing account during sign-out.")

        self._token_cache.clear()
        self._pca = None
        self._active_account = None
        self._active_msal_account = None
        self._status = (
            AuthStatus.SIGNED_OUT if self._config.is_configured else AuthStatus.NOT_CONFIGURED
        )
        self._status_message = (
            "Signed out. Local authentication cache cleared."
            if self._config.is_configured
            else "Signed out. Configure a Microsoft Entra Client ID to sign in."
        )
        logger.info("User signed out and local token cache cleared.")
        return self.state

    @staticmethod
    def _build_authenticated_message(account: AuthAccount) -> str:
        if account.is_personal_account:
            return (
                "Signed in with a personal Microsoft account. "
                "Power BI workspace access typically requires an organizational Entra ID account."
            )
        return "Authenticated with Microsoft Entra ID. Workspace permissions will be verified per registration."
