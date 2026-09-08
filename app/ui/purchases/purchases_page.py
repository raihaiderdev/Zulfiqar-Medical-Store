"""
Purchases page — record purchases + history with Mark as Paid action.
"""
from __future__ import annotations

from datetime import date, timedelta

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QDateEdit,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.services import medicine_service, party_service, purchase_service
from app.utils.exceptions import ApplicationError


class PurchasesPage(QWidget):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        root = QVBoxLayout(self)

        # Header
        header_row = QHBoxLayout()
        header = QLabel("Purchases")
        header.setStyleSheet("font-size: 18px; font-weight: 600;")
        header_row.addWidget(header)
        root.addLayout(header_row)

        # Splitter: form on left, history on right
        splitter = QSplitter(Qt.Orientation.Horizontal)
        root.addWidget(splitter, 1)

        # --- Left: New Purchase Form ---
        form_widget = QWidget()
        form_layout = QVBoxLayout(form_widget)
        form_layout.addWidget(QLabel("Record New Purchase"))

        form = QFormLayout()
        self.supplier_combo = QComboBox()
        self.medicine_combo = QComboBox()
        self.invoice_edit = QLineEdit()
        self.batch_number_edit = QLineEdit()
        self.quantity_spin = QSpinBox()
        self.quantity_spin.setRange(1, 1_000_000)
        self.purchase_price_edit = QLineEdit()
        self.selling_price_edit = QLineEdit()
        self.expiry_edit = QDateEdit(calendarPopup=True)
        self.expiry_edit.setDate(date.today() + timedelta(days=365))

        form.addRow("Supplier *", self.supplier_combo)
        form.addRow("Medicine *", self.medicine_combo)
        form.addRow("Supplier Invoice #", self.invoice_edit)
        form.addRow("Batch Number *", self.batch_number_edit)
        form.addRow("Quantity *", self.quantity_spin)
        form.addRow("Purchase Price *", self.purchase_price_edit)
        form.addRow("Selling Price *", self.selling_price_edit)
        form.addRow("Expiry Date *", self.expiry_edit)
        form_layout.addLayout(form)

        submit_button = QPushButton("✔ Record Purchase")
        submit_button.setStyleSheet("background-color: #27ae60; color: white; padding: 8px; font-weight: 600;")
        submit_button.clicked.connect(self._submit)
        form_layout.addWidget(submit_button)
        form_layout.addStretch()
        splitter.addWidget(form_widget)

        # --- Right: Purchase History ---
        history_widget = QWidget()
        history_layout = QVBoxLayout(history_widget)

        hist_header_row = QHBoxLayout()
        hist_header_row.addWidget(QLabel("Purchase History (selected supplier)"))
        hist_header_row.addStretch()
        refresh_btn = QPushButton("Refresh")
        refresh_btn.clicked.connect(self._refresh_history)
        hist_header_row.addWidget(refresh_btn)
        history_layout.addLayout(hist_header_row)

        # Table: Date, Invoice #, Total Cost, Status, Actions
        self.history_table = QTableWidget(0, 5)
        self.history_table.setHorizontalHeaderLabels([
            "Date", "Invoice #", "Total Cost (Rs)", "Status", "Actions"
        ])
        self.history_table.horizontalHeader().setStretchLastSection(True)
        self.history_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.history_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        history_layout.addWidget(self.history_table)
        splitter.addWidget(history_widget)
        splitter.setSizes([380, 580])

        self.supplier_combo.currentIndexChanged.connect(self._refresh_history)
        self._reload_dropdowns()

    def _reload_dropdowns(self) -> None:
        try:
            suppliers = party_service.list_suppliers()
            medicines = medicine_service.search_medicines("")
        except ApplicationError as exc:
            QMessageBox.warning(self, "Cannot load data", str(exc))
            return

        self.supplier_combo.clear()
        for s in suppliers:
            self.supplier_combo.addItem(s.name, s.id)

        self.medicine_combo.clear()
        for m in medicines:
            self.medicine_combo.addItem(m.name, m.id)

        self._refresh_history()

    def _refresh_history(self) -> None:
        supplier_id = self.supplier_combo.currentData()
        self.history_table.setRowCount(0)
        if supplier_id is None:
            return
        try:
            history = purchase_service.supplier_purchase_history(supplier_id)
        except ApplicationError as exc:
            QMessageBox.warning(self, "Cannot load history", str(exc))
            return

        for item in history:
            row = self.history_table.rowCount()
            self.history_table.insertRow(row)
            self.history_table.setItem(row, 0, QTableWidgetItem(item["date"]))
            self.history_table.setItem(row, 1, QTableWidgetItem(item["invoice_number"] or ""))
            self.history_table.setItem(row, 2, QTableWidgetItem(f"{item['total_cost']:.2f}"))

            status = item["payment_status"]
            status_item = QTableWidgetItem(status)
            if status == "PAID":
                status_item.setForeground(Qt.GlobalColor.darkGreen)
            elif status == "UNPAID":
                status_item.setForeground(Qt.GlobalColor.red)
            else:
                status_item.setForeground(Qt.GlobalColor.darkYellow)
            self.history_table.setItem(row, 3, status_item)

            # Actions cell
            actions = QWidget()
            al = QHBoxLayout(actions)
            al.setContentsMargins(2, 2, 2, 2)
            al.setSpacing(4)

            if status != "PAID":
                paid_btn = QPushButton("Mark as Paid")
                paid_btn.setStyleSheet("padding: 3px 8px; background-color: #2980b9; color: white;")
                paid_btn.clicked.connect(
                    lambda _, pid=item["purchase_id"]: self._mark_paid(pid)
                )
                al.addWidget(paid_btn)
            else:
                paid_label = QLabel("✔ Paid")
                paid_label.setStyleSheet("color: green; padding: 3px 8px;")
                al.addWidget(paid_label)

            self.history_table.setCellWidget(row, 4, actions)

        self.history_table.resizeColumnsToContents()

    def _mark_paid(self, purchase_id: int) -> None:
        confirm = QMessageBox.question(
            self, "Mark as Paid",
            "Mark this purchase as fully paid?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return
        try:
            purchase_service.mark_purchase_paid(purchase_id)
        except ApplicationError as exc:
            QMessageBox.critical(self, "Action failed", str(exc))
            return
        self._refresh_history()

    def _submit(self) -> None:
        supplier_id = self.supplier_combo.currentData()
        medicine_id = self.medicine_combo.currentData()
        if supplier_id is None or medicine_id is None:
            QMessageBox.warning(self, "Missing selection", "Add at least one supplier and medicine first.")
            return
        if not self.batch_number_edit.text().strip():
            QMessageBox.warning(self, "Missing field", "Batch number is required.")
            return
        try:
            purchase_price = float(self.purchase_price_edit.text())
            selling_price = float(self.selling_price_edit.text())
        except ValueError:
            QMessageBox.warning(self, "Invalid input", "Prices must be numeric.")
            return

        qt_date = self.expiry_edit.date()
        expiry = date(qt_date.year(), qt_date.month(), qt_date.day())

        try:
            purchase_service.record_purchase(
                supplier_id=supplier_id,
                supplier_invoice_number=self.invoice_edit.text().strip() or None,
                lines=[{
                    "medicine_id": medicine_id,
                    "batch_number": self.batch_number_edit.text().strip(),
                    "quantity": self.quantity_spin.value(),
                    "purchase_price": purchase_price,
                    "selling_price": selling_price,
                    "expiry_date": expiry,
                }],
            )
        except ApplicationError as exc:
            QMessageBox.critical(self, "Purchase failed", str(exc))
            return

        QMessageBox.information(self, "Purchase recorded", "Stock has been updated.")
        self.batch_number_edit.clear()
        self.purchase_price_edit.clear()
        self.selling_price_edit.clear()
        self._refresh_history()
