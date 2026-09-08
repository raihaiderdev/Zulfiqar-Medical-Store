"""
Settings page (Phase 1 §33, §31). Admin-only pharmacy info fields plus
working Backup and Restore buttons.
"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import (
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from app.config.settings import BACKUP_DIR
from app.services import backup_service, settings_service
from app.utils.exceptions import ApplicationError


class SettingsPage(QWidget):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        root = QVBoxLayout(self)

        header = QLabel("Settings")
        header.setStyleSheet("font-size: 18px; font-weight: 600;")
        root.addWidget(header)

        form = QFormLayout()
        self.name_edit = QLineEdit()
        self.address_edit = QLineEdit()
        self.phone_edit = QLineEdit()
        form.addRow("Pharmacy Name", self.name_edit)
        form.addRow("Address", self.address_edit)
        form.addRow("Phone", self.phone_edit)
        root.addLayout(form)

        save_button = QPushButton("Save Settings")
        save_button.clicked.connect(self._save)
        root.addWidget(save_button)

        root.addWidget(QLabel(""))  # spacer
        backup_row = QHBoxLayout()
        backup_button = QPushButton("Backup Database Now")
        backup_button.clicked.connect(self._backup)
        restore_button = QPushButton("Restore From Backup…")
        restore_button.clicked.connect(self._restore)
        backup_row.addWidget(backup_button)
        backup_row.addWidget(restore_button)
        root.addLayout(backup_row)

        root.addStretch()
        self.refresh()

    def refresh(self) -> None:
        self.name_edit.setText(settings_service.get_setting("pharmacy.name", default="") or "")
        self.address_edit.setText(settings_service.get_setting("pharmacy.address", default="") or "")
        self.phone_edit.setText(settings_service.get_setting("pharmacy.phone", default="") or "")

    def _save(self) -> None:
        try:
            settings_service.set_setting("pharmacy.name", self.name_edit.text().strip())
            settings_service.set_setting("pharmacy.address", self.address_edit.text().strip())
            settings_service.set_setting("pharmacy.phone", self.phone_edit.text().strip())
        except ApplicationError as exc:
            QMessageBox.critical(self, "Could not save settings", str(exc))
            return
        QMessageBox.information(self, "Saved", "Settings updated.")

    def _backup(self) -> None:
        try:
            path = backup_service.create_backup(destination_dir=BACKUP_DIR)
        except ApplicationError as exc:
            QMessageBox.critical(self, "Backup failed", str(exc))
            return
        QMessageBox.information(self, "Backup created", f"Saved to:\n{path}")

    def _restore(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Select Backup File", str(BACKUP_DIR), "SQLite DB (*.db)")
        if not path:
            return
        confirm = QMessageBox.warning(
            self, "Confirm restore",
            "Restoring will replace the current database with the selected backup.\n"
            "A safety backup of the current database will be made first.\n\nContinue?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return
        try:
            safety_backup = backup_service.restore_backup(Path(path))
        except ApplicationError as exc:
            QMessageBox.critical(self, "Restore failed", str(exc))
            return
        QMessageBox.information(
            self, "Restore complete",
            f"Database restored from:\n{path}\n\nA safety backup of the previous database was saved to:\n{safety_backup}",
        )
