"""
First-run Setup Wizard — shown only when no admin account exists yet.

Pages:
  1. Welcome / Choose path:
       • Start fresh  →  go to PharmacyInfoPage then CreateAdminPage
       • Restore from backup  →  go to RestoreBackupPage then done
  2. PharmacyInfoPage  (only in fresh-start path)
  3. CreateAdminPage   (only in fresh-start path)
  4. RestoreBackupPage (only in restore path)
  5. FinishPage
"""
from __future__ import annotations

import shutil
import sqlite3
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QRadioButton,
    QVBoxLayout,
    QWizard,
    QWizardPage,
)

from app.database.session import session_scope
from app.models import ApplicationSetting
from app.services import auth_service
from app.utils.exceptions import ApplicationError


# ── Shared validation ─────────────────────────────────────────────────────

_REQUIRED_TABLES = {"users", "medicines", "medicine_batches", "sales", "stock_transactions"}


def _validate_backup(path: Path) -> str | None:
    """Returns None if valid, or an error message string."""
    if not path.exists():
        return f"File not found: {path}"
    try:
        con = sqlite3.connect(str(path))
        cursor = con.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = {row[0] for row in cursor.fetchall()}
        con.close()
    except sqlite3.Error as exc:
        return f"Not a valid SQLite database: {exc}"
    missing = _REQUIRED_TABLES - tables
    if missing:
        return f"Not a pharmacy database — missing table(s): {', '.join(sorted(missing))}"
    return None


# ── Page 1: Welcome / Choose path ────────────────────────────────────────

class WelcomePage(QWizardPage):
    """Asks the user whether to start fresh or restore from a backup."""

    # Page IDs used for custom navigation
    PAGE_WELCOME  = 0
    PAGE_INFO     = 1
    PAGE_ADMIN    = 2
    PAGE_RESTORE  = 3
    PAGE_FINISH   = 4

    def __init__(self) -> None:
        super().__init__()
        self.setTitle("Welcome to Zulfiqar Medical Store")
        self.setSubTitle("Choose how you want to set up this system.")
        layout = QVBoxLayout(self)
        layout.setSpacing(16)

        self._fresh_radio = QRadioButton(
            "🆕  Start fresh — set up a new pharmacy from scratch"
        )
        self._fresh_radio.setChecked(True)
        self._fresh_radio.setStyleSheet("font-size: 13px; padding: 6px 0;")

        self._restore_radio = QRadioButton(
            "📂  Restore from backup — I have a database backup from a previous version"
        )
        self._restore_radio.setStyleSheet("font-size: 13px; padding: 6px 0;")

        layout.addWidget(self._fresh_radio)

        restore_note = QLabel(
            "<i>Use this if you upgraded to Version 2.0 and want to keep your medicines, "
            "sales history, customers, and all other data from Version 1.0.</i>"
        )
        restore_note.setTextFormat(Qt.TextFormat.RichText)
        restore_note.setWordWrap(True)
        restore_note.setStyleSheet("color: #555; font-size: 12px; margin-left: 24px;")
        layout.addWidget(restore_note)

        layout.addWidget(self._restore_radio)

        fresh_note = QLabel(
            "<i>Use this for a completely new installation with no previous data.</i>"
        )
        fresh_note.setTextFormat(Qt.TextFormat.RichText)
        fresh_note.setWordWrap(True)
        fresh_note.setStyleSheet("color: #555; font-size: 12px; margin-left: 24px;")
        layout.addWidget(fresh_note)

        layout.addStretch()

    def is_restore_path(self) -> bool:
        return self._restore_radio.isChecked()

    def nextId(self) -> int:
        if self._restore_radio.isChecked():
            return WelcomePage.PAGE_RESTORE
        return WelcomePage.PAGE_INFO


# ── Page 2: Pharmacy Info ────────────────────────────────────────────────

class PharmacyInfoPage(QWizardPage):
    def __init__(self) -> None:
        super().__init__()
        self.setTitle("Pharmacy Information")
        self.setSubTitle("This appears on invoices and reports. You can change it later in Settings.")

        self.name_edit    = QLineEdit()
        self.address_edit = QLineEdit()
        self.phone_edit   = QLineEdit()

        layout = QFormLayout(self)
        layout.addRow("Pharmacy Name *", self.name_edit)
        layout.addRow("Address",         self.address_edit)
        layout.addRow("Phone",           self.phone_edit)

        self.registerField("pharmacy_name*", self.name_edit)
        self.registerField("pharmacy_address", self.address_edit)
        self.registerField("pharmacy_phone",   self.phone_edit)

    def nextId(self) -> int:
        return WelcomePage.PAGE_ADMIN


