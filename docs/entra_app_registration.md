# Microsoft Entra ID App Registration Guide

The Power BI Validation Tool signs in interactively as a **Public Client (Desktop)** application using Microsoft Authentication Library (MSAL) with OAuth 2.0 + PKCE. **No client secret is created or stored.**

## 1. Create the App Registration
1. Open the [Microsoft Entra Admin Center](https://entra.microsoft.com) → **Identity** → **Applications** → **App registrations** → **New registration**.
2. **Name:** `Power BI Validation Tool (Desktop)`
3. **Supported account types:**
   - Recommended: **Accounts in this organizational directory only (Single tenant)**, or **Accounts in any organizational directory (Multitenant)**.
   - Note: Power BI workspace access requires an organizational Microsoft Entra ID tenant. Personal Microsoft accounts cannot generally access Power BI Service workspaces.
4. **Redirect URI:**
   - Platform: **Mobile and desktop applications** (Public client/native)
   - Redirect URI: `http://localhost`
5. Click **Register**.

## 2. Configure Delegated Power BI API Permissions
1. Go to **API permissions** → **Add a permission** → **Power BI Service** → **Delegated permissions**.
2. Select only the minimal read permissions needed:
   - `Workspace.Read.All` — list accessible workspaces and verify access
   - `Dataset.Read.All` — read semantic model metadata, refresh history, and execute DAX validation queries
   - `Report.Read.All` — read report metadata linked to semantic models
3. If required by your organization's tenant policy, ask a Microsoft Entra administrator to grant admin consent.

## 3. Configure in the Application
Provide the **Application (client) ID** and **Directory (tenant) ID** (or `organizations`) using either:
- The **Configure Entra App** button on the Home authentication banner inside the desktop app, OR
- Environment variables before launching:
  ```powershell
  $env:PBI_VALIDATOR_CLIENT_ID = "<your-application-client-id-guid>"
  $env:PBI_VALIDATOR_TENANT_ID = "<your-tenant-id-guid-or-organizations>"
  ```

## 4. Security Notes
- Tokens are cached solely in `%LOCALAPPDATA%\PowerBIValidationTool\auth\msal_token_cache.bin`, encrypted with **Windows DPAPI (`CryptProtectData`)** tied to your Windows user profile.
- Raw access tokens and refresh tokens are never stored in SQLite, never displayed in the UI, and automatically scrubbed from logs.
- Signing out clears both the in-memory MSAL cache and the local encrypted cache file.
