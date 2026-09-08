"""
Sales / POS page.

Features implemented:
  F4 — Smart prefix search with live dropdown (MedicineSearchWidget).
  F5 — Cart reservation display: shows DB available stock MINUS cart qty.
  F7 — Full medicine detail panel below search.
  F8 — Clearing the search field removes all stale results.
  F10 — Unit selector per cart line (Tablet / Strip / Box etc.).
       Base-unit deduction computed from units_per_pack.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
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
    quantity: int                   # in chosen sale unit
    unit_price_estimate: float      # price per chosen sale unit
    sale_unit: str = "Unit"         # e.g. "Tablet", "Strip", "Bottle"
    units_per_pack: int = 1         # how many base units per chosen sale unit
    db_stock: int = 0               # stock in DB at add-time (base units)

    @property
    def base_units_in_cart(self) -> int:
        """Base units currently reserved in the cart for this line."""
        return self.quantity * self.units_per_pack

    @property
    def available_display(self) -> int:
        """DB stock minus cart reservation (shown to user)."""
        return max(0, self.db_stock - self.base_units_in_cart)


class SalesPOSPage(QWidget):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.cart: list[CartLine] = []
        self._last_search_results: list = []
        root = QVBoxLayout(self)

        # ── Header ────────────────────────────────────────────────────────
        header_row = QHBoxLayout()
        header = QLabel("Sales / POS")
        header.setStyleSheet("font-size: 18px; font-weight: 600;")
        header_row.addWidget(header)
        header_row.addStretch()
        self.total_label = QLabel(f"Total: {settings.currency} 0.00")
        self.total_label.setStyleSheet("font-size: 14px; font-weight: 600; color: #154c89;")
        header_row.addWidget(self.total_label)
        root.addLayout(header_row)

        # ── Search (F4 + F7 + F8) ─────────────────────────────────────────
        from app.ui.common.medicine_search_widget import MedicineSearchWidget
        self.search_widget = MedicineSearchWidget(
            self,
            show_detail=True,
            placeholder="Scan barcode or type medicine name, then Enter…",
        )
        self.search_widget.medicine_selected.connect(self._on_medicine_selected)
        root.addWidget(self.search_widget)

        # Qty + unit selector row
        qty_row = QHBoxLayout()
        qty_row.addWidget(QLabel("Qty:"))
        self.quantity_spin = QSpinBox()
        self.quantity_spin.setRange(1, 100_000)
        self.quantity_spin.setValue(1)
        qty_row.addWidget(self.quantity_spin)

        qty_row.addWidget(QLabel("Sell as:"))
        self.unit_combo = QComboBox()
        self.unit_combo.setMinimumWidth(110)
        self.unit_combo.currentIndexChanged.connect(self._on_unit_changed)
        qty_row.addWidget(self.unit_combo)

        self.unit_price_label = QLabel("@ Rs 0.00 each")
        self.unit_price_label.setStyleSheet("font-size: 12px; color: #555;")
        qty_row.addWidget(self.unit_price_label)
        qty_row.addStretch()

        add_btn = QPushButton("＋ Add to Cart")
        add_btn.setStyleSheet("background-color: #27ae60; color: white; padding: 5px 14px; font-weight: 600;")
        add_btn.clicked.connect(self._add_selected_to_cart)
        qty_row.addWidget(add_btn)
        root.addLayout(qty_row)

        # ── Cart table (F5: shows DB-Avail column) ────────────────────────
        self.cart_table = QTableWidget(0, 7)
        self.cart_table.setHorizontalHeaderLabels([
            "Medicine", "Sale Unit", "Qty", "Unit Price (Rs)",
            "DB Avail", "Est. Total (Rs)", "Remove"
        ])
        self.cart_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        for col in range(1, 7):
            self.cart_table.horizontalHeader().setSectionResizeMode(
                col, QHeaderView.ResizeMode.ResizeToContents
            )
        self.cart_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.cart_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        root.addWidget(self.cart_table)

        # ── Totals / actions ───────────────────────────────────────────────
        totals_row = QHBoxLayout()
        totals_row.addWidget(QLabel("Discount (Rs):"))
        self.discount_edit = QLineEdit("0")
        self.discount_edit.setFixedWidth(80)
        self.discount_edit.textChanged.connect(self._update_total_label)
        totals_row.addWidget(self.discount_edit)
        totals_row.addWidget(QLabel("Amount Paid (Rs):"))
        self.amount_paid_edit = QLineEdit("0")
        self.amount_paid_edit.setFixedWidth(100)
        totals_row.addWidget(self.amount_paid_edit)
        totals_row.addStretch()

        clear_btn = QPushButton("Clear Cart")
        clear_btn.clicked.connect(self._clear_cart)
        totals_row.addWidget(clear_btn)

        complete_btn = QPushButton("✔  Complete Sale")
        complete_btn.setStyleSheet(
            "background-color: #154c89; color: white; padding: 8px 18px; "
            "font-weight: 700; font-size: 13px;"
        )
        complete_btn.clicked.connect(self._complete_sale)
        totals_row.addWidget(complete_btn)
        root.addLayout(totals_row)

        # State for currently selected medicine from search
        self._selected_medicine_id: Optional[int] = None
        self._selected_medicine_detail: Optional[dict] = None

    # ── Search selection callback ─────────────────────────────────────────

    def _on_medicine_selected(self, medicine_id: int, medicine_name: str) -> None:
        self._selected_medicine_id = medicine_id
        # Load detail for unit picker
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
            return

        base_unit = detail.get("base_unit") or "Unit"
        pack_unit = detail.get("pack_unit") or ""
        units_per_pack = int(detail.get("units_per_pack") or 1)

        # Get price from first in-stock FEFO batch
        base_price = 0.0
        for b in detail.get("batches", []):
            if b["quantity"] > 0 and b["status"] not in ("EXPIRED",):
                base_price = b["selling_price"]
                break

        # Always add base unit
        self.unit_combo.addItem(base_unit, (1, base_price))

        # Add pack unit if configured and > 1
        if pack_unit and units_per_pack > 1:
            pack_price = base_price * units_per_pack
            self.unit_combo.addItem(
                f"{pack_unit} ({units_per_pack} {base_unit}s)",
                (units_per_pack, pack_price),
            )

        self.unit_combo.blockSignals(False)
        self._on_unit_changed()

    def _on_unit_changed(self) -> None:
        data = self.unit_combo.currentData()
        if data is None:
            self.unit_price_label.setText("@ Rs 0.00 each")
            return
        _units_per, price = data
        self.unit_price_label.setText(f"@ Rs {price:.2f} each")

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
        medicine_name = (
            detail["name"] if detail else str(self._selected_medicine_id)
        )

        # DB total available (base units)
        db_stock = detail["total_stock"] if detail else 0

        # How many base units are already in cart for this medicine?
        already_reserved = sum(
            line.base_units_in_cart
            for line in self.cart
            if line.medicine_id == self._selected_medicine_id
        )
        base_needed = quantity * units_per_pack
        free_stock = db_stock - already_reserved

        if base_needed > free_stock:
            QMessageBox.warning(
                self, "Insufficient stock",
                f"Only {free_stock} base unit(s) available for '{medicine_name}'.\n"
                f"You are trying to add {base_needed} base unit(s)."
            )
            return

        # Update existing cart line if same medicine + same unit
        for line in self.cart:
            if line.medicine_id == self._selected_medicine_id and line.sale_unit == sale_unit:
                line.quantity += quantity
                self._render_cart()
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
        self._render_cart()

    def _remove_from_cart(self, index: int) -> None:
        if 0 <= index < len(self.cart):
            self.cart.pop(index)
            self._render_cart()

    def _clear_cart(self) -> None:
        self.cart.clear()
        self._render_cart()
        self.search_widget.clear_search()
        self._selected_medicine_id = None
        self._selected_medicine_detail = None
        self._rebuild_unit_combo(None)

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

            # F5: Available = DB stock - cart reservation
            avail = line.available_display
            avail_item = QTableWidgetItem(f"{avail}")
            if avail <= 0:
                avail_item.setForeground(Qt.GlobalColor.red)
            elif avail <= 10:
                avail_item.setForeground(Qt.GlobalColor.darkYellow)
            else:
                avail_item.setForeground(Qt.GlobalColor.darkGreen)
            self.cart_table.setItem(row, 4, avail_item)

            total_item = QTableWidgetItem(
                f"{line.unit_price_estimate * line.quantity:.2f}"
            )
            total_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self.cart_table.setItem(row, 5, total_item)

            remove_btn = QPushButton("✕ Remove")
            remove_btn.setStyleSheet("padding: 3px 8px; background-color: #e74c3c; color: white;")
            remove_btn.clicked.connect(lambda _, i=idx: self._remove_from_cart(i))
            cell = QWidget()
            cl = QHBoxLayout(cell)
            cl.setContentsMargins(2, 2, 2, 2)
            cl.addWidget(remove_btn)
            self.cart_table.setCellWidget(row, 6, cell)

        self._update_total_label()

    def _update_total_label(self) -> None:
        subtotal = sum(l.unit_price_estimate * l.quantity for l in self.cart)
        try:
            discount = float(self.discount_edit.text() or 0)
        except ValueError:
            discount = 0.0
        total = max(0.0, subtotal - discount)
        self.total_label.setText(f"Total: {settings.currency} {total:.2f}")

    # ── Complete sale ─────────────────────────────────────────────────────

    def _complete_sale(self) -> None:
        if not self.cart:
            QMessageBox.information(self, "Empty cart", "Add at least one item before completing the sale.")
            return
        try:
            discount = float(self.discount_edit.text() or 0)
            amount_paid = float(self.amount_paid_edit.text() or 0)
        except ValueError:
            QMessageBox.warning(self, "Invalid input", "Discount and Amount Paid must be numeric.")
            return

        # Build sale lines — quantity sent to service is in BASE UNITS
        lines = []
        for line in self.cart:
            lines.append({
                "medicine_id": line.medicine_id,
                "quantity": line.base_units_in_cart,
            })

        try:
            result = sales_service.complete_sale(
                lines=lines, amount_paid=amount_paid, discount_total=discount
            )
        except ApplicationError as exc:
            QMessageBox.critical(self, "Sale failed", str(exc))
            return

        QMessageBox.information(
            self, "Sale Completed ✔",
            f"Invoice:     {result.invoice_number}\n"
            f"Total:        {settings.currency} {result.total:.2f}\n"
            f"Paid:          {settings.currency} {amount_paid:.2f}\n"
            f"Change due: {settings.currency} {result.change_due:.2f}",
        )
        self._offer_print_invoice(result.sale_id)
        self.cart.clear()
        self.discount_edit.setText("0")
        self.amount_paid_edit.setText("0")
        self.search_widget.clear_search()
        self._selected_medicine_id = None
        self._selected_medicine_detail = None
        self._rebuild_unit_combo(None)
        self._render_cart()

    def _offer_print_invoice(self, sale_id: int) -> None:
        answer = QMessageBox.question(self, "Print Invoice?", "Save this invoice as a PDF?")
        if answer != QMessageBox.StandardButton.Yes:
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
