# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec for Pharmacy Management System.

Build with:
    pyinstaller pharmacy_management.spec

Produces: dist/PharmacyManagement/PharmacyManagement.exe

Notes:
- onedir style is used (not onefile): faster startup, and the database/,
  logs/, and backups/ folders are visible alongside the executable.
- Alembic migrations are bundled so a fresh install can upgrade the DB.
"""
import os
from PyInstaller.utils.hooks import collect_submodules, collect_data_files

block_cipher = None

hidden_imports = (
    collect_submodules("alembic")
    + collect_submodules("sqlalchemy.dialects.sqlite")
    + collect_submodules("sqlalchemy.dialects")
    + collect_submodules("PySide6")
    + [
        "barcode.writer",
        "PIL",
        "PIL._imagingtk",
        "reportlab.graphics.barcode",
        "reportlab.graphics.charts",
        "qrcode",
        "qrcode.image.pil",
        "openpyxl",
        "pandas",
        "bcrypt",
    ]
)

# Only include datas that actually exist
datas = [
    ("database/migrations", "database/migrations"),
    ("alembic.ini", "."),
]

# Include assets folder only if it exists
if os.path.exists("assets"):
    datas.append(("assets", "assets"))
else:
    import sys
    print("WARNING: assets/ folder not found — logo and icons will be missing in the build!", file=sys.stderr)

a = Analysis(
    ["main.py"],
    pathex=["."],
    binaries=[],
    datas=datas,
    hiddenimports=hidden_imports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["tkinter", "matplotlib", "matplotlib.tests", "pytest", "pytest_cov"],
    noarchive=False,
    cipher=block_cipher,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="PharmacyManagement",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,   # no black terminal window on Windows
    icon="assets/icons/app.ico" if os.path.exists("assets/icons/app.ico") else None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="PharmacyManagement",
)
