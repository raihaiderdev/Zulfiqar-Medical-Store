"""
Login window with Forgot Password / Reset Password option.
"""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QIcon, QPixmap
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
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
from app.utils.exceptions import AuthenticationError, ApplicationError

_REMEMBERED_USERNAME_SETTING_KEY = "ui.remembered_username"

# ── Reset Password dialog ─────────────────────────────────────────────────

class ResetPasswordDialog(QDialog):
    """
    Allows an admin to reset any user's password directly from the login screen.

    Flow:
      1. Enter the username whose password you want to reset.
      2. Enter the admin master key (the pharmacy name set during setup,
         used as a recovery phrase — simple but effective for a single-
         location desktop app that has no internet).
      3. Enter and confirm a new password.

    The admin master key is the pharmacy name stored in ApplicationSetting.
    This means the person who did the original setup can always recover access.
    """

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Reset Password")
        self.setMinimumWidth(420)
        layout = QVBoxLayout(self)

        # Info banner — load pharmacy name to show as hint
        pharmacy_hint = "the pharmacy name set during setup"
        try:
            from app.database.session import session_scope
            from app.models import ApplicationSetting
            with session_scope() as session:
                s = session.query(ApplicationSetting).filter_by(key="pharmacy.name").one_or_none()
                if s and s.value:
                    pharmacy_hint = f'<b style="color:#154c89">{s.value}</b>'
        except Exception:
            pass

        info = QLabel(
            f"<b>Reset Password</b><br><br>"
            f"Enter the username and the pharmacy name as the recovery key, "
            f"then choose a new password.<br><br>"
            f"Recovery Key (pharmacy name): {pharmacy_hint}"
        )
        info.setTextFormat(Qt.TextFormat.RichText)
        info.setWordWrap(True)
        info.setStyleSheet(
            "background:#eaf4fb; padding:10px; border-radius:5px; "
            "border:1px solid #aed6f1; font-size:12px;"
        )
        layout.addWidget(info)

        form = QFormLayout()

        self.username_edit = QLineEdit()
        self.username_edit.setPlaceholderText("Enter the username to reset")
        self.username_edit.setMinimumHeight(32)
        form.addRow("Username *:", self.username_edit)

        self.recovery_key_edit = QLineEdit()
        self.recovery_key_edit.setPlaceholderText("Pharmacy name (e.g. Zulfiqar Medical Store)")
        self.recovery_key_edit.setMinimumHeight(32)
        form.addRow("Recovery Key *:", self.recovery_key_edit)

        self.new_password_edit = QLineEdit()
        self.new_password_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.new_password_edit.setPlaceholderText("Min 8 characters")
        self.new_password_edit.setMinimumHeight(32)
        form.addRow("New Password *:", self.new_password_edit)

        self.confirm_edit = QLineEdit()
        self.confirm_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.confirm_edit.setMinimumHeight(32)
        form.addRow("Confirm Password *:", self.confirm_edit)

        self.show_pwd_check = QCheckBox("Show passwords")
        self.show_pwd_check.toggled.connect(self._toggle_visibility)
        form.addRow("", self.show_pwd_check)

        layout.addLayout(form)

        self._status_label = QLabel("")
        self._status_label.setWordWrap(True)
        self._status_label.setStyleSheet("color: #c0392b; font-size: 12px;")
        layout.addWidget(self._status_label)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        ok_btn = buttons.button(QDialogButtonBox.StandardButton.Ok)
        ok_btn.setText("Reset Password")
        ok_btn.setStyleSheet(
            "background-color: #154c89; color: white; "
            "font-weight: 700; padding: 6px 18px; border-radius: 4px;"
        )
        buttons.accepted.connect(self._do_reset)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _toggle_visibility(self, checked: bool) -> None:
        mode = QLineEdit.EchoMode.Normal if checked else QLineEdit.EchoMode.Password
        self.new_password_edit.setEchoMode(mode)
        self.confirm_edit.setEchoMode(mode)

    def _do_reset(self) -> None:
        username     = self.username_edit.text().strip()
        recovery_key = self.recovery_key_edit.text().strip()
        new_password = self.new_password_edit.text()
        confirm      = self.confirm_edit.text()

        # Basic validation
        if not username:
            self._status_label.setText("Username is required.")
            return
        if not recovery_key:
            self._status_label.setText("Recovery key is required.")
            return
        if len(new_password) < 8:
            self._status_label.setText("New password must be at least 8 characters.")
            return
        if new_password != confirm:
            self._status_label.setText("Passwords do not match.")
            return

        # Verify the recovery key against the pharmacy name in settings
        try:
            from app.database.session import session_scope
            from app.models import ApplicationSetting, User
            from app.security.passwords import hash_password
            import re

            def _normalise(text: str) -> str:
                """Lower-case, remove all spaces and punctuation for fuzzy match."""
                return re.sub(r'[^a-z0-9]', '', text.lower())

            with session_scope() as session:
                # Check pharmacy name (fuzzy — ignore case/spaces/punctuation)
                setting = session.query(ApplicationSetting).filter_by(
                    key="pharmacy.name"
                ).one_or_none()
                stored_name = (setting.value or "").strip() if setting else ""

                if _normalise(stored_name) != _normalise(recovery_key):
                    # Show hint: first 4 chars of stored name so user can verify
                    hint = stored_name[:6] + "..." if len(stored_name) > 6 else stored_name
                    self._status_label.setText(
                        f"Recovery key is incorrect.\n"
                        f"Hint: the stored pharmacy name starts with  '{hint}'\n"
                        f"Enter the pharmacy name exactly as set during setup."
                    )
                    return

                # Find user
                user = session.query(User).filter(
                    User.username == username
                ).one_or_none()
                if user is None:
                    # Try case-insensitive match
                    from sqlalchemy import func
                    user = session.query(User).filter(
                        func.lower(User.username) == username.lower()
                    ).one_or_none()
                if user is None:
                    self._status_label.setText(
                        f"Username '{username}' not found.\n"
                        "Check the spelling and try again."
                    )
                    return

                # Reset password
                user.password_hash = hash_password(new_password)
                session.add(user)

        except Exception as exc:
            self._status_label.setText(f"Error: {exc}")
            return

        QMessageBox.information(
            self, "Password Reset ✔",
            f"Password for '{username}' has been reset successfully.\n\n"
            f"You can now log in with the new password."
        )
        self.accept()


