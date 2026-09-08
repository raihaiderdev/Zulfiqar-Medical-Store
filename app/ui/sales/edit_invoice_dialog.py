"""
Edit Invoice dialog (Feature 3).

Bugs fixed:
  • sale_item_id was missing from get_sale_detail() items — caused KeyError crash.
  • price_changed used lr.original_qty instead of comparing to original_price.
  • Price / discount were always included in changes even when unchanged.
  • Actions cell too narrow — split into two separate columns.
"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
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
from app.services import sales_service
from app.utils.exceptions import ApplicationError


class _EditLineRow:
    """Holds the editable widgets for one sale-item row."""

    def __init__(self, item: dict, table: QTableWidget, row: int) -> None:
        self.sale_item_id: int   = item["sale_item_id"]
        self.original_qty: int   = item["quantity"]
        self.original_price: float = item["unit_price"]
        self.original_disc: float  = item["line_discount"]

        table.setItem(row, 0, QTableWidgetItem(item["medicine_name"]))
        table.setItem(row, 1, QTableWidgetItem(item["batch_number"]))

        # col 2 — editable quantity (0 = remove line)
        self.qty_spin = QSpinBox()
        self.qty_spin.setRange(0, 1_000_000)
        self.qty_spin.setValue(item["quantity"])
        self.qty_spin.setToolTip("Set to 0 to remove this line from the invoice.")
        table.setCellWidget(row, 2, self.qty_spin)

        # col 3 — editable unit price
        self.price_edit = QLineEdit(f"{item['unit_price']:.2f}")
        self.price_edit.setToolTip("Unit price — leave as-is to keep original.")
        table.setCellWidget(row, 3, self.price_edit)

        # col 4 — editable line discount
        self.discount_edit = QLineEdit(f"{item['line_discount']:.2f}")
        self.discount_edit.setToolTip("Line discount — leave as-is to keep original.")
        table.setCellWidget(row, 4, self.discount_edit)

        # col 5 — original total (read-only)
        orig_item = QTableWidgetItem(f"{item['line_total']:.2f}")
        orig_item.setFlags(orig_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
        orig_item.setForeground(Qt.GlobalColor.darkGray)
        table.setItem(row, 5, orig_item)


class EditInvoiceDialog(QDialog):
    """
    Opens a completed invoice for correction.

    When opened from Sales History the invoice is pre-loaded.
    The search bar also allows looking up any invoice by number.
    """

    def __init__(self, parent=None, *, initial_sale_id: int | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Edit Invoice")
        self.setMinimumSize(940, 640)
        self._current_sale_id: int | None = None
        self._line_rows: list[_EditLineRow] = []

        layout = QVBoxLayout(self)

        # ── Search bar ─────────────────────────────────────────────────────
        search_group = QGroupBox("Find Invoice")
        sg_layout = QHBoxLayout(search_group)
        sg_layout.addWidget(QLabel("Invoice Number:"))
        self._search_edit = QLineEdit()
        self._search_edit.setPlaceholderText("e.g. INV-2026-000001")
        self._search_edit.returnPressed.connect(self._load_by_search)
        sg_layout.addWidget(self._search_edit, 1)
        load_btn = QPushButton("Load Invoice")
        load_btn.setStyleSheet(
            "background-color: #2980b9; color: white; padding: 6px 14px; font-weight: 600;"
        )
        load_btn.clicked.connect(self._load_by_search)
        sg_layout.addWidget(load_btn)
        layout.addWidget(search_group)

        # ── Read-only header summary ───────────────────────────────────────
        self._header_label = QLabel("No invoice loaded — enter an invoice number above or close this dialog and click Edit Invoice on a row.")
        self._header_label.setStyleSheet(
            "background: #eef2f7; padding: 8px; border-radius: 4px; "
            "font-size: 12px; color: #333;"
        )
        self._header_label.setWordWrap(True)
        layout.addWidget(self._header_label)

        # ── Line items table ───────────────────────────────────────────────
        table_label = QLabel("Line Items  (edit Qty / Price / Discount below, then Save)")
        table_label.setStyleSheet("font-weight: 600; font-size: 12px; margin-top: 4px;")
        layout.addWidget(table_label)

        self._table = QTableWidget(0, 6)
        self._table.setHorizontalHeaderLabels([
            "Medicine", "Batch",
            "Qty ✏", "Unit Price ✏", "Discount ✏",
            "Orig. Total"
        ])
        self._table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeMode.Stretch
        )
        for col in (1, 2, 3, 4, 5):
            self._table.horizontalHeader().setSectionResizeMode(
                col, QHeaderView.ResizeMode.ResizeToContents
            )
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._table.setMinimumHeight(200)
        self._table.setAlternatingRowColors(True)
        layout.addWidget(self._table)

        # ── Optional header overrides ──────────────────────────────────────
        override_group = QGroupBox("Header Overrides  (optional — leave blank to keep current values)")
        og_layout = QFormLayout(override_group)
        self._new_paid_edit = QLineEdit()
        self._new_paid_edit.setPlaceholderText("Leave blank to keep current")
        og_layout.addRow(f"Amount Paid ({settings.currency}):", self._new_paid_edit)
        self._new_notes_edit = QLineEdit()
        self._new_notes_edit.setPlaceholderText("Leave blank to keep current")
        og_layout.addRow("Notes:", self._new_notes_edit)
        layout.addWidget(override_group)

        # ── Reason (mandatory) ─────────────────────────────────────────────
        reason_row = QHBoxLayout()
        reason_lbl = QLabel("Reason for edit *")
        reason_lbl.setStyleSheet("font-weight: 600;")
        reason_row.addWidget(reason_lbl)
        self._reason_edit = QLineEdit()
        self._reason_edit.setPlaceholderText(
            "Required — describe what changed and why, e.g. 'Customer returned 2 units of Panadol'"
        )
        reason_row.addWidget(self._reason_edit, 1)
        layout.addLayout(reason_row)

        # ── Action buttons ─────────────────────────────────────────────────
        btn_row = QHBoxLayout()
        self._save_btn = QPushButton("✔  Save Changes")
        self._save_btn.setEnabled(False)
        self._save_btn.setStyleSheet(
            "background-color: #27ae60; color: white; "
            "padding: 8px 22px; font-weight: 700; font-size: 13px;"
        )
        self._save_btn.clicked.connect(self._save)

        cancel_btn = QPushButton("Cancel")
        cancel_btn.setStyleSheet("padding: 8px 18px;")
        cancel_btn.clicked.connect(self.reject)

        btn_row.addStretch()
        btn_row.addWidget(cancel_btn)
        btn_row.addWidget(self._save_btn)
        layout.addLayout(btn_row)

        # Pre-load if called directly from the history table
        if initial_sale_id is not None:
            self._load_invoice(initial_sale_id)

    # ── Load helpers ──────────────────────────────────────────────────────

    def _load_by_search(self) -> None:
        term = self._search_edit.text().strip()
        if not term:
            QMessageBox.information(
                self, "Enter invoice number",
                "Type an invoice number (e.g. INV-2026-000001) and click Load."
            )
            return
        try:
            all_sales = sales_service.list_sales(limit=10_000)
        except ApplicationError as exc:
            QMessageBox.warning(self, "Cannot search", str(exc))
            return

        term_upper = term.upper()
        matches = [s for s in all_sales if term_upper in s["invoice_number"].upper()]

        if not matches:
            QMessageBox.information(
                self, "Not found",
                f"No invoice containing '{term}' was found.\n"
                "Check the number and try again."
            )
            return

        # Exact match wins; otherwise use first partial match
        exact = [s for s in matches if s["invoice_number"].upper() == term_upper]
        best = (exact or matches)[0]
        self._load_invoice(best["sale_id"])

    def _load_invoice(self, sale_id: int) -> None:
        try:
            detail = sales_service.get_sale_detail(sale_id)
        except ApplicationError as exc:
            QMessageBox.critical(self, "Cannot load invoice", str(exc))
            return

        if detail["status"] not in ("COMPLETED", "PARTIALLY_REFUNDED"):
            QMessageBox.warning(
                self, "Cannot edit this invoice",
                f"Only COMPLETED invoices can be edited.\n"
                f"This invoice has status: {detail['status']}."
            )
            return

        # Verify sale_item_id is present (sanity check)
        for item in detail["items"]:
            if "sale_item_id" not in item:
                QMessageBox.critical(
                    self, "Data error",
                    "Invoice items are missing their ID. "
                    "Please restart the application and try again."
                )
                return

        self._current_sale_id = sale_id
        self._line_rows = []

        # Update the header summary strip
        cur = settings.currency
        self._header_label.setText(
            f"Invoice: <b>{detail['invoice_number']}</b>  |  "
            f"Date: {detail['date']}  |  "
            f"Status: {detail['status']}  |  "
            f"Subtotal: {cur} {detail['subtotal']:.2f}  |  "
            f"Discount: {cur} {detail['discount_total']:.2f}  |  "
            f"<b>Total: {cur} {detail['total']:.2f}</b>  |  "
            f"Paid: {cur} {detail['amount_paid']:.2f}"
        )
        self._header_label.setTextFormat(Qt.TextFormat.RichText)

        # Populate line-item table
        self._table.setRowCount(0)
        for item in detail["items"]:
            row = self._table.rowCount()
            self._table.insertRow(row)
            line_row = _EditLineRow(item, self._table, row)
            self._line_rows.append(line_row)

        self._table.resizeColumnsToContents()
        self._save_btn.setEnabled(True)

        # Pre-fill the search box so it shows which invoice is loaded
        self._search_edit.setText(detail["invoice_number"])

    # ── Save ──────────────────────────────────────────────────────────────

    def _save(self) -> None:
        if self._current_sale_id is None:
            QMessageBox.warning(self, "No invoice loaded", "Load an invoice first.")
            return

        reason = self._reason_edit.text().strip()
        if not reason:
            QMessageBox.warning(
                self, "Reason required",
                "Please explain why this invoice is being edited."
            )
            return

        changes: list[dict] = []
        for lr in self._line_rows:
            change: dict = {"sale_item_id": lr.sale_item_id}

            # ── Quantity ──────────────────────────────────────────────────
            new_qty = lr.qty_spin.value()
            if new_qty != lr.original_qty:
                change["new_quantity"] = new_qty

            # ── Unit price ────────────────────────────────────────────────
            price_text = lr.price_edit.text().strip()
            if price_text:
                try:
                    new_price = float(price_text)
                except ValueError:
                    QMessageBox.warning(
                        self, "Invalid price",
                        f"'{price_text}' is not a valid number for unit price."
                    )
                    return
                if abs(new_price - lr.original_price) > 0.001:
                    change["new_unit_price"] = new_price

            # ── Line discount ─────────────────────────────────────────────
            disc_text = lr.discount_edit.text().strip()
            if disc_text:
                try:
                    new_disc = float(disc_text)
                except ValueError:
                    QMessageBox.warning(
                        self, "Invalid discount",
                        f"'{disc_text}' is not a valid number for discount."
                    )
                    return
                if abs(new_disc - lr.original_disc) > 0.001:
                    change["new_line_discount"] = new_disc

            # Only send lines that actually have something to change
            if len(change) > 1:     # more than just sale_item_id
                changes.append(change)

        if not changes:
            QMessageBox.information(
                self, "No changes detected",
                "None of the quantities, prices or discounts have changed.\n"
                "Modify at least one value before saving."
            )
            return

        # Optional header overrides
        new_paid: float | None = None
        paid_text = self._new_paid_edit.text().strip()
        if paid_text:
            try:
                new_paid = float(paid_text)
            except ValueError:
                QMessageBox.warning(self, "Invalid amount", "Amount paid must be numeric.")
                return

        new_notes: str | None = self._new_notes_edit.text().strip() or None

        # Confirm before committing
        confirm = QMessageBox.question(
            self, "Confirm Edit",
            f"Apply {len(changes)} change(s) to invoice "
            f"{self._search_edit.text()}?\n\n"
            f"Reason: {reason}\n\n"
            "This will adjust stock levels and create an audit log entry.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return

        try:
            from app.services.invoice_edit_service import edit_invoice
            result = edit_invoice(
                sale_id=self._current_sale_id,
                line_changes=changes,
                reason=reason,
                new_amount_paid=new_paid,
                new_notes=new_notes,
            )
        except ApplicationError as exc:
            QMessageBox.critical(self, "Edit failed", str(exc))
            return

        cur = settings.currency
        QMessageBox.information(
            self, "Invoice Updated ✔",
            f"Invoice {result['invoice_number']} has been updated.\n\n"
            f"New Total:     {cur} {result['total']:.2f}\n"
            f"Amount Paid:  {cur} {result['amount_paid']:.2f}\n"
            f"Change Due:   {cur} {result['change_due']:.2f}\n\n"
            "Stock levels and audit log have been updated."
        )
        self.accept()
