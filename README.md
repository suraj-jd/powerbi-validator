# Power BI Validation Tool

Local-first Windows desktop application for automating Power BI report and semantic model validation.

## Current Stage

**Stage 0 — Base PySide6 Desktop Shell**

- Runnable PySide6 Windows desktop application
- Dark navy sidebar navigation (`Home`, `Settings`, `History`, `About`)
- Light enterprise theme with resizable layout and placeholder pages
- Application title, version, and window icon placeholder
- Basic logging and clean exit flow
- No Power BI credentials, network calls, or local database yet

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