# ── Login Window ──────────────────────────────────────────────────────────

class LoginWindow(QWidget):
    """Emits `login_succeeded` once `auth_service.login()` succeeds."""

    login_succeeded = Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Zulfiqar Medical Store — Login")
        self.setMinimumWidth(420)
        self.setWindowIcon(QIcon(asset_path("assets/icons/app.ico")))
        self._build_ui()
        self._load_remembered_username()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setSpacing(8)

        # ── Logo ──────────────────────────────────────────────────────────
        logo_label = QLabel()
        logo_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        logo_pixmap = QPixmap(asset_path("assets/icons/logo_256.png"))
        if not logo_pixmap.isNull():
            logo_label.setPixmap(
                logo_pixmap.scaled(
                    160, 160,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
            )
        root.addWidget(logo_label)

        title = QLabel("Zulfiqar Medical Store")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet(
            "font-size: 20px; font-weight: 700; color: #154c89; margin-bottom: 4px;"
        )
        root.addWidget(title)

        subtitle = QLabel("Pharmacy Management System")
        subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        subtitle.setStyleSheet(
            "font-size: 13px; color: #555; margin-bottom: 12px;"
        )
        root.addWidget(subtitle)

        # ── Form ──────────────────────────────────────────────────────────
        form = QFormLayout()
        self.username_edit = QLineEdit()
        self.username_edit.setPlaceholderText("Username")
        self.username_edit.setMinimumHeight(34)

        self.password_edit = QLineEdit()
        self.password_edit.setPlaceholderText("Password")
        self.password_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.password_edit.setMinimumHeight(34)
        self.password_edit.returnPressed.connect(self._attempt_login)

        form.addRow("Username", self.username_edit)
        form.addRow("Password", self.password_edit)
        root.addLayout(form)

        # ── Options row ───────────────────────────────────────────────────
        options_row = QHBoxLayout()
        self.show_password_checkbox = QCheckBox("Show password")
        self.show_password_checkbox.toggled.connect(self._toggle_password_visibility)
        self.remember_username_checkbox = QCheckBox("Remember username")
        options_row.addWidget(self.show_password_checkbox)
        options_row.addWidget(self.remember_username_checkbox)
        root.addLayout(options_row)

        # ── Error label ───────────────────────────────────────────────────
        self.error_label = QLabel("")
        self.error_label.setStyleSheet("color: #c0392b;")
        self.error_label.setWordWrap(True)
        root.addWidget(self.error_label)

        # ── Buttons ───────────────────────────────────────────────────────
        buttons_row = QHBoxLayout()

        self.clear_button = QPushButton("Clear")
        self.clear_button.clicked.connect(self._clear_form)
        self.clear_button.setStyleSheet("padding: 6px 14px;")

        self.login_button = QPushButton("Login")
        self.login_button.setDefault(True)
        self.login_button.clicked.connect(self._attempt_login)
        self.login_button.setStyleSheet(
            "background-color: #154c89; color: white; "
            "font-weight: 700; padding: 6px 24px; border-radius: 4px;"
        )

        buttons_row.addWidget(self.clear_button)
        buttons_row.addStretch()
        buttons_row.addWidget(self.login_button)
        root.addLayout(buttons_row)

        # ── Forgot password link ──────────────────────────────────────────
        forgot_row = QHBoxLayout()
        forgot_row.addStretch()
        self.forgot_btn = QPushButton("🔑  Forgot Password? Reset it")
        self.forgot_btn.setStyleSheet(
            "QPushButton { border: none; color: #2980b9; font-size: 12px; "
            "text-decoration: underline; background: transparent; padding: 4px; }"
            "QPushButton:hover { color: #154c89; }"
        )
        self.forgot_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.forgot_btn.clicked.connect(self._open_reset_dialog)
        forgot_row.addWidget(self.forgot_btn)
        forgot_row.addStretch()
        root.addLayout(forgot_row)

        # ── Version ───────────────────────────────────────────────────────
        version_label = QLabel(f"Version {settings.app_version}")
        version_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        version_label.setStyleSheet(
            "color: #888; font-size: 11px; margin-top: 6px;"
        )
        root.addWidget(version_label)

    # ── Slots ─────────────────────────────────────────────────────────────

    def _toggle_password_visibility(self, checked: bool) -> None:
        self.password_edit.setEchoMode(
            QLineEdit.EchoMode.Normal if checked else QLineEdit.EchoMode.Password
        )

    def _clear_form(self) -> None:
        self.username_edit.clear()
        self.password_edit.clear()
        self.error_label.setText("")
        self.username_edit.setFocus()

    def _open_reset_dialog(self) -> None:
        dlg = ResetPasswordDialog(self)
        dlg.exec()

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
                    session.add(
                        ApplicationSetting(
                            key=_REMEMBERED_USERNAME_SETTING_KEY, value=value
                        )
                    )
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
        except Exception:
            QMessageBox.critical(
                self, "Unexpected error", "Something went wrong. Please try again."
            )
            return
        finally:
            self.login_button.setEnabled(True)

        self._save_remembered_username(username)
        self.password_edit.clear()
        self.login_succeeded.emit()
