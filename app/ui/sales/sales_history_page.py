"""
Sales History page — view all sales with date filter, per-sale detail,
Edit Invoice, and Return Medicine.
"""
from __future__ import annotations

from datetime import date

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QDateEdit,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.config.settings import settings
from app.security.session_context import current_session
from app.services import returns_service, sales_service
from app.utils.exceptions import ApplicationError


# ─────────────────────────────────────────────────────────────────────────────
# Sale Detail dialog
# ─────────────────────────────────────────────────────────────────────────────
class SaleDetailDialog(QDialog):
    def __init__(self, sale_id: int, invoice_number: str, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle(f"Invoice Detail — {invoice_number}")
        self.resize(700, 500)
        layout = QVBoxLayout(self)

        try:
            detail = sales_service.get_sale_detail(sale_id)
        except ApplicationError as exc:
            layout.addWidget(QLabel(f"Error loading sale: {exc}"))
            close_btn = QPushButton("Close")
            close_btn.clicked.connect(self.accept)
            layout.addWidget(close_btn)
            return

        cur = settings.currency
        summary_row = QHBoxLayout()

        def _info(label: str, value: str) -> QVBoxLayout:
            col = QVBoxLayout()
            lbl = QLabel(label)
            lbl.setStyleSheet("font-size: 11px; color: #666;")
            val = QLabel(value)
            val.setStyleSheet("font-weight: 600; font-size: 13px;")
            col.addWidget(lbl)
            col.addWidget(val)
            return col

        summary_row.addLayout(_info("Invoice #",  detail["invoice_number"]))
        summary_row.addLayout(_info("Date",        detail["date"]))
        summary_row.addLayout(_info("Status",      detail["status"]))
        summary_row.addLayout(_info("Subtotal",    f"{cur} {detail['subtotal']:.2f}"))
        summary_row.addLayout(_info("Discount",    f"{cur} {detail['discount_total']:.2f}"))
        summary_row.addLayout(_info("Total",       f"{cur} {detail['total']:.2f}"))
        summary_row.addLayout(_info("Paid",        f"{cur} {detail['amount_paid']:.2f}"))
        summary_row.addLayout(_info("Change Due",  f"{cur} {detail['change_due']:.2f}"))
        layout.addLayout(summary_row)

        div = QWidget(); div.setFixedHeight(1); div.setStyleSheet("background:#ddd;")
        layout.addWidget(div)

        items_label = QLabel("Line Items")
        items_label.setStyleSheet("font-weight: 600; margin-top: 8px;")
        layout.addWidget(items_label)

        table = QTableWidget(0, 7)
        table.setHorizontalHeaderLabels([
            "Medicine", "Batch", "Qty", "Unit Price", "Unit Cost", "Discount", "Line Total"
        ])
        table.horizontalHeader().setStretchLastSection(True)
        table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        table.setAlternatingRowColors(True)
        layout.addWidget(table)

        for item in detail["items"]:
            row = table.rowCount(); table.insertRow(row)
            table.setItem(row, 0, QTableWidgetItem(item["medicine_name"]))
            table.setItem(row, 1, QTableWidgetItem(item["batch_number"]))
            table.setItem(row, 2, QTableWidgetItem(str(item["quantity"])))
            table.setItem(row, 3, QTableWidgetItem(f"{item['unit_price']:.2f}"))
            table.setItem(row, 4, QTableWidgetItem(f"{item['unit_cost']:.2f}"))
            table.setItem(row, 5, QTableWidgetItem(f"{item['line_discount']:.2f}"))
            table.setItem(row, 6, QTableWidgetItem(f"{item['line_total']:.2f}"))
        table.resizeColumnsToContents()

        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.accept)
        layout.addWidget(close_btn)


