@echo off
setlocal
cd /d "%~dp0"

echo Creating Power BI Validator desktop shortcut...
powershell -NoProfile -ExecutionPolicy Bypass -Command "$ws = New-Object -ComObject WScript.Shell; $d = [Environment]::GetFolderPath('Desktop'); $s = $ws.CreateShortcut(\"$d\Power BI Validator.lnk\"); $s.TargetPath = \"$env:USERPROFILE\.venvs\powerbi-validation-tool\Scripts\pythonw.exe\"; $s.Arguments = '-m app.main'; $s.WorkingDirectory = (Get-Location).Path; $s.IconLocation = \"$((Get-Location).Path)\assets\app_icon.ico\"; $s.Description = 'Power BI Automated Validation Tool'; $s.Save(); Write-Host 'Desktop shortcut created successfully!'"

echo Done.
