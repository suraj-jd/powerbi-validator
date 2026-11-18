# Power BI Validation Tool

Local-first Windows desktop application for automating Power BI report and semantic model validation.

## Current Stage

**Stage 4 — Power BI Connectivity & Permission Verification**

- Authenticated Power BI Service REST client (`app/integrations/powerbi/rest_client.py`) using `httpx` with timeouts, `Retry-After` throttling retries (HTTP 429), and clear `401`/`403`/`404`/`5xx` error handling
- Typed Pydantic Power BI models and clients (`WorkspaceClient`, `DatasetClient`) for listing accessible workspaces, datasets, reports, and verifying workspace/dataset/report permissions using the signed-in user's identity
- Honest permission reporting grounded strictly in Microsoft API responses (never infers workspace ownership from sign-in alone)
- Non-blocking `PowerBIService` background worker and interactive Home access verification panel
- Microsoft Entra ID MSAL auth + Windows DPAPI token cache, SQLite/Alembic persistence, and reusable UI components (Stages 0–3)

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
