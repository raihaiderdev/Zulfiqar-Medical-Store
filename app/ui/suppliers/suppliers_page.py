"""
Suppliers page — full CRUD: Add, Edit, Deactivate/Reactivate.
"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.services import party_service
from app.utils.exceptions import ApplicationError


# ---------------------------------------------------------------------------
# Add Supplier dialog
# ---------------------------------------------------------------------------
class AddSupplierDialog(QDialog):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Add Supplier")
        layout = QFormLayout(self)

        self.name_edit = QLineEdit()
        self.company_edit = QLineEdit()
        self.phone_edit = QLineEdit()
        self.email_edit = QLineEdit()
        self.address_edit = QLineEdit()
        self.tax_reg_edit = QLineEdit()
        self.notes_edit = QLineEdit()

        layout.addRow("Name *", self.name_edit)
        layout.addRow("Company", self.company_edit)
        layout.addRow("Phone", self.phone_edit)
        layout.addRow("Email", self.email_edit)
        layout.addRow("Address", self.address_edit)
        layout.addRow("Tax Reg. Number", self.tax_reg_edit)
        layout.addRow("Notes", self.notes_edit)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._save)
        buttons.rejected.connect(self.reject)
        layout.addRow(buttons)

    def _save(self) -> None:
        if not self.name_edit.text().strip():
            QMessageBox.warning(self, "Missing field", "Supplier name is required.")
            return
        try:
            party_service.add_supplier(
                self.name_edit.text().strip(),
                company=self.company_edit.text().strip() or None,
                phone=self.phone_edit.text().strip() or None,
                email=self.email_edit.text().strip() or None,
                address=self.address_edit.text().strip() or None,
                tax_registration_number=self.tax_reg_edit.text().strip() or None,
                notes=self.notes_edit.text().strip() or None,
            )
        except ApplicationError as exc:
            QMessageBox.critical(self, "Could not add supplier", str(exc))
            return
        self.accept()


# ---------------------------------------------------------------------------
# Edit Supplier dialog
# ---------------------------------------------------------------------------
class EditSupplierDialog(QDialog):
    def __init__(self, supplier_id: int, parent=None) -> None:
        super().__init__(parent)
        self._supplier_id = supplier_id
        self.setWindowTitle("Edit Supplier")
        layout = QFormLayout(self)

        # Load current values — use list_all_suppliers so inactive suppliers
        # can also be edited (list_suppliers only returns active ones).
        try:
            suppliers = party_service.list_all_suppliers()
            sup = next((s for s in suppliers if s.id == supplier_id), None)
        except ApplicationError:
            sup = None

        self.name_edit = QLineEdit(sup.name if sup else "")
        self.company_edit = QLineEdit(sup.company or "" if sup else "")
        self.phone_edit = QLineEdit(sup.phone or "" if sup else "")
        self.email_edit = QLineEdit(sup.email or "" if sup else "")
        self.address_edit = QLineEdit(sup.address or "" if sup else "")
        self.tax_reg_edit = QLineEdit(sup.tax_registration_number or "" if sup else "")
        self.notes_edit = QLineEdit(sup.notes or "" if sup else "")

        layout.addRow("Name *", self.name_edit)
        layout.addRow("Company", self.company_edit)
        layout.addRow("Phone", self.phone_edit)
        layout.addRow("Email", self.email_edit)
        layout.addRow("Address", self.address_edit)
        layout.addRow("Tax Reg. Number", self.tax_reg_edit)
        layout.addRow("Notes", self.notes_edit)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._save)
        buttons.rejected.connect(self.reject)
        layout.addRow(buttons)

    def _save(self) -> None:
        if not self.name_edit.text().strip():
            QMessageBox.warning(self, "Missing field", "Supplier name is required.")
            return
        try:
            party_service.edit_supplier(
                self._supplier_id,
                name=self.name_edit.text().strip(),
                company=self.company_edit.text().strip() or None,
                phone=self.phone_edit.text().strip() or None,
                email=self.email_edit.text().strip() or None,
                address=self.address_edit.text().strip() or None,
                tax_registration_number=self.tax_reg_edit.text().strip() or None,
                notes=self.notes_edit.text().strip() or None,
            )
        except ApplicationError as exc:
            QMessageBox.critical(self, "Could not save changes", str(exc))
            return
        self.accept()


# ---------------------------------------------------------------------------
# Suppliers page
# ---------------------------------------------------------------------------
class SuppliersPage(QWidget):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        root = QVBoxLayout(self)

        top_row = QHBoxLayout()
        header = QLabel("Suppliers")
        header.setStyleSheet("font-size: 18px; font-weight: 600;")
        top_row.addWidget(header)
        top_row.addStretch()
        add_button = QPushButton("＋ Add Supplier")
        add_button.setStyleSheet("background-color: #27ae60; color: white; padding: 6px 14px; font-weight: 600;")
        add_button.clicked.connect(self._add_supplier)
        top_row.addWidget(add_button)
        root.addLayout(top_row)

        # Table: ID, Name, Company, Phone, Email, Address, Active, Actions
        self.table = QTableWidget(0, 8)
        self.table.setHorizontalHeaderLabels([
            "ID", "Name", "Company", "Phone", "Email", "Address", "Active", "Actions"
        ])
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        root.addWidget(self.table)

        self.refresh()

    def _add_supplier(self) -> None:
        dialog = AddSupplierDialog(self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.refresh()

    def _edit_supplier(self, supplier_id: int) -> None:
        dialog = EditSupplierDialog(supplier_id, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.refresh()

    def _toggle_active(self, supplier_id: int, currently_active: bool) -> None:
        action = "deactivate" if currently_active else "reactivate"
        confirm = QMessageBox.question(
            self, f"Confirm {action.title()}",
            f"Are you sure you want to {action} this supplier?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return
        try:
            if currently_active:
                party_service.deactivate_supplier(supplier_id)
            else:
                party_service.reactivate_supplier(supplier_id)
        except ApplicationError as exc:
            QMessageBox.critical(self, "Action failed", str(exc))
            return
        self.refresh()

    def refresh(self) -> None:
        try:
            suppliers = party_service.list_all_suppliers()
        except ApplicationError as exc:
            QMessageBox.warning(self, "Cannot load suppliers", str(exc))
            return

        self.table.setRowCount(0)
        for s in suppliers:
            row = self.table.rowCount()
            self.table.insertRow(row)
            self.table.setItem(row, 0, QTableWidgetItem(str(s.id)))
            self.table.setItem(row, 1, QTableWidgetItem(s.name))
            self.table.setItem(row, 2, QTableWidgetItem(s.company or ""))
            self.table.setItem(row, 3, QTableWidgetItem(s.phone or ""))
            self.table.setItem(row, 4, QTableWidgetItem(s.email or ""))
            self.table.setItem(row, 5, QTableWidgetItem(s.address or ""))

            active_item = QTableWidgetItem("✔ Active" if s.is_active else "✘ Inactive")
            active_item.setForeground(
                Qt.GlobalColor.darkGreen if s.is_active else Qt.GlobalColor.red
            )
            self.table.setItem(row, 6, active_item)

            actions = QWidget()
            al = QHBoxLayout(actions)
            al.setContentsMargins(2, 2, 2, 2)
            al.setSpacing(4)

            edit_btn = QPushButton("Edit")
            edit_btn.setStyleSheet("padding: 3px 8px;")
            edit_btn.clicked.connect(lambda _, sid=s.id: self._edit_supplier(sid))

            toggle_btn = QPushButton("Deactivate" if s.is_active else "Reactivate")
            toggle_btn.setStyleSheet(
                "padding: 3px 8px; background-color: #e74c3c; color: white;"
                if s.is_active else
                "padding: 3px 8px; background-color: #27ae60; color: white;"
            )
            toggle_btn.clicked.connect(
                lambda _, sid=s.id, active=s.is_active: self._toggle_active(sid, active)
            )

            al.addWidget(edit_btn)
            al.addWidget(toggle_btn)
            self.table.setCellWidget(row, 7, actions)

        self.table.resizeColumnsToContents()
