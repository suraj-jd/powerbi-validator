# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller build specification for Power BI Validation Tool (Stage 15)."""

import os
from pathlib import Path
from PyInstaller.utils.hooks import collect_data_files, collect_submodules

block_cipher = None
project_root = Path(os.path.abspath(SPECPATH))

# Collect non-python assets and database migration templates
datas = [
    (str(project_root / "assets"), "assets"),
    (str(project_root / "app" / "database" / "migrations"), "app/database/migrations"),
    (str(project_root / "alembic.ini"), "."),
]

# Hidden imports to ensure dynamic modules are packaged
hiddenimports = [
    "alembic",
    "alembic.config",
    "alembic.script",
    "alembic.environment",
    "openpyxl",
    "openpyxl.styles",
    "openpyxl.utils",
    "sqlite3",
    "pydantic",
    "msal",
    "httpx",
    "sqlalchemy",
    "sqlalchemy.dialects.sqlite",
    "PySide6.QtCore",
    "PySide6.QtGui",
    "PySide6.QtWidgets",
    "PySide6.QtSvg",
    "PySide6.QtSvgWidgets",
]
hiddenimports += collect_submodules("app")

# Ensure no local secrets or active databases are inadvertently bundled
excludes = [
    "tests",
    "*.pyc",
    "*.db",
    "*.token_cache",
    "*.log",
]

a = Analysis(
    ["app/main.py"],
    pathex=[str(project_root)],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=excludes,
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(
    a.pure,
    a.zipped_data,
    cipher=block_cipher,
)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="PowerBIValidationTool",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,  # Windowed desktop application
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=str(project_root / "assets" / "app_icon.ico") if (project_root / "assets" / "app_icon.ico").exists() else None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="PowerBIValidationTool",
)
