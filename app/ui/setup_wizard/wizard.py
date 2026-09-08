"""
First-run Setup Wizard (Phase 1 §42): shown only when
`auth_service.needs_first_run_setup()` is True. Two steps — Pharmacy Info,
then Create Administrator — followed by DB init (already done by the time
this runs, via `alembic upgrade head` at app startup) and a finish screen.
Demo data insertion is left as a script-level option (`scripts/seed_demo_data.py
--with-demo-data`) rather than a wizard step, since it's a one-off dev/demo
convenience rather than something a real pharmacy needs on every first run.
"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFormLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QVBoxLayout,
    QWizard,
    QWizardPage,
)

from app.database.session import session_scope
from app.models import ApplicationSetting
from app.services import auth_service
from app.utils.exceptions import ApplicationError


class PharmacyInfoPage(QWizardPage):
    def __init__(self) -> None:
        super().__init__()
        self.setTitle("Pharmacy Information")
        self.setSubTitle("This appears on invoices and reports. You can change it later in Settings.")

        self.name_edit = QLineEdit()
        self.address_edit = QLineEdit()
        self.phone_edit = QLineEdit()

        layout = QFormLayout(self)
        layout.addRow("Pharmacy Name *", self.name_edit)
        layout.addRow("Address", self.address_edit)
        layout.addRow("Phone", self.phone_edit)

        self.registerField("pharmacy_name*", self.name_edit)
        self.registerField("pharmacy_address", self.address_edit)
        self.registerField("pharmacy_phone", self.phone_edit)


class CreateAdminPage(QWizardPage):
    def __init__(self) -> None:
        super().__init__()
        self.setTitle("Create Administrator")
        self.setSubTitle("This account has full access to the system. Choose a strong password.")

        self.username_edit = QLineEdit()
        self.full_name_edit = QLineEdit()
        self.password_edit = QLineEdit()
        self.password_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.confirm_edit = QLineEdit()
        self.confirm_edit.setEchoMode(QLineEdit.EchoMode.Password)

        layout = QFormLayout(self)
        layout.addRow("Username *", self.username_edit)
        layout.addRow("Full Name", self.full_name_edit)
        layout.addRow("Password *", self.password_edit)
        layout.addRow("Confirm Password *", self.confirm_edit)

        self.registerField("admin_username*", self.username_edit)
        self.registerField("admin_full_name", self.full_name_edit)
        self.registerField("admin_password*", self.password_edit)

    def validatePage(self) -> bool:
        if self.password_edit.text() != self.confirm_edit.text():
            QMessageBox.warning(self, "Password mismatch", "The two passwords you entered do not match.")
            return False
        if len(self.password_edit.text()) < auth_service.MIN_PASSWORD_LENGTH:
            QMessageBox.warning(
                self, "Weak password",
                f"Password must be at least {auth_service.MIN_PASSWORD_LENGTH} characters.",
            )
            return False
        return True


class FinishPage(QWizardPage):
    def __init__(self) -> None:
        super().__init__()
        self.setTitle("Setup Complete")
        layout = QVBoxLayout(self)
        label = QLabel("Your pharmacy is ready to go. Click Finish to continue to the login screen.")
        label.setWordWrap(True)
        layout.addWidget(label)


class SetupWizard(QWizard):
    """On acceptance, persists pharmacy info and creates the admin account.
    Any failure (e.g. someone raced to create an admin from another
    process) is shown as a friendly message, never a raw traceback."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Pharmacy Management System — First-Run Setup")
        self.setWizardStyle(QWizard.WizardStyle.ModernStyle)
        self.setOption(QWizard.WizardOption.NoBackButtonOnStartPage, True)

        self.addPage(PharmacyInfoPage())
        self.addPage(CreateAdminPage())
        self.addPage(FinishPage())

    def accept(self) -> None:
        try:
            # Use upsert pattern so re-running the wizard (e.g. on a
            # restored DB that already has these keys) doesn't crash with
            # a UNIQUE constraint IntegrityError.
            with session_scope() as session:
                for key, value in [
                    ("pharmacy.name", self.field("pharmacy_name")),
                    ("pharmacy.address", self.field("pharmacy_address")),
                    ("pharmacy.phone", self.field("pharmacy_phone")),
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
        except ApplicationError as exc:
            QMessageBox.critical(self, "Setup failed", str(exc))
            return
        except Exception as exc:
            QMessageBox.critical(self, "Setup failed", f"Unexpected error: {exc}")
            return
        super().accept()
