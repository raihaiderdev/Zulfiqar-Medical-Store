"""
Login window (Phase 1 §3). Always the first screen once first-run setup
is complete. Calls only `auth_service.login()` — never touches the ORM.
"""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QIcon, QPixmap
from PySide6.QtWidgets import (
    QCheckBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from app.config.settings import settings
from app.services import auth_service
from app.utils.assets import asset_path
from app.utils.exceptions import AuthenticationError

_REMEMBERED_USERNAME_SETTING_KEY = "ui.remembered_username"


class LoginWindow(QWidget):
    """Emits `login_succeeded` once `auth_service.login()` has populated
    the process-wide session, so the caller (main.py) knows to swap to
    the admin/user dashboard."""

    login_succeeded = Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Zulfiqar Medical Store — Login")
        self.setMinimumWidth(400)

        # Set window icon
        icon_file = asset_path("assets/icons/app.ico")
        self.setWindowIcon(QIcon(icon_file))

        self._build_ui()
        self._load_remembered_username()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setSpacing(8)

        # --- Logo ---
        logo_label = QLabel()
        logo_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        logo_pixmap = QPixmap(asset_path("assets/icons/logo_256.png"))
        if not logo_pixmap.isNull():
            logo_label.setPixmap(logo_pixmap.scaled(160, 160, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
        root.addWidget(logo_label)

        title = QLabel("Zulfiqar Medical Store")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet("font-size: 20px; font-weight: 700; color: #154c89; margin-bottom: 4px;")
        root.addWidget(title)

        subtitle = QLabel("Pharmacy Management System")
        subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        subtitle.setStyleSheet("font-size: 13px; color: #555; margin-bottom: 12px;")
        root.addWidget(subtitle)

        form = QFormLayout()
        self.username_edit = QLineEdit()
        self.username_edit.setPlaceholderText("Username")

        self.password_edit = QLineEdit()
        self.password_edit.setPlaceholderText("Password")
        self.password_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.password_edit.returnPressed.connect(self._attempt_login)

        form.addRow("Username", self.username_edit)
        form.addRow("Password", self.password_edit)
        root.addLayout(form)

        options_row = QHBoxLayout()
        self.show_password_checkbox = QCheckBox("Show password")
        self.show_password_checkbox.toggled.connect(self._toggle_password_visibility)
        self.remember_username_checkbox = QCheckBox("Remember username")
        options_row.addWidget(self.show_password_checkbox)
        options_row.addWidget(self.remember_username_checkbox)
        root.addLayout(options_row)

        self.error_label = QLabel("")
        self.error_label.setStyleSheet("color: #c0392b;")
        self.error_label.setWordWrap(True)
        root.addWidget(self.error_label)

        buttons_row = QHBoxLayout()
        self.login_button = QPushButton("Login")
        self.login_button.setDefault(True)
        self.login_button.clicked.connect(self._attempt_login)
        self.clear_button = QPushButton("Clear")
        self.clear_button.clicked.connect(self._clear_form)
        buttons_row.addWidget(self.clear_button)
        buttons_row.addWidget(self.login_button)
        root.addLayout(buttons_row)

        version_label = QLabel(f"Version {settings.app_version}")
        version_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        version_label.setStyleSheet("color: #888; font-size: 11px; margin-top: 8px;")
        root.addWidget(version_label)

    def _toggle_password_visibility(self, checked: bool) -> None:
        self.password_edit.setEchoMode(
            QLineEdit.EchoMode.Normal if checked else QLineEdit.EchoMode.Password
        )

    def _clear_form(self) -> None:
        self.username_edit.clear()
        self.password_edit.clear()
        self.error_label.setText("")
        self.username_edit.setFocus()

    def _load_remembered_username(self) -> None:
        try:
            from app.database.session import session_scope
            from app.models import ApplicationSetting

            with session_scope() as session:
                row = (
                    session.query(ApplicationSetting)
                    .filter_by(key=_REMEMBERED_USERNAME_SETTING_KEY)
                    .one_or_none()
                )
                if row and row.value:
                    self.username_edit.setText(row.value)
                    self.remember_username_checkbox.setChecked(True)
                    self.password_edit.setFocus()
        except Exception:
            # Non-critical convenience feature — never block login over it.
            pass

    def _save_remembered_username(self, username: str) -> None:
        try:
            from app.database.session import session_scope
            from app.models import ApplicationSetting

            with session_scope() as session:
                row = (
                    session.query(ApplicationSetting)
                    .filter_by(key=_REMEMBERED_USERNAME_SETTING_KEY)
                    .one_or_none()
                )
                value = username if self.remember_username_checkbox.isChecked() else ""
                if row:
                    row.value = value
                    session.add(row)
                else:
                    session.add(ApplicationSetting(key=_REMEMBERED_USERNAME_SETTING_KEY, value=value))
        except Exception:
            pass

    def _attempt_login(self) -> None:
        username = self.username_edit.text().strip()
        password = self.password_edit.text()
        self.error_label.setText("")

        if not username or not password:
            self.error_label.setText("Please enter both username and password.")
            return

        self.login_button.setEnabled(False)
        try:
            auth_service.login(username, password)
        except AuthenticationError as exc:
            self.error_label.setText(str(exc))
            self.password_edit.clear()
            self.password_edit.setFocus()
            return
        except Exception as exc:  # noqa: BLE001 - never show a raw traceback to the user
            QMessageBox.critical(self, "Unexpected error", "Something went wrong. Please try again.")
            return
        finally:
            self.login_button.setEnabled(True)

        self._save_remembered_username(username)
        self.password_edit.clear()
        self.login_succeeded.emit()
