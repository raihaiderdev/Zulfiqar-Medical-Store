"""
Sales / POS page.

Features:
  • Smart prefix search with live dropdown + full detail panel.
  • Cart reservation display (DB Avail = stock − cart qty).
  • Unit selector per line (Tablet / Strip / Box etc.).
  • Cart summary row: total items + grand total displayed below table.
  • Amount Paid auto-fills with (subtotal − discount) and updates live
    whenever discount changes — cashier can still override it manually.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QFrame,
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
from app.services import medicine_service, sales_service, settings_service
from app.utils.exceptions import ApplicationError


@dataclass
class CartLine:
    medicine_id: int
    medicine_name: str
    quantity: int
    unit_price_estimate: float
    sale_unit: str = "Unit"
    units_per_pack: int = 1
    db_stock: int = 0

    @property
    def base_units_in_cart(self) -> int:
        return self.quantity * self.units_per_pack

    @property
    def available_display(self) -> int:
        return max(0, self.db_stock - self.base_units_in_cart)

    @property
    def line_total(self) -> float:
        return self.unit_price_estimate * self.quantity


class SalesPOSPage(QWidget):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.cart: list[CartLine] = []
        self._last_search_results: list = []
        self._amount_paid_user_edited = False   # True once user manually types in amount paid

        root = QVBoxLayout(self)
        root.setSpacing(6)

        # ── Header ────────────────────────────────────────────────────────
        header_row = QHBoxLayout()
        header = QLabel("Sales / POS")
        header.setStyleSheet("font-size: 18px; font-weight: 600;")
        header_row.addWidget(header)
        header_row.addStretch()
        self.total_label = QLabel(f"Total: {settings.currency} 0.00")
        self.total_label.setStyleSheet("font-size: 15px; font-weight: 700; color: #154c89;")
        header_row.addWidget(self.total_label)
        root.addLayout(header_row)

        # ── Search + detail panel ─────────────────────────────────────────
        from app.ui.common.medicine_search_widget import MedicineSearchWidget
        self.search_widget = MedicineSearchWidget(
            self,
            show_detail=True,
            placeholder="Scan barcode or type medicine name…",
        )
        self.search_widget.medicine_selected.connect(self._on_medicine_selected)
        root.addWidget(self.search_widget)

        # ── Qty + unit row ────────────────────────────────────────────────
        qty_row = QHBoxLayout()
        qty_row.addWidget(QLabel("Qty:"))
        self.quantity_spin = QSpinBox()
        self.quantity_spin.setRange(1, 100_000)
        self.quantity_spin.setValue(1)
        qty_row.addWidget(self.quantity_spin)
        qty_row.addWidget(QLabel("Sell as:"))
        self.unit_combo = QComboBox()
        self.unit_combo.setMinimumWidth(120)
        self.unit_combo.currentIndexChanged.connect(self._on_unit_changed)
        qty_row.addWidget(self.unit_combo)
        self.unit_price_label = QLabel(f"@ {settings.currency} 0.00 each")
        self.unit_price_label.setStyleSheet("font-size: 12px; color: #555;")
        qty_row.addWidget(self.unit_price_label)
        qty_row.addStretch()
        add_btn = QPushButton("＋ Add to Cart")
        add_btn.setStyleSheet(
            "background-color: #27ae60; color: white; padding: 6px 16px; "
            "font-weight: 600; border-radius: 4px;"
        )
        add_btn.clicked.connect(self._add_selected_to_cart)
        qty_row.addWidget(add_btn)
        root.addLayout(qty_row)

        # ── Cart table ────────────────────────────────────────────────────
        self.cart_table = QTableWidget(0, 7)
        self.cart_table.setHorizontalHeaderLabels([
            "Medicine", "Sale Unit", "Qty",
            f"Unit Price ({settings.currency})",
            "DB Avail",
            f"Est. Total ({settings.currency})",
            "Remove",
        ])
        self.cart_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        for col in range(1, 7):
            self.cart_table.horizontalHeader().setSectionResizeMode(
                col, QHeaderView.ResizeMode.ResizeToContents
            )
        self.cart_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.cart_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.cart_table.setAlternatingRowColors(True)
        root.addWidget(self.cart_table)

        # ── Cart summary strip ────────────────────────────────────────────
        summary_frame = QFrame()
        summary_frame.setStyleSheet(
            "QFrame { background: #eaf4fb; border-radius: 4px; "
            "border: 1px solid #aed6f1; padding: 4px; }"
        )
        summary_layout = QHBoxLayout(summary_frame)
        summary_layout.setContentsMargins(10, 4, 10, 4)

        self._items_label = QLabel("Items: 0")
        self._items_label.setStyleSheet("font-size: 12px; color: #555;")
        summary_layout.addWidget(self._items_label)

        summary_layout.addStretch()

        self._subtotal_label = QLabel(f"Subtotal: {settings.currency} 0.00")
        self._subtotal_label.setStyleSheet("font-size: 12px; font-weight: 600; color: #333;")
        summary_layout.addWidget(self._subtotal_label)

        summary_layout.addWidget(QLabel("   "))

        self._summary_total_label = QLabel(f"Total after discount: {settings.currency} 0.00")
        self._summary_total_label.setStyleSheet(
            "font-size: 13px; font-weight: 700; color: #154c89;"
        )
        summary_layout.addWidget(self._summary_total_label)
        root.addWidget(summary_frame)

        # ── Payment row ───────────────────────────────────────────────────
        payment_frame = QFrame()
        payment_frame.setStyleSheet(
            "QFrame { background: #fdfefe; border-radius: 4px; "
            "border: 1px solid #ddd; padding: 4px; }"
        )
        payment_layout = QHBoxLayout(payment_frame)
        payment_layout.setContentsMargins(10, 6, 10, 6)
        payment_layout.setSpacing(12)

        disc_lbl = QLabel(f"Discount ({settings.currency}):")
        disc_lbl.setStyleSheet("font-weight: 600;")
        payment_layout.addWidget(disc_lbl)
        self.discount_edit = QLineEdit("0")
        self.discount_edit.setFixedWidth(90)
        self.discount_edit.setStyleSheet("padding: 4px; font-size: 13px;")
        self.discount_edit.textChanged.connect(self._on_discount_changed)
        payment_layout.addWidget(self.discount_edit)

        paid_lbl = QLabel(f"Amount Paid ({settings.currency}):")
        paid_lbl.setStyleSheet("font-weight: 600;")
        payment_layout.addWidget(paid_lbl)
        self.amount_paid_edit = QLineEdit("0")
        self.amount_paid_edit.setFixedWidth(110)
        self.amount_paid_edit.setStyleSheet(
            "padding: 4px; font-size: 13px; font-weight: 600; "
            "background: #eafaf1; border: 1px solid #27ae60;"
        )
        # Track when user manually edits the amount paid
        self.amount_paid_edit.textEdited.connect(self._on_amount_paid_edited)
        payment_layout.addWidget(self.amount_paid_edit)

        payment_layout.addStretch()

        clear_btn = QPushButton("🗑  Clear Cart")
        clear_btn.setStyleSheet("padding: 6px 14px; border-radius: 4px;")
        clear_btn.clicked.connect(self._clear_cart)
        payment_layout.addWidget(clear_btn)

        complete_btn = QPushButton("✔  Complete Sale")
        complete_btn.setStyleSheet(
            "background-color: #154c89; color: white; "
            "padding: 8px 20px; font-weight: 700; font-size: 13px; border-radius: 4px;"
        )
        complete_btn.clicked.connect(self._complete_sale)
        payment_layout.addWidget(complete_btn)

        root.addWidget(payment_frame)

        self._selected_medicine_id: Optional[int] = None
        self._selected_medicine_detail: Optional[dict] = None

    # ── Search callbacks ──────────────────────────────────────────────────

    def _on_medicine_selected(self, medicine_id: int, medicine_name: str) -> None:
        self._selected_medicine_id = medicine_id
        try:
            detail = medicine_service.get_medicine_detail(medicine_id)
        except ApplicationError:
            detail = None
        self._selected_medicine_detail = detail
        self._rebuild_unit_combo(detail)

    def _rebuild_unit_combo(self, detail: Optional[dict]) -> None:
        self.unit_combo.blockSignals(True)
        self.unit_combo.clear()
        if detail is None:
            self.unit_combo.addItem("Unit", (1, 0.0))
            self.unit_combo.blockSignals(False)
            self._on_unit_changed()
            return

        base_unit = detail.get("base_unit") or "Unit"
        pack_unit = detail.get("pack_unit") or ""
        units_per_pack = int(detail.get("units_per_pack") or 1)

        base_price = 0.0
        for b in detail.get("batches", []):
            if b["quantity"] > 0 and b["status"] != "EXPIRED":
                base_price = b["selling_price"]
                break

        self.unit_combo.addItem(base_unit, (1, base_price))
        if pack_unit and units_per_pack > 1:
            self.unit_combo.addItem(
                f"{pack_unit} ({units_per_pack} {base_unit}s)",
                (units_per_pack, base_price * units_per_pack),
            )
        self.unit_combo.blockSignals(False)
        self._on_unit_changed()

    def _on_unit_changed(self) -> None:
        data = self.unit_combo.currentData()
        if data is None:
            self.unit_price_label.setText(f"@ {settings.currency} 0.00 each")
            return
        _, price = data
        self.unit_price_label.setText(f"@ {settings.currency} {price:.2f} each")

    # ── Payment callbacks ─────────────────────────────────────────────────

    def _on_discount_changed(self) -> None:
        """Whenever discount changes, recalculate total AND auto-update Amount Paid."""
        self._update_summary()
        # Auto-update amount paid UNLESS the cashier manually typed something
        if not self._amount_paid_user_edited:
            self._auto_fill_amount_paid()

    def _on_amount_paid_edited(self) -> None:
        """User manually typed in Amount Paid — stop auto-filling."""
        self._amount_paid_user_edited = True

    def _auto_fill_amount_paid(self) -> None:
        """Set Amount Paid = subtotal − discount (the exact amount due)."""
        subtotal = sum(l.line_total for l in self.cart)
        try:
            discount = float(self.discount_edit.text() or 0)
        except ValueError:
            discount = 0.0
        total = max(0.0, subtotal - discount)
        self.amount_paid_edit.blockSignals(True)
        self.amount_paid_edit.setText(f"{total:.2f}")
        self.amount_paid_edit.blockSignals(False)

    # ── Cart management ───────────────────────────────────────────────────

    def _add_selected_to_cart(self) -> None:
        if self._selected_medicine_id is None:
            QMessageBox.information(self, "No selection", "Search and select a medicine first.")
            return

        quantity = self.quantity_spin.value()
        data = self.unit_combo.currentData()
        if data is None:
            QMessageBox.warning(self, "No unit", "Select a unit to sell.")
            return
        units_per_pack, price_per_unit = data
        sale_unit = self.unit_combo.currentText()
        detail = self._selected_medicine_detail
        medicine_name = detail["name"] if detail else str(self._selected_medicine_id)
        db_stock = detail["total_stock"] if detail else 0

        already_reserved = sum(
            l.base_units_in_cart for l in self.cart
            if l.medicine_id == self._selected_medicine_id
        )
        base_needed = quantity * units_per_pack
        free_stock = db_stock - already_reserved

        if base_needed > free_stock:
            QMessageBox.warning(
                self, "Insufficient stock",
                f"Only {free_stock} base unit(s) available for '{medicine_name}'.\n"
                f"Trying to add {base_needed} base unit(s)."
            )
            return

        # Increment existing line if same medicine + same unit
        for line in self.cart:
            if line.medicine_id == self._selected_medicine_id and line.sale_unit == sale_unit:
                line.quantity += quantity
                self._render_cart()
                # Reset manual-edit flag so Amount Paid updates
                self._amount_paid_user_edited = False
                self._auto_fill_amount_paid()
                return

        self.cart.append(CartLine(
            medicine_id=self._selected_medicine_id,
            medicine_name=medicine_name,
            quantity=quantity,
            unit_price_estimate=price_per_unit,
            sale_unit=sale_unit,
            units_per_pack=units_per_pack,
            db_stock=db_stock,
        ))
        # Reset so Amount Paid updates to new total
        self._amount_paid_user_edited = False
        self._render_cart()
        self._auto_fill_amount_paid()

    def _remove_from_cart(self, index: int) -> None:
        if 0 <= index < len(self.cart):
            self.cart.pop(index)
            self._amount_paid_user_edited = False
            self._render_cart()
            self._auto_fill_amount_paid()

    def _clear_cart(self) -> None:
        self.cart.clear()
        self._amount_paid_user_edited = False
        self.discount_edit.setText("0")
        self.amount_paid_edit.setText("0")
        self.search_widget.clear_search()
        self._selected_medicine_id = None
        self._selected_medicine_detail = None
        self._rebuild_unit_combo(None)
        self._render_cart()

    def _render_cart(self) -> None:
        self.cart_table.setRowCount(0)
        for idx, line in enumerate(self.cart):
            row = self.cart_table.rowCount()
            self.cart_table.insertRow(row)

            self.cart_table.setItem(row, 0, QTableWidgetItem(line.medicine_name))
            self.cart_table.setItem(row, 1, QTableWidgetItem(line.sale_unit))
            self.cart_table.setItem(row, 2, QTableWidgetItem(str(line.quantity)))

            price_item = QTableWidgetItem(f"{line.unit_price_estimate:.2f}")
            price_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self.cart_table.setItem(row, 3, price_item)

            avail = line.available_display
            avail_item = QTableWidgetItem(str(avail))
            avail_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter | Qt.AlignmentFlag.AlignVCenter)
            if avail <= 0:
                avail_item.setForeground(Qt.GlobalColor.red)
            elif avail <= 10:
                avail_item.setForeground(Qt.GlobalColor.darkYellow)
            else:
                avail_item.setForeground(Qt.GlobalColor.darkGreen)
            self.cart_table.setItem(row, 4, avail_item)

            total_item = QTableWidgetItem(f"{line.line_total:.2f}")
            total_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self.cart_table.setItem(row, 5, total_item)

            remove_btn = QPushButton("✕ Remove")
            remove_btn.setStyleSheet(
                "padding: 3px 8px; background-color: #e74c3c; color: white; border-radius: 3px;"
            )
            remove_btn.clicked.connect(lambda _, i=idx: self._remove_from_cart(i))
            cell = QWidget()
            cl = QHBoxLayout(cell)
            cl.setContentsMargins(3, 2, 3, 2)
            cl.addWidget(remove_btn)
            self.cart_table.setCellWidget(row, 6, cell)

        self._update_summary()

    def _update_summary(self) -> None:
        """Update the cart summary strip, header total label, and Amount Paid."""
        subtotal = sum(l.line_total for l in self.cart)
        total_items = sum(l.quantity for l in self.cart)

        try:
            discount = float(self.discount_edit.text() or 0)
        except ValueError:
            discount = 0.0

        total = max(0.0, subtotal - discount)

        # Header total (top right)
        self.total_label.setText(f"Total: {settings.currency} {total:.2f}")

        # Summary strip
        self._items_label.setText(
            f"Items: {len(self.cart)} line(s)  |  Total Qty: {total_items}"
        )
        self._subtotal_label.setText(
            f"Subtotal: {settings.currency} {subtotal:.2f}"
            + (f"  −  Discount: {settings.currency} {discount:.2f}" if discount > 0 else "")
        )
        self._summary_total_label.setText(
            f"Amount Due: {settings.currency} {total:.2f}"
        )

    # ── Complete sale ─────────────────────────────────────────────────────

    def _complete_sale(self) -> None:
        if not self.cart:
            QMessageBox.information(self, "Empty cart", "Add at least one item before completing the sale.")
            return
        try:
            discount    = float(self.discount_edit.text() or 0)
            amount_paid = float(self.amount_paid_edit.text() or 0)
        except ValueError:
            QMessageBox.warning(self, "Invalid input", "Discount and Amount Paid must be numeric.")
            return

        lines = [
            {"medicine_id": line.medicine_id, "quantity": line.base_units_in_cart}
            for line in self.cart
        ]

        try:
            result = sales_service.complete_sale(
                lines=lines, amount_paid=amount_paid, discount_total=discount
            )
        except ApplicationError as exc:
            QMessageBox.critical(self, "Sale failed", str(exc))
            return

        cur = settings.currency
        QMessageBox.information(
            self, "Sale Completed ✔",
            f"Invoice:      {result.invoice_number}\n"
            f"Total:         {cur} {result.total:.2f}\n"
            f"Paid:           {cur} {amount_paid:.2f}\n"
            f"Change due: {cur} {result.change_due:.2f}",
        )
        self._offer_print_invoice(result.sale_id)

        # Reset everything
        self.cart.clear()
        self._amount_paid_user_edited = False
        self.discount_edit.setText("0")
        self.amount_paid_edit.setText("0")
        self.search_widget.clear_search()
        self._selected_medicine_id = None
        self._selected_medicine_detail = None
        self._rebuild_unit_combo(None)
        self._render_cart()

    def _offer_print_invoice(self, sale_id: int) -> None:
        if QMessageBox.question(self, "Print Invoice?", "Save this invoice as a PDF?") \
                != QMessageBox.StandardButton.Yes:
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "Save Invoice PDF", "invoice.pdf", "PDF Files (*.pdf)"
        )
        if not path:
            return
        try:
            from app.printing.pdf_documents import render_invoice_pdf
            detail = sales_service.get_sale_detail(sale_id)
            pharmacy_name = settings_service.get_setting(
                "pharmacy.name", default="Zulfiqar Medical Store"
            )
            render_invoice_pdf(detail, path, pharmacy_name=pharmacy_name)
            QMessageBox.information(self, "PDF Saved", f"Invoice saved to:\n{path}")
        except Exception as exc:
            QMessageBox.critical(self, "Could not generate invoice", str(exc))
