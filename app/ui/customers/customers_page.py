"""
Customers page — full CRUD: Add, Edit, Deactivate/Reactivate, View History.
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
# Add Customer dialog
# ---------------------------------------------------------------------------
class AddCustomerDialog(QDialog):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Add Customer")
        layout = QFormLayout(self)

        self.name_edit = QLineEdit()
        self.phone_edit = QLineEdit()
        self.address_edit = QLineEdit()
        self.email_edit = QLineEdit()
        self.notes_edit = QLineEdit()

        layout.addRow("Name *", self.name_edit)
        layout.addRow("Phone", self.phone_edit)
        layout.addRow("Address", self.address_edit)
        layout.addRow("Email", self.email_edit)
        layout.addRow("Notes", self.notes_edit)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._save)
        buttons.rejected.connect(self.reject)
        layout.addRow(buttons)

    def _save(self) -> None:
        if not self.name_edit.text().strip():
            QMessageBox.warning(self, "Missing field", "Customer name is required.")
            return
        try:
            party_service.add_customer(
                self.name_edit.text().strip(),
                phone=self.phone_edit.text().strip() or None,
                address=self.address_edit.text().strip() or None,
                email=self.email_edit.text().strip() or None,
                notes=self.notes_edit.text().strip() or None,
            )
        except ApplicationError as exc:
            QMessageBox.critical(self, "Could not add customer", str(exc))
            return
        self.accept()


# ---------------------------------------------------------------------------
# Edit Customer dialog
# ---------------------------------------------------------------------------
class EditCustomerDialog(QDialog):
    def __init__(self, customer_id: int, parent=None) -> None:
        super().__init__(parent)
        self._customer_id = customer_id
        self.setWindowTitle("Edit Customer")
        layout = QFormLayout(self)

        try:
            customers = party_service.list_all_customers()
            cust = next((c for c in customers if c.id == customer_id), None)
        except ApplicationError:
            cust = None

        self.name_edit = QLineEdit(cust.name if cust else "")
        self.phone_edit = QLineEdit(cust.phone or "" if cust else "")
        self.address_edit = QLineEdit(cust.address or "" if cust else "")
        self.email_edit = QLineEdit(cust.email or "" if cust else "")
        self.notes_edit = QLineEdit(cust.notes or "" if cust else "")

        layout.addRow("Name *", self.name_edit)
        layout.addRow("Phone", self.phone_edit)
        layout.addRow("Address", self.address_edit)
        layout.addRow("Email", self.email_edit)
        layout.addRow("Notes", self.notes_edit)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._save)
        buttons.rejected.connect(self.reject)
        layout.addRow(buttons)

    def _save(self) -> None:
        if not self.name_edit.text().strip():
            QMessageBox.warning(self, "Missing field", "Customer name is required.")
            return
        try:
            party_service.edit_customer(
                self._customer_id,
                name=self.name_edit.text().strip(),
                phone=self.phone_edit.text().strip() or None,
                address=self.address_edit.text().strip() or None,
                email=self.email_edit.text().strip() or None,
                notes=self.notes_edit.text().strip() or None,
            )
        except ApplicationError as exc:
            QMessageBox.critical(self, "Could not save changes", str(exc))
            return
        self.accept()


# ---------------------------------------------------------------------------
# Customer History dialog
# ---------------------------------------------------------------------------
class CustomerHistoryDialog(QDialog):
    def __init__(self, customer_id: int, customer_name: str, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle(f"Purchase History — {customer_name}")
        self.resize(500, 360)
        layout = QVBoxLayout(self)

        table = QTableWidget(0, 3)
        table.setHorizontalHeaderLabels(["Date", "Invoice #", "Total"])
        table.horizontalHeader().setStretchLastSection(True)
        table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        layout.addWidget(table)

        try:
            history = party_service.customer_purchase_history(customer_id)
        except ApplicationError as exc:
            QMessageBox.warning(self, "Cannot load history", str(exc))
        else:
            for item in history:
                row = table.rowCount()
                table.insertRow(row)
                table.setItem(row, 0, QTableWidgetItem(item["date"]))
                table.setItem(row, 1, QTableWidgetItem(item["invoice_number"] or ""))
                table.setItem(row, 2, QTableWidgetItem(f"{item['total']:.2f}"))

        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.accept)
        layout.addWidget(close_btn)


# ---------------------------------------------------------------------------
# Customers page
# ---------------------------------------------------------------------------
class CustomersPage(QWidget):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        root = QVBoxLayout(self)

        top_row = QHBoxLayout()
        header = QLabel("Customers")
        header.setStyleSheet("font-size: 18px; font-weight: 600;")
        top_row.addWidget(header)
        top_row.addStretch()
        add_button = QPushButton("＋ Add Customer")
        add_button.setStyleSheet("background-color: #27ae60; color: white; padding: 6px 14px; font-weight: 600;")
        add_button.clicked.connect(self._add_customer)
        top_row.addWidget(add_button)
        root.addLayout(top_row)

        # Table: ID, Name, Phone, Email, Address, Active, Actions
        self.table = QTableWidget(0, 7)
        self.table.setHorizontalHeaderLabels([
            "ID", "Name", "Phone", "Email", "Address", "Active", "Actions"
        ])
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        root.addWidget(self.table)

        self.refresh()

    def _add_customer(self) -> None:
        dialog = AddCustomerDialog(self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.refresh()

    def _edit_customer(self, customer_id: int) -> None:
        dialog = EditCustomerDialog(customer_id, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.refresh()

    def _toggle_active(self, customer_id: int, currently_active: bool) -> None:
        action = "deactivate" if currently_active else "reactivate"
        confirm = QMessageBox.question(
            self, f"Confirm {action.title()}",
            f"Are you sure you want to {action} this customer?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return
        try:
            if currently_active:
                party_service.deactivate_customer(customer_id)
            else:
                party_service.reactivate_customer(customer_id)
        except ApplicationError as exc:
            QMessageBox.critical(self, "Action failed", str(exc))
            return
        self.refresh()

    def _view_history(self, customer_id: int, customer_name: str) -> None:
        dialog = CustomerHistoryDialog(customer_id, customer_name, self)
        dialog.exec()

    def refresh(self) -> None:
        try:
            customers = party_service.list_all_customers()
        except ApplicationError as exc:
            QMessageBox.warning(self, "Cannot load customers", str(exc))
            return

        self.table.setRowCount(0)
        for c in customers:
            row = self.table.rowCount()
            self.table.insertRow(row)
            self.table.setItem(row, 0, QTableWidgetItem(str(c.id)))
            self.table.setItem(row, 1, QTableWidgetItem(c.name))
            self.table.setItem(row, 2, QTableWidgetItem(c.phone or ""))
            self.table.setItem(row, 3, QTableWidgetItem(c.email or ""))
            self.table.setItem(row, 4, QTableWidgetItem(c.address or ""))

            active_item = QTableWidgetItem("✔ Active" if c.is_active else "✘ Inactive")
            active_item.setForeground(
                Qt.GlobalColor.darkGreen if c.is_active else Qt.GlobalColor.red
            )
            self.table.setItem(row, 5, active_item)

            actions = QWidget()
            al = QHBoxLayout(actions)
            al.setContentsMargins(2, 2, 2, 2)
            al.setSpacing(4)

            edit_btn = QPushButton("Edit")
            edit_btn.setStyleSheet("padding: 3px 8px;")
            edit_btn.clicked.connect(lambda _, cid=c.id: self._edit_customer(cid))

            history_btn = QPushButton("History")
            history_btn.setStyleSheet("padding: 3px 8px;")
            history_btn.clicked.connect(
                lambda _, cid=c.id, cname=c.name: self._view_history(cid, cname)
            )

            toggle_btn = QPushButton("Deactivate" if c.is_active else "Reactivate")
            toggle_btn.setStyleSheet(
                "padding: 3px 8px; background-color: #e74c3c; color: white;"
                if c.is_active else
                "padding: 3px 8px; background-color: #27ae60; color: white;"
            )
            toggle_btn.clicked.connect(
                lambda _, cid=c.id, active=c.is_active: self._toggle_active(cid, active)
            )

            al.addWidget(edit_btn)
            al.addWidget(history_btn)
            al.addWidget(toggle_btn)
            self.table.setCellWidget(row, 6, actions)

        self.table.resizeColumnsToContents()
