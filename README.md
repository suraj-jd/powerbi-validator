# Power BI Validation Tool

Local-first Windows desktop application for automating Power BI report and semantic model validation.

## Current Stage

**Stage 5 — Workspace, Report & Dataset Registry UI**

- Settings page **Workspace & Dataset Configuration** table loaded automatically from SQLite at startup
- Manual Add, Edit, Toggle Active/Inactive, Delete (with confirmation), GUID format validation, duplicate detection, and live **Verify Access** against Power BI REST APIs
- CSV and XLSX import workflow with row-by-row validation preview, explicit row-level error reporting (never silently discarding invalid rows), and blank CSV/XLSX template export
- Power BI REST connectivity & permission verification, Microsoft Entra ID MSAL auth + Windows DPAPI token cache, SQLite/Alembic persistence, and reusable UI components (Stages 0–4)

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