# ─────────────────────────────────────────────────────────────────────────────
# Return Medicine dialog
# ─────────────────────────────────────────────────────────────────────────────
class ReturnMedicineDialog(QDialog):
    """
    Let an authorised user return one or more items from a completed sale.

    For each returnable line the user sees:
      Medicine | Batch | Sold Qty | Already Returned | Max Returnable | Return Qty spin

    They also choose:
      • Restock (default ON)  — units go back to shelf
      • Damaged (restock OFF) — units are written off as DAMAGED

    A mandatory reason field is required.

    After saving:
      • Stock is updated immediately.
      • Sale status changes to PARTIALLY_REFUNDED or REFUNDED.
      • Sale total is reduced by the returned value.
      • Dashboard and Reports automatically reflect the change on next refresh.
    """

    def __init__(self, sale_id: int, invoice_number: str, parent=None) -> None:
        super().__init__(parent)
        self._sale_id = sale_id
        self.setWindowTitle(f"Return Medicine — Invoice {invoice_number}")
        self.setMinimumSize(760, 520)
        layout = QVBoxLayout(self)

        # ── Info banner ────────────────────────────────────────────────────
        info = QLabel(
            f"<b>Invoice: {invoice_number}</b><br>"
            "Select the quantity to return for each medicine. "
            "Set quantity to <b>0</b> to skip a line."
        )
        info.setTextFormat(Qt.TextFormat.RichText)
        info.setWordWrap(True)
        info.setStyleSheet(
            "background: #eaf4fb; padding: 8px; border-radius: 5px; "
            "border: 1px solid #aed6f1; font-size: 12px;"
        )
        layout.addWidget(info)

        # ── Line items table with qty spinners ─────────────────────────────
        self._items_table = QTableWidget(0, 6)
        self._items_table.setHorizontalHeaderLabels([
            "Medicine", "Batch", "Sold", "Already Returned", "Max Returnable", "Return Qty"
        ])
        self._items_table.horizontalHeader().setStretchLastSection(False)
        self._items_table.horizontalHeader().setSectionResizeMode(
            0, self._items_table.horizontalHeader().ResizeMode.Stretch
        )
        self._items_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._items_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._items_table.setAlternatingRowColors(True)
        self._items_table.setMinimumHeight(200)
        layout.addWidget(self._items_table)

        self._qty_spins: list[QSpinBox] = []
        self._returnable_items: list[dict] = []

        # Load returnable items
        try:
            items = returns_service.get_sale_returnable_items(sale_id)
        except ApplicationError as exc:
            layout.addWidget(QLabel(f"Error loading items: {exc}"))
            close_btn = QPushButton("Close")
            close_btn.clicked.connect(self.reject)
            layout.addWidget(close_btn)
            return

        if not items:
            no_items_lbl = QLabel(
                "All items on this invoice have already been returned."
            )
            no_items_lbl.setStyleSheet("color: #888; font-size: 13px; padding: 8px;")
            layout.addWidget(no_items_lbl)
            close_btn = QPushButton("Close")
            close_btn.clicked.connect(self.reject)
            layout.addWidget(close_btn)
            return

        self._returnable_items = items
        cur = settings.currency

        for item in items:
            row = self._items_table.rowCount()
            self._items_table.insertRow(row)
            self._items_table.setItem(row, 0, QTableWidgetItem(item["medicine_name"]))
            self._items_table.setItem(row, 1, QTableWidgetItem(item["batch_number"]))
            self._items_table.setItem(row, 2, QTableWidgetItem(str(item["sold_quantity"])))
            self._items_table.setItem(row, 3, QTableWidgetItem(str(item["already_returned"])))

            max_item = QTableWidgetItem(str(item["returnable"]))
            max_item.setForeground(Qt.GlobalColor.darkGreen)
            self._items_table.setItem(row, 4, max_item)

            # Return qty spinner
            spin = QSpinBox()
            spin.setRange(0, item["returnable"])
            spin.setValue(0)
            spin.setMinimumHeight(28)
            spin_cell = QWidget()
            sc_layout = QHBoxLayout(spin_cell)
            sc_layout.setContentsMargins(4, 2, 4, 2)
            sc_layout.addWidget(spin)
            self._items_table.setCellWidget(row, 5, spin_cell)
            self._qty_spins.append(spin)

        self._items_table.resizeColumnsToContents()

        # ── Options ────────────────────────────────────────────────────────
        options_group = QGroupBox("Return Options")
        og = QFormLayout(options_group)

        self._restock_checkbox = QCheckBox("Return to stock (medicine goes back to shelf)")
        self._restock_checkbox.setChecked(True)
        og.addRow(self._restock_checkbox)

        damaged_note = QLabel(
            "Uncheck above if the medicine is damaged / expired / unsellable — "
            "it will be written off as DAMAGED (removed from inventory)."
        )
        damaged_note.setWordWrap(True)
        damaged_note.setStyleSheet("color: #888; font-size: 11px;")
        og.addRow(damaged_note)

        layout.addWidget(options_group)

        # ── Reason ─────────────────────────────────────────────────────────
        reason_row = QHBoxLayout()
        reason_lbl = QLabel("Reason *:")
        reason_lbl.setStyleSheet("font-weight: 600;")
        reason_row.addWidget(reason_lbl)
        self._reason_edit = QLineEdit()
        self._reason_edit.setPlaceholderText(
            "Required — e.g. 'Wrong medicine dispensed' or 'Customer refused'"
        )
        self._reason_edit.setMinimumHeight(32)
        reason_row.addWidget(self._reason_edit, 1)
        layout.addLayout(reason_row)

        # ── Buttons ────────────────────────────────────────────────────────
        btn_row = QHBoxLayout()
        cancel_btn = QPushButton("Cancel")
        cancel_btn.setStyleSheet("padding: 7px 18px;")
        cancel_btn.clicked.connect(self.reject)

        self._save_btn = QPushButton("✔  Process Return")
        self._save_btn.setStyleSheet(
            "background-color: #e67e22; color: white; font-weight: 700; "
            "font-size: 13px; padding: 7px 22px; border-radius: 4px;"
        )
        self._save_btn.clicked.connect(self._save)

        btn_row.addStretch()
        btn_row.addWidget(cancel_btn)
        btn_row.addWidget(self._save_btn)
        layout.addLayout(btn_row)

    def _save(self) -> None:
        reason = self._reason_edit.text().strip()
        if not reason:
            QMessageBox.warning(self, "Reason required",
                                "Please enter a reason for this return.")
            return

        lines = []
        for i, item in enumerate(self._returnable_items):
            qty = self._qty_spins[i].value()
            if qty > 0:
                lines.append({"sale_item_id": item["sale_item_id"], "quantity": qty})

        if not lines:
            QMessageBox.warning(self, "Nothing to return",
                                "Set a return quantity greater than 0 for at least one item.")
            return

        # Confirm
        total_units = sum(l["quantity"] for l in lines)
        confirm = QMessageBox.question(
            self, "Confirm Return",
            f"Return {total_units} unit(s) from this invoice?\n\n"
            f"Reason: {reason}\n"
            f"Restock: {'Yes — back to shelf' if self._restock_checkbox.isChecked() else 'No — damaged/write-off'}\n\n"
            "The sale total and status will be updated automatically.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return

        try:
            returns_service.process_sale_return(
                sale_id=self._sale_id,
                lines=lines,
                reason=reason,
                restock=self._restock_checkbox.isChecked(),
            )
        except ApplicationError as exc:
            QMessageBox.critical(self, "Return failed", str(exc))
            return

        cur = settings.currency
        QMessageBox.information(
            self, "✔  Return Processed",
            f"Return processed successfully.\n\n"
            f"Units returned: {total_units}\n"
            f"{'Stock has been restored.' if self._restock_checkbox.isChecked() else 'Units written off as DAMAGED.'}\n\n"
            "The sale status and totals have been updated.\n"
            "The dashboard will reflect the change on next refresh."
        )
        self.accept()


# ─────────────────────────────────────────────────────────────────────────────
# Sales History page
# ─────────────────────────────────────────────────────────────────────────────
class SalesHistoryPage(QWidget):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        root = QVBoxLayout(self)

        # ── Header ─────────────────────────────────────────────────────────
        header_row = QHBoxLayout()
        header = QLabel("Sales History")
        header.setStyleSheet("font-size: 18px; font-weight: 600;")
        header_row.addWidget(header)
        header_row.addStretch()
        self.total_label = QLabel("Total: Rs 0.00")
        self.total_label.setStyleSheet("font-weight: 600; font-size: 13px;")
        header_row.addWidget(self.total_label)
        root.addLayout(header_row)

        # ── Date filter ────────────────────────────────────────────────────
        filter_row = QHBoxLayout()
        filter_row.addWidget(QLabel("From:"))
        self.from_date = QDateEdit(calendarPopup=True)
        self.from_date.setDate(date.today().replace(day=1))
        filter_row.addWidget(self.from_date)
        filter_row.addWidget(QLabel("To:"))
        self.to_date = QDateEdit(calendarPopup=True)
        self.to_date.setDate(date.today())
        filter_row.addWidget(self.to_date)
        search_btn = QPushButton("Search")
        search_btn.clicked.connect(self.refresh)
        filter_row.addWidget(search_btn)
        filter_row.addStretch()
        root.addLayout(filter_row)

        # ── Permission flags ───────────────────────────────────────────────
        self._can_edit   = current_session.has_permission("sales.edit_invoice")
        self._can_return = current_session.has_permission("returns.process")

        # ── Columns: Invoice#, Date, Total, Paid, Change, Status, View,
        #              [Return], [Edit]
        # ──────────────────────────────────────────────────────────────────
        col_count = 7
        headers = ["Invoice #", "Date", f"Total ({settings.currency})",
                   f"Paid ({settings.currency})", f"Change ({settings.currency})",
                   "Status", "View"]
        if self._can_return:
            col_count += 1
            headers.append("Return")
        if self._can_edit:
            col_count += 1
            headers.append("Edit")

        self._col_return = 7 if self._can_return else None
        self._col_edit   = (8 if self._can_return else 7) if self._can_edit else None

        self.table = QTableWidget(0, col_count)
        self.table.setHorizontalHeaderLabels(headers)
        self.table.horizontalHeader().setStretchLastSection(False)
        self.table.horizontalHeader().setSectionResizeMode(
            0, self.table.horizontalHeader().ResizeMode.Stretch
        )
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setAlternatingRowColors(True)
        root.addWidget(self.table)

        self.refresh()

    # ── Refresh ───────────────────────────────────────────────────────────

    def refresh(self) -> None:
        fd = self.from_date.date()
        td = self.to_date.date()
        date_from = date(fd.year(), fd.month(), fd.day())
        date_to   = date(td.year(), td.month(), td.day())

        try:
            sales = sales_service.list_sales(date_from=date_from, date_to=date_to)
        except ApplicationError as exc:
            QMessageBox.warning(self, "Cannot load sales", str(exc))
            return

        self.table.setRowCount(0)
        grand_total = 0.0
        cur = settings.currency

        STATUS_COLOURS = {
            "COMPLETED":          Qt.GlobalColor.darkGreen,
            "CANCELLED":          Qt.GlobalColor.red,
            "REFUNDED":           Qt.GlobalColor.darkMagenta,
            "PARTIALLY_REFUNDED": Qt.GlobalColor.darkYellow,
        }

        for s in sales:
            row = self.table.rowCount()
            self.table.insertRow(row)

            self.table.setItem(row, 0, QTableWidgetItem(s["invoice_number"]))
            self.table.setItem(row, 1, QTableWidgetItem(s["date"]))

            for col_idx, key in enumerate(["total", "amount_paid", "change_due"], start=2):
                it = QTableWidgetItem(f"{s[key]:.2f}")
                it.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                self.table.setItem(row, col_idx, it)

            status = s["status"]
            st_item = QTableWidgetItem(status)
            st_item.setForeground(STATUS_COLOURS.get(status, Qt.GlobalColor.black))
            self.table.setItem(row, 5, st_item)

            # col 6 — View
            view_btn = QPushButton("View Details")
            view_btn.setStyleSheet("padding: 3px 10px;")
            view_btn.clicked.connect(
                lambda _, sid=s["sale_id"], inv=s["invoice_number"]:
                    self._view_detail(sid, inv)
            )
            self._set_btn_cell(row, 6, view_btn)

            # col 7 — Return (if permitted)
            if self._can_return and self._col_return is not None:
                # Only allow return if status is COMPLETED or PARTIALLY_REFUNDED
                can_ret = status in ("COMPLETED", "PARTIALLY_REFUNDED")
                ret_btn = QPushButton("↩  Return")
                ret_btn.setStyleSheet(
                    "padding: 3px 10px; background-color: #e67e22; color: white; font-weight: 600;"
                    if can_ret else
                    "padding: 3px 10px; color: #aaa; background: #f5f5f5;"
                )
                ret_btn.setEnabled(can_ret)
                ret_btn.setToolTip(
                    "Process a return for this invoice"
                    if can_ret else "Already fully refunded or cancelled"
                )
                ret_btn.clicked.connect(
                    lambda _, sid=s["sale_id"], inv=s["invoice_number"]:
                        self._return_medicine(sid, inv)
                )
                self._set_btn_cell(row, self._col_return, ret_btn)

            # col 7/8 — Edit
            if self._can_edit and self._col_edit is not None:
                edit_btn = QPushButton("✏  Edit")
                edit_btn.setStyleSheet(
                    "padding: 3px 10px; background-color: #2980b9; "
                    "color: white; font-weight: 600;"
                )
                edit_btn.clicked.connect(
                    lambda _, sid=s["sale_id"]: self._edit_invoice(sid)
                )
                self._set_btn_cell(row, self._col_edit, edit_btn)

            grand_total += s["total"]

        self.total_label.setText(f"Total: {cur} {grand_total:,.2f}")
        self.table.resizeColumnsToContents()

    # ── Helpers ───────────────────────────────────────────────────────────

    def _set_btn_cell(self, row: int, col: int, btn: QPushButton) -> None:
        cell = QWidget()
        cl = QHBoxLayout(cell)
        cl.setContentsMargins(3, 2, 3, 2)
        cl.addWidget(btn)
        self.table.setCellWidget(row, col, cell)

    def _view_detail(self, sale_id: int, invoice_number: str) -> None:
        SaleDetailDialog(sale_id, invoice_number, self).exec()

    def _return_medicine(self, sale_id: int, invoice_number: str) -> None:
        dlg = ReturnMedicineDialog(sale_id, invoice_number, self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self.refresh()

    def _edit_invoice(self, sale_id: int) -> None:
        from app.ui.sales.edit_invoice_dialog import EditInvoiceDialog
        dlg = EditInvoiceDialog(self, initial_sale_id=sale_id)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self.refresh()
