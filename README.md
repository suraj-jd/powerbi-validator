# Power BI Validation Tool

Local-first Windows desktop application for automating Power BI report and semantic model validation.

## Current Stage

**Stage 3 — Microsoft Authentication**

- Microsoft Entra ID public-client sign-in via MSAL OAuth 2.0 + PKCE (system browser interactive login, no passwords or client secrets)
- Windows DPAPI (`CryptProtectData` / `CryptUnprotectData`) encrypted MSAL token cache stored at `%LOCALAPPDATA%\PowerBIValidationTool\auth\msal_token_cache.bin` (never stored in SQLite)
- Silent session restoration on startup, expired/revoked session detection, **Switch Account**, and **Sign Out** (clears local token cache)
- Non-blocking `AuthService` background worker, Home `AuthBanner`, sidebar account profile panel, and `Configure Entra App` dialog
- Entra App Registration setup guide in [docs/entra_app_registration.md](docs/entra_app_registration.md)
- Local SQLite persistence via SQLAlchemy + Alembic, rotating secret-redacting logs, and reusable UI components (Stages 0–2)

## Setup & Run (Windows PowerShell)

```powershell
# Create virtual environment (placed on C: if D: has limited free space)
py -3.12 -m venv C:\Users\suraj\.venvs\powerbi-validation-tool

# Activate virtual environment
C:\Users\suraj\.venvs\powerbi-validation-tool\Scripts\Activate.ps1

# Install dependencies
pip install -r requirements.txt

# Launch the application
python -m app.main
```

## Run Tests

```powershell
pytest
```
