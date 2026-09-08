"""
Users page — Admin-only. Create users, grant/revoke permissions,
edit permissions after creation, deactivate/reactivate, reset passwords.
"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.permissions.keys import GRANTABLE_PERMISSIONS
from app.services import user_service
from app.utils.exceptions import ApplicationError


# ---------------------------------------------------------------------------
# Create User dialog
# ---------------------------------------------------------------------------
class AddUserDialog(QDialog):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Create User")
        self.setMinimumWidth(480)
        layout = QVBoxLayout(self)

        form = QFormLayout()
        self.username_edit = QLineEdit()
        self.full_name_edit = QLineEdit()
        self.password_edit = QLineEdit()
        self.password_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.is_admin_checkbox = QCheckBox("Grant full administrator access")
        self.is_admin_checkbox.toggled.connect(self._on_admin_toggled)
        form.addRow("Username *", self.username_edit)
        form.addRow("Full Name", self.full_name_edit)
        form.addRow("Password *", self.password_edit)
        form.addRow("", self.is_admin_checkbox)
        layout.addLayout(form)

        self.permission_group = QGroupBox("Grantable Permissions (ignored if Administrator is checked)")
        perm_layout = QVBoxLayout(self.permission_group)
        self.permission_checkboxes: dict[str, QCheckBox] = {}
        for key, description in GRANTABLE_PERMISSIONS.items():
            box = QCheckBox(f"{description}  [{key}]")
            perm_layout.addWidget(box)
            self.permission_checkboxes[key] = box

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(self.permission_group)
        scroll.setMaximumHeight(260)
        layout.addWidget(scroll)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._save)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _on_admin_toggled(self, checked: bool) -> None:
        self.permission_group.setEnabled(not checked)

    def _save(self) -> None:
        if not self.username_edit.text().strip() or not self.password_edit.text():
            QMessageBox.warning(self, "Missing field", "Username and password are required.")
            return
        selected_keys = [key for key, box in self.permission_checkboxes.items() if box.isChecked()]
        try:
            user_service.create_user(
                username=self.username_edit.text().strip(),
                password=self.password_edit.text(),
                full_name=self.full_name_edit.text().strip() or None,
                is_admin=self.is_admin_checkbox.isChecked(),
                permission_keys=selected_keys,
            )
        except ApplicationError as exc:
            QMessageBox.critical(self, "Could not create user", str(exc))
            return
        self.accept()


# ---------------------------------------------------------------------------
# Edit Permissions dialog  ← NEW
# ---------------------------------------------------------------------------
class EditPermissionsDialog(QDialog):
    def __init__(self, user_id: int, username: str, parent=None) -> None:
        super().__init__(parent)
        self._user_id = user_id
        self.setWindowTitle(f"Edit Permissions — {username}")
        self.setMinimumWidth(480)
        layout = QVBoxLayout(self)

        layout.addWidget(QLabel(f"Permissions for <b>{username}</b>:"))

        # Load current permissions
        current_perms: set[str] = set()
        try:
            current_perms = user_service.get_user_permissions(user_id)
        except ApplicationError:
            pass

        self.permission_group = QGroupBox("Grantable Permissions")
        perm_layout = QVBoxLayout(self.permission_group)
        self.permission_checkboxes: dict[str, QCheckBox] = {}
        for key, description in GRANTABLE_PERMISSIONS.items():
            box = QCheckBox(f"{description}  [{key}]")
            box.setChecked(key in current_perms)
            perm_layout.addWidget(box)
            self.permission_checkboxes[key] = box

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(self.permission_group)
        scroll.setMaximumHeight(300)
        layout.addWidget(scroll)

        # Quick-select helpers
        helper_row = QHBoxLayout()
        select_all_btn = QPushButton("Select All")
        select_all_btn.clicked.connect(lambda: self._toggle_all(True))
        clear_all_btn = QPushButton("Clear All")
        clear_all_btn.clicked.connect(lambda: self._toggle_all(False))
        helper_row.addWidget(select_all_btn)
        helper_row.addWidget(clear_all_btn)
        helper_row.addStretch()
        layout.addLayout(helper_row)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._save)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _toggle_all(self, state: bool) -> None:
        for box in self.permission_checkboxes.values():
            box.setChecked(state)

    def _save(self) -> None:
        selected_keys = [key for key, box in self.permission_checkboxes.items() if box.isChecked()]
        try:
            user_service.set_user_permissions(self._user_id, selected_keys)
        except ApplicationError as exc:
            QMessageBox.critical(self, "Could not save permissions", str(exc))
            return
        self.accept()


# ---------------------------------------------------------------------------
# Users page
# ---------------------------------------------------------------------------
class UsersPage(QWidget):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        root = QVBoxLayout(self)

        top_row = QHBoxLayout()
        header = QLabel("Users")
        header.setStyleSheet("font-size: 18px; font-weight: 600;")
        top_row.addWidget(header)
        top_row.addStretch()
        add_button = QPushButton("＋ Create User")
        add_button.setStyleSheet(
            "background-color: #27ae60; color: white; padding: 6px 14px; font-weight: 600;"
        )
        add_button.clicked.connect(self._add_user)
        top_row.addWidget(add_button)
        root.addLayout(top_row)

        # Table: ID, Username, Full Name, Role, Status, Actions
        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels([
            "ID", "Username", "Full Name", "Role", "Status", "Actions"
        ])
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        root.addWidget(self.table)

        self.refresh()

    def _add_user(self) -> None:
        dialog = AddUserDialog(self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.refresh()

    def _edit_permissions(self, user_id: int, username: str) -> None:
        dialog = EditPermissionsDialog(user_id, username, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            QMessageBox.information(self, "Saved", f"Permissions updated for '{username}'.")
            self.refresh()

    def _toggle_active(self, user_id: int, currently_active: bool) -> None:
        action = "deactivate" if currently_active else "reactivate"
        confirm = QMessageBox.question(
            self, f"Confirm {action.title()}",
            f"Are you sure you want to {action} this user?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return
        try:
            if currently_active:
                user_service.deactivate_user(user_id)
            else:
                user_service.reactivate_user(user_id)
        except ApplicationError as exc:
            QMessageBox.critical(self, "Action failed", str(exc))
            return
        self.refresh()

    def _reset_password(self, user_id: int) -> None:
        new_password, ok = QInputDialog.getText(
            self, "Reset Password",
            "New password (leave blank to auto-generate):"
        )
        if not ok:
            return
        try:
            generated = user_service.reset_password(user_id, new_password=new_password or None)
        except ApplicationError as exc:
            QMessageBox.critical(self, "Reset failed", str(exc))
            return
        QMessageBox.information(
            self, "Password reset",
            f"New password: {generated}\n\nShare this with the user securely."
        )

    def refresh(self) -> None:
        try:
            users = user_service.list_users()
        except ApplicationError as exc:
            QMessageBox.warning(self, "Cannot load users", str(exc))
            return

        self.table.setRowCount(0)
        for user in users:
            row = self.table.rowCount()
            self.table.insertRow(row)
            self.table.setItem(row, 0, QTableWidgetItem(str(user.id)))
            self.table.setItem(row, 1, QTableWidgetItem(user.username))
            self.table.setItem(row, 2, QTableWidgetItem(user.full_name or ""))

            role_item = QTableWidgetItem("Administrator" if user.is_admin else "User")
            role_item.setForeground(
                Qt.GlobalColor.darkBlue if user.is_admin else Qt.GlobalColor.black
            )
            self.table.setItem(row, 3, role_item)

            status_item = QTableWidgetItem("✔ Active" if user.is_active else "✘ Inactive")
            status_item.setForeground(
                Qt.GlobalColor.darkGreen if user.is_active else Qt.GlobalColor.red
            )
            self.table.setItem(row, 4, status_item)

            # Actions
            actions = QWidget()
            al = QHBoxLayout(actions)
            al.setContentsMargins(2, 2, 2, 2)
            al.setSpacing(4)

            # Edit Permissions button — only for non-admin users
            if not user.is_admin:
                perm_btn = QPushButton("Edit Permissions")
                perm_btn.setStyleSheet("padding: 3px 8px; background-color: #2980b9; color: white;")
                perm_btn.clicked.connect(
                    lambda _, uid=user.id, uname=user.username: self._edit_permissions(uid, uname)
                )
                al.addWidget(perm_btn)

            toggle_btn = QPushButton("Deactivate" if user.is_active else "Reactivate")
            toggle_btn.setStyleSheet(
                "padding: 3px 8px; background-color: #e74c3c; color: white;"
                if user.is_active else
                "padding: 3px 8px; background-color: #27ae60; color: white;"
            )
            toggle_btn.clicked.connect(
                lambda _, uid=user.id, active=user.is_active: self._toggle_active(uid, active)
            )

            reset_btn = QPushButton("Reset Password")
            reset_btn.setStyleSheet("padding: 3px 8px;")
            reset_btn.clicked.connect(lambda _, uid=user.id: self._reset_password(uid))

            al.addWidget(toggle_btn)
            al.addWidget(reset_btn)
            self.table.setCellWidget(row, 5, actions)

        self.table.resizeColumnsToContents()