# ── Page 3: Create Admin ─────────────────────────────────────────────────

class CreateAdminPage(QWizardPage):
    def __init__(self) -> None:
        super().__init__()
        self.setTitle("Create Administrator")
        self.setSubTitle("This account has full access. Choose a strong password.")

        self.username_edit = QLineEdit()
        self.full_name_edit = QLineEdit()
        self.password_edit  = QLineEdit()
        self.password_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.confirm_edit   = QLineEdit()
        self.confirm_edit.setEchoMode(QLineEdit.EchoMode.Password)

        layout = QFormLayout(self)
        layout.addRow("Username *",         self.username_edit)
        layout.addRow("Full Name",          self.full_name_edit)
        layout.addRow("Password *",         self.password_edit)
        layout.addRow("Confirm Password *", self.confirm_edit)

        self.registerField("admin_username*",  self.username_edit)
        self.registerField("admin_full_name",  self.full_name_edit)
        self.registerField("admin_password*",  self.password_edit)

    def validatePage(self) -> bool:
        if self.password_edit.text() != self.confirm_edit.text():
            QMessageBox.warning(self, "Password mismatch",
                                "The two passwords do not match.")
            return False
        if len(self.password_edit.text()) < auth_service.MIN_PASSWORD_LENGTH:
            QMessageBox.warning(
                self, "Weak password",
                f"Password must be at least {auth_service.MIN_PASSWORD_LENGTH} characters.",
            )
            return False
        return True

    def nextId(self) -> int:
        return WelcomePage.PAGE_FINISH


# ── Page 4: Restore from Backup ──────────────────────────────────────────

class RestoreBackupPage(QWizardPage):
    """
    Lets the user pick a .db backup file from Version 1.0 (or any previous
    version) and validates it before the wizard accepts.

    The actual file copy happens in SetupWizard.accept() so it runs inside
    the same transaction as all the other first-run setup steps.
    """

    def __init__(self) -> None:
        super().__init__()
        self.setTitle("Restore from Backup")
        self.setSubTitle("Select your backup file to restore all medicines, sales, and data.")
        self._backup_path: Path | None = None

        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        info = QLabel(
            "<b>How to find your backup file:</b><br>"
            "In your old installation, go to <b>Settings → Backup Database Now</b>.<br>"
            "The backup is saved in the <code>backups/</code> folder next to the "
            "<code>PharmacyManagement.exe</code> file.<br><br>"
            "You can also browse to any <code>.db</code> file you have saved."
        )
        info.setTextFormat(Qt.TextFormat.RichText)
        info.setWordWrap(True)
        info.setStyleSheet(
            "background: #eaf4fb; padding: 10px; border-radius: 5px; "
            "border: 1px solid #aed6f1; font-size: 12px;"
        )
        layout.addWidget(info)

        browse_row = QHBoxLayout()
        self._path_label = QLabel("No file selected")
        self._path_label.setStyleSheet(
            "color: #555; font-size: 12px; padding: 6px; "
            "background: #f8f9fa; border: 1px solid #dee2e6; border-radius: 4px;"
        )
        self._path_label.setWordWrap(True)
        browse_row.addWidget(self._path_label, 1)

        browse_btn = QPushButton("📂  Browse…")
        browse_btn.setMinimumHeight(36)
        browse_btn.setStyleSheet(
            "padding: 6px 16px; font-weight: 600; font-size: 13px;"
        )
        browse_btn.clicked.connect(self._browse)
        browse_row.addWidget(browse_btn)
        layout.addLayout(browse_row)

        self._status_label = QLabel("")
        self._status_label.setWordWrap(True)
        self._status_label.setStyleSheet("font-size: 12px;")
        layout.addWidget(self._status_label)

        layout.addStretch()

    def _browse(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Select Backup File", "", "SQLite Database (*.db);;All Files (*)"
        )
        if not path:
            return

        candidate = Path(path)
        error = _validate_backup(candidate)
        if error:
            self._path_label.setText(str(candidate))
            self._status_label.setText(f"❌  {error}")
            self._status_label.setStyleSheet("color: #c0392b; font-size: 12px;")
            self._backup_path = None
        else:
            self._backup_path = candidate
            self._path_label.setText(str(candidate))
            self._status_label.setText(
                "✔  Valid pharmacy database found — click Next to restore."
            )
            self._status_label.setStyleSheet(
                "color: #1e8449; font-weight: 600; font-size: 12px;"
            )
        self.completeChanged.emit()

    def isComplete(self) -> bool:
        return self._backup_path is not None

    def get_backup_path(self) -> Path | None:
        return self._backup_path

    def nextId(self) -> int:
        return WelcomePage.PAGE_FINISH


