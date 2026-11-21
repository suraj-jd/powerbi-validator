@echo off
setlocal
cd /d "%~dp0"

set VENV_PYTHON=%USERPROFILE%\.venvs\powerbi-validation-tool\Scripts\pythonw.exe

if exist "%VENV_PYTHON%" (
    start "" "%VENV_PYTHON%" -m app.main
) else (
    start "" pythonw -m app.main
)
exit /b 0
