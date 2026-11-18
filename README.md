# Power BI Validation Tool

Local-first Windows desktop application for automating Power BI report and semantic model validation.

## Current Stage

**Stage 2 — Local SQLite Foundation**

- Local SQLite database (`%LOCALAPPDATA%\PowerBIValidationTool\data\validation_tool.db`) created and migrated automatically on startup via SQLAlchemy 2.0 + Alembic
- Core tables: `app_settings`, `workspace_registrations`, `validation_rules`, `validation_runs`, `validation_results`, `refresh_records`
- Repository layer (`app/database/repositories/`) for CRUD operations, duplicate-registration protection, immutable run history, and secret-key rejection in `app_settings`
- Backup & restore design notes documented in `docs/database_backup_restore.md`
- Layered architecture, Pydantic config, rotating secret-redacting logs, global exception hooks, and reusable UI components (Stages 0–1)

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
