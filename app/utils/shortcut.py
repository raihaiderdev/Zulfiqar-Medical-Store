"""
Desktop shortcut helper — Windows only.

Offers to create a Desktop shortcut pointing to the running EXE the
first time the packaged application launches.  In dev/source mode this
is a no-op so developers are never prompted.

The "already asked" flag is stored as a plain text file next to the EXE
so it survives across DB restores.
"""
from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

logger = logging.getLogger(__name__)


def _is_frozen() -> bool:
    """True only when running inside a PyInstaller bundle."""
    return getattr(sys, "frozen", False)


def _flag_file() -> Path:
    """Path to the flag file that records we have already offered a shortcut."""
    exe_dir = Path(sys.executable).parent if _is_frozen() else Path.cwd()
    return exe_dir / ".shortcut_offered"


def _exe_path() -> Path:
    return Path(sys.executable)


def _desktop_path() -> Path:
    return Path(os.path.join(os.path.expanduser("~"), "Desktop"))


def _icon_path() -> Path | None:
    """Return path to app.ico sitting next to the EXE (in _internal/assets/icons/)."""
    from app.utils.assets import asset_path
    p = Path(asset_path("assets/icons/app.ico"))
    return p if p.exists() else None


def _create_shortcut() -> bool:
    """Create PharmacyManagement.lnk on the Desktop. Returns True on success."""
    try:
        import win32com.client  # type: ignore[import]
    except ImportError:
        # pywin32 not available — fall back to PowerShell WScript.Shell
        return _create_shortcut_via_powershell()

    try:
        shell = win32com.client.Dispatch("WScript.Shell")
        shortcut = shell.CreateShortCut(str(_desktop_path() / "PharmacyManagement.lnk"))
        shortcut.TargetPath = str(_exe_path())
        shortcut.WorkingDirectory = str(_exe_path().parent)
        shortcut.Description = "Zulfiqar Medical Store — Pharmacy Management"
        icon = _icon_path()
        if icon:
            shortcut.IconLocation = str(icon)
        shortcut.save()
        return True
    except Exception as exc:
        logger.warning("Shortcut creation via win32com failed: %s", exc)
        return _create_shortcut_via_powershell()


def _create_shortcut_via_powershell() -> bool:
    """Fallback: create the shortcut via a PowerShell one-liner."""
    import subprocess

    exe = str(_exe_path()).replace("'", "''")
    work = str(_exe_path().parent).replace("'", "''")
    dest = str(_desktop_path() / "PharmacyManagement.lnk").replace("'", "''")
    icon = _icon_path()
    icon_str = f"$s.IconLocation = '{str(icon).replace(chr(39), chr(39)*2)}';" if icon else ""

    ps_script = (
        f"$ws = New-Object -ComObject WScript.Shell;"
        f"$s = $ws.CreateShortcut('{dest}');"
        f"$s.TargetPath = '{exe}';"
        f"$s.WorkingDirectory = '{work}';"
        f"$s.Description = 'Zulfiqar Medical Store - Pharmacy Management';"
        f"{icon_str}"
        f"$s.Save()"
    )
    try:
        result = subprocess.run(
            ["powershell", "-NoProfile", "-Command", ps_script],
            capture_output=True,
            timeout=10,
        )
        return result.returncode == 0
    except Exception as exc:
        logger.warning("Shortcut creation via PowerShell failed: %s", exc)
        return False


def maybe_offer_desktop_shortcut(parent=None) -> None:
    """
    Show a one-time dialog asking the user whether to create a Desktop
    shortcut.  Does nothing if:
      - not running as a frozen bundle
      - the flag file already exists (already asked before)
      - the Desktop folder cannot be found
    """
    if not _is_frozen():
        return  # dev mode — never prompt

    flag = _flag_file()
    if flag.exists():
        return  # already offered

    # Mark as offered immediately so a crash mid-prompt doesn't loop
    try:
        flag.touch()
    except OSError:
        pass

    desktop = _desktop_path()
    if not desktop.exists():
        return  # unusual system layout

    # Import Qt only here (called after QApplication is created)
    from PySide6.QtWidgets import QMessageBox

    msg = QMessageBox(parent)
    msg.setWindowTitle("Create Desktop Shortcut")
    msg.setText(
        "Would you like to create a Desktop shortcut for\n"
        "Zulfiqar Medical Store — Pharmacy Management?"
    )
    msg.setIcon(QMessageBox.Icon.Question)
    msg.setStandardButtons(
        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
    )
    msg.setDefaultButton(QMessageBox.StandardButton.Yes)

    # Apply window icon if available
    from PySide6.QtGui import QIcon
    from app.utils.assets import asset_path
    ico = asset_path("assets/icons/app.ico")
    if Path(ico).exists():
        msg.setWindowIcon(QIcon(ico))

    if msg.exec() != QMessageBox.StandardButton.Yes:
        return

    if _create_shortcut():
        QMessageBox.information(
            parent,
            "Shortcut Created",
            "A Desktop shortcut has been created.\n"
            "You can now launch the application from your Desktop.",
        )
    else:
        QMessageBox.warning(
            parent,
            "Shortcut Failed",
            "Could not create the Desktop shortcut automatically.\n"
            "You can right-click PharmacyManagement.exe and choose\n"
            "'Send to → Desktop (create shortcut)' manually.",
        )
