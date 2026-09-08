"""
Asset path resolution — works in both dev mode and PyInstaller bundles.

In dev:      base = project root  (two parents above this file)
In bundle:   sys._MEIPASS is the temp folder where PyInstaller unpacks data
"""
from __future__ import annotations

import sys
from pathlib import Path


def _base_dir() -> Path:
    """Return the root directory that contains the 'assets/' folder."""
    if getattr(sys, "frozen", False):
        # Running inside a PyInstaller bundle
        return Path(sys._MEIPASS)  # type: ignore[attr-defined]
    # Running from source: this file is at app/utils/assets.py
    # → go up two levels to reach the project root
    return Path(__file__).parent.parent.parent


def asset_path(relative: str) -> str:
    """Return the absolute path to an asset file as a string.

    Example:
        asset_path("assets/icons/app.ico")   → "D:/...project.../assets/icons/app.ico"
    """
    return str(_base_dir() / relative)
