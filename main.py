"""
Application entry point.

Flow: init DB (create_all — production should run `alembic upgrade head`
via the packaged installer/first-launch script instead) -> first-run
setup wizard if no admin exists yet -> login window -> main window with
permission-gated sidebar navigation (Admin dashboard, Medicines,
Inventory, Sales/POS, Purchases, Customers, Suppliers, Reports, and for
admins, Users and Settings).
"""
from __future__ import annotations

import sys

from PySide6.QtWidgets import QApplication, QMessageBox

from app.database.migrate import run_migrations_to_head
from app.logging.setup import configure_logging
from app.services import auth_service
from app.ui.login.login_window import LoginWindow
from app.ui.main.main_window import MainWindow
from app.ui.setup_wizard.wizard import SetupWizard


class AppController:
    """Owns window lifecycle so login -> main window -> logout -> login
    can cycle without leaking widgets."""

    def __init__(self) -> None:
        self.main_window: MainWindow | None = None
        self.login_window: LoginWindow | None = None

    def start(self) -> None:
        if auth_service.needs_first_run_setup():
            wizard = SetupWizard()
            if wizard.exec() != SetupWizard.DialogCode.Accepted:
                sys.exit(0)
            QMessageBox.information(None, "Setup complete", "Administrator account created. Please log in.")
        self.show_login()

    def show_login(self) -> None:
        self.login_window = LoginWindow()
        self.login_window.login_succeeded.connect(self.show_main_window)
        self.login_window.show()

    def show_main_window(self) -> None:
        if self.login_window:
            self.login_window.close()
            self.login_window = None
        self.main_window = MainWindow(on_logout=self._handle_logout)
        self.main_window.show()

    def _handle_logout(self) -> None:
        if self.main_window:
            self.main_window.close()
            self.main_window = None
        self.show_login()


def main() -> None:
    configure_logging()
    run_migrations_to_head()  # creates the DB fresh, or upgrades it in place — never destructive
    app = QApplication(sys.argv)

    # Set application-wide icon (taskbar, Alt+Tab, etc.)
    from PySide6.QtGui import QIcon
    from app.utils.assets import asset_path
    app.setWindowIcon(QIcon(asset_path("assets/icons/app.ico")))

    # One-time offer to create a Desktop shortcut (frozen/EXE builds only)
    from app.utils.shortcut import maybe_offer_desktop_shortcut
    maybe_offer_desktop_shortcut()

    controller = AppController()
    controller.start()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
