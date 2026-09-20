# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec — Zulfiqar Medical Store Pharmacy Management v2.1

Build:
    pyinstaller pharmacy_management.spec --clean --noconfirm

Output: dist/ZulfiqarMedicalStore/ZulfiqarMedicalStore.exe
"""
import os
import sys
from PyInstaller.utils.hooks import collect_submodules

block_cipher = None

hidden_imports = (
    collect_submodules("alembic")
    + collect_submodules("sqlalchemy")
    + collect_submodules("sqlalchemy.dialects.sqlite")
    + collect_submodules("sqlalchemy.dialects")
    + collect_submodules("PySide6")
    + [
        "logging", "logging.config", "logging.handlers",
        "importlib.metadata", "importlib.resources",
        "importlib.abc", "importlib.machinery", "importlib.util",
        "configparser", "threading", "queue", "socket",
        "email", "email.mime", "email.mime.text",
        "http", "http.client", "urllib", "urllib.parse", "urllib.request",
        "xml.etree.ElementTree", "decimal", "fractions", "statistics",
        "textwrap", "unicodedata", "codecs", "encodings",
        "encodings.utf_8", "encodings.ascii", "encodings.latin_1",
        "app", "app.ui.common", "app.ui.common.expiry_alert",
        "app.ui.common.medicine_search_widget",
        "app.services.invoice_edit_service",
        "barcode", "barcode.writer", "barcode.codex",
        "PIL", "PIL._imaging", "PIL.Image", "PIL.ImageDraw", "PIL.ImageFont",
        "reportlab", "reportlab.graphics", "reportlab.graphics.barcode",
        "reportlab.graphics.charts", "reportlab.platypus",
        "reportlab.platypus.tables", "reportlab.lib",
        "reportlab.lib.pagesizes", "reportlab.lib.styles",
        "reportlab.lib.units", "reportlab.lib.colors",
        "reportlab.pdfgen", "reportlab.pdfgen.canvas",
        "qrcode", "qrcode.image.pil", "qrcode.image.base",
        "openpyxl", "openpyxl.styles", "openpyxl.utils", "openpyxl.writer.excel",
        "pandas", "pandas.io.formats.excel", "pandas.io.parsers",
        "bcrypt",
        "mako", "mako.template", "mako.lookup", "mako.runtime",
        "mako.filters", "mako.cache", "mako.codegen", "mako.compat",
        "win32com", "win32com.client", "win32com.shell", "pywintypes",
        "shutil", "sqlite3",
    ]
)

datas = [
    ("database/migrations", "database/migrations"),
    ("alembic.ini", "."),
]
if os.path.exists("assets"):
    datas.append(("assets", "assets"))

a = Analysis(
    ["main.py"],
    pathex=["."],
    binaries=[],
    datas=datas,
    hiddenimports=hidden_imports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "tkinter", "matplotlib", "matplotlib.tests",
        "pytest", "pytest_cov", "_pytest",
        "IPython", "notebook", "jupyter", "scipy",
        "PyQt5", "PyQt6",
    ],
    noarchive=False,
    cipher=block_cipher,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="ZulfiqarMedicalStore",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    icon="assets/icons/app.ico" if os.path.exists("assets/icons/app.ico") else None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=["vcruntime140.dll", "python3*.dll"],
    name="ZulfiqarMedicalStore",
)