# ── Page 5: Finish ───────────────────────────────────────────────────────

class FinishPage(QWizardPage):
    def __init__(self) -> None:
        super().__init__()
        self.setTitle("Setup Complete")
        layout = QVBoxLayout(self)
        label = QLabel(
            "Your pharmacy is ready to go.\n"
            "Click Finish to continue to the login screen."
        )
        label.setWordWrap(True)
        layout.addWidget(label)

    def nextId(self) -> int:
        return -1  # last page


# ── Setup Wizard ─────────────────────────────────────────────────────────

class SetupWizard(QWizard):
    """
    First-run wizard. Two paths:
      A) Fresh start  →  Page1 → PharmacyInfo → CreateAdmin → Finish
      B) Restore      →  Page1 → RestoreBackup → Finish
    """

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Pharmacy Management System — Setup")
        self.setWizardStyle(QWizard.WizardStyle.ModernStyle)
        self.setOption(QWizard.WizardOption.NoBackButtonOnStartPage, True)
        self.setMinimumSize(620, 460)

        self._welcome_page  = WelcomePage()
        self._info_page     = PharmacyInfoPage()
        self._admin_page    = CreateAdminPage()
        self._restore_page  = RestoreBackupPage()
        self._finish_page   = FinishPage()

        self.setPage(WelcomePage.PAGE_WELCOME, self._welcome_page)
        self.setPage(WelcomePage.PAGE_INFO,    self._info_page)
        self.setPage(WelcomePage.PAGE_ADMIN,   self._admin_page)
        self.setPage(WelcomePage.PAGE_RESTORE, self._restore_page)
        self.setPage(WelcomePage.PAGE_FINISH,  self._finish_page)

        self.setStartId(WelcomePage.PAGE_WELCOME)

    def accept(self) -> None:
        try:
            if self._welcome_page.is_restore_path():
                self._do_restore()
            else:
                self._do_fresh_setup()
        except ApplicationError as exc:
            QMessageBox.critical(self, "Setup failed", str(exc))
            return
        except Exception as exc:
            QMessageBox.critical(self, "Setup failed", f"Unexpected error: {exc}")
            return
        super().accept()

    # ── Fresh start ───────────────────────────────────────────────────────

    def _do_fresh_setup(self) -> None:
        with session_scope() as session:
            for key, value in [
                ("pharmacy.name",    self.field("pharmacy_name")),
                ("pharmacy.address", self.field("pharmacy_address")),
                ("pharmacy.phone",   self.field("pharmacy_phone")),
            ]:
                row = session.query(ApplicationSetting).filter_by(key=key).one_or_none()
                if row:
                    row.value = value
                else:
                    session.add(ApplicationSetting(key=key, value=value))

        auth_service.create_first_admin(
            username=self.field("admin_username"),
            password=self.field("admin_password"),
            full_name=self.field("admin_full_name") or None,
        )

    # ── Restore from backup ───────────────────────────────────────────────

    def _do_restore(self) -> None:
        backup_path = self._restore_page.get_backup_path()
        if backup_path is None:
            raise ApplicationError("No backup file selected.")

        # Validate one more time
        error = _validate_backup(backup_path)
        if error:
            raise ApplicationError(f"Backup validation failed: {error}")

        # Get live DB path from settings
        from app.config.settings import settings as app_settings
        if not app_settings.database_url.startswith("sqlite:///"):
            raise ApplicationError("Restore supports SQLite databases only.")

        live_path = Path(app_settings.database_url.replace("sqlite:///", "", 1))

        # Release all DB connections before swapping the file
        from app.database.session import get_engine
        get_engine().dispose()

        # Copy backup over the live DB
        live_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(backup_path, live_path)

        # Clear WAL/SHM sidecars
        for suffix in ("-wal", "-shm"):
            sidecar = live_path.with_name(live_path.name + suffix)
            sidecar.unlink(missing_ok=True)

        # Run migrations on the restored DB to bring it up to the latest schema
        # (handles upgrades from v1.0 to v2.0 safely)
        from app.database.migrate import run_migrations_to_head
        run_migrations_to_head()

        QMessageBox.information(
            self, "Backup Restored ✔",
            f"Database restored from:\n{backup_path}\n\n"
            "All your medicines, sales history, customers and settings "
            "have been restored.\n\n"
            "Please log in with your existing administrator username and password."
        )
