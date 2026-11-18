# Power BI Validation Tool

Local-first Windows desktop application for automating Power BI report and semantic model validation.

## Current Stage

**Stage 1 — Architecture & Shared Components**

- Layered module structure (`app/core/`, `app/ui/models/`, `app/ui/widgets/`, `app/ui/dialogs/`, `app/bootstrap.py`)
- Validated central configuration using Pydantic (`%LOCALAPPDATA%\PowerBIValidationTool\config.json`, no secrets stored)
- Rotating local log files with automatic secret/token redaction
- Application-wide uncaught exception hooks for main and worker threads
- Reusable UI components: `NotificationBanner`, Qt Model/View `DataTableWidget`, and `ConfirmDialog`
- Updated `About` page with runtime diagnostics, log folder shortcut, and live component preview

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
