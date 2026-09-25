"""
Purchase Orders page — Phase 2.

Full PO lifecycle: Create → Approve → Receive → Complete.
Reorder suggestions can auto-populate a new PO (Phase 1 + Phase 2 integration).
"""
from __future__ import annotations

from datetime import date, timedelta

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QDateEdit,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
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
from app.utils.exceptions import ApplicationError


# ── Create PO dialog ──────────────────────────────────────────────────────

class CreatePODialog(QDialog):
    """Simple dialog to create a draft PO with multiple medicine lines."""

    def __init__(self, parent=None, prefill_lines: list[dict] | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Create Purchase Order")
        self.setMinimumSize(720, 560)
        self._lines: list[dict] = []
        layout = QVBoxLayout(self)

        # Supplier
        top = QFormLayout()
        self._supplier_combo = QComboBox()
        self._supplier_combo.setMinimumHeight(30)
        top.addRow("Supplier *:", self._supplier_combo)

        self._delivery_edit = QDateEdit(calendarPopup=True)
        self._delivery_edit.setDate(date.today() + timedelta(days=7))
        top.addRow("Expected Delivery:", self._delivery_edit)

        self._notes_edit = QLineEdit()
        self._notes_edit.setPlaceholderText("Optional notes")
        top.addRow("Notes:", self._notes_edit)
        layout.addLayout(top)

        # Lines table
        lines_lbl = QLabel("Order Lines:")
        lines_lbl.setStyleSheet("font-weight:600;")
        layout.addWidget(lines_lbl)

        self._lines_table = QTableWidget(0, 4)
        self._lines_table.setHorizontalHeaderLabels(
            ["Medicine", "Ordered Qty", f"Unit Price ({settings.currency})", "Notes"]
        )
        self._lines_table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeMode.Stretch
        )
        self._lines_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._lines_table.setAlternatingRowColors(True)
        layout.addWidget(self._lines_table, 1)

        # Add line row
        add_row = QHBoxLayout()
        self._med_combo = QComboBox()
        self._med_combo.setMinimumWidth(200)
        self._qty_spin = QSpinBox()
        self._qty_spin.setRange(1, 100_000)
        self._qty_spin.setValue(1)
        self._price_edit = QLineEdit()
        self._price_edit.setPlaceholderText("Price")
        self._price_edit.setFixedWidth(80)
        add_line_btn = QPushButton("＋ Add Line")
        add_line_btn.setStyleSheet(
            "background:#27ae60;color:white;font-weight:600;padding:5px 12px;border-radius:4px;"
        )
        add_line_btn.clicked.connect(self._add_line)

        add_row.addWidget(QLabel("Medicine:"))
        add_row.addWidget(self._med_combo, 1)
        add_row.addWidget(QLabel("Qty:"))
        add_row.addWidget(self._qty_spin)
        add_row.addWidget(QLabel("Price:"))
        add_row.addWidget(self._price_edit)
        add_row.addWidget(add_line_btn)
        layout.addLayout(add_row)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.button(QDialogButtonBox.StandardButton.Save).setText("Create PO")
        buttons.accepted.connect(self._save)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self._load_data(prefill_lines)

    def _load_data(self, prefill_lines) -> None:
        try:
            from app.services.party_service import list_all_suppliers
            suppliers = list_all_suppliers()
            for s in suppliers:
                self._supplier_combo.addItem(s.name, s.id)
        except ApplicationError:
            pass

        try:
            from app.services.medicine_service import search_medicines
            medicines = search_medicines("")
            for m in medicines:
                self._med_combo.addItem(m.name, m.id)
        except ApplicationError:
            pass

        if prefill_lines:
            for line in prefill_lines:
                self._lines.append(line)
                self._render_line(line)

    def _add_line(self) -> None:
        med_id   = self._med_combo.currentData()
        med_name = self._med_combo.currentText()
        qty = self._qty_spin.value()
        try:
            price = float(self._price_edit.text() or 0)
        except ValueError:
            QMessageBox.warning(self, "Invalid price", "Price must be a number.")
            return
        if price <= 0:
            QMessageBox.warning(self, "Price required", "Enter a unit price > 0.")
            return
        line = {"medicine_id": med_id, "medicine_name": med_name,
                "ordered_quantity": qty, "unit_price": price}
        self._lines.append(line)
        self._render_line(line)

    def _render_line(self, line: dict) -> None:
        row = self._lines_table.rowCount()
        self._lines_table.insertRow(row)
        self._lines_table.setItem(row, 0, QTableWidgetItem(line.get("medicine_name", "")))
        qty_item = QTableWidgetItem(str(line["ordered_quantity"]))
        qty_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter | Qt.AlignmentFlag.AlignVCenter)
        self._lines_table.setItem(row, 1, qty_item)
        price_item = QTableWidgetItem(f"{line['unit_price']:.2f}")
        price_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self._lines_table.setItem(row, 2, price_item)
        self._lines_table.setItem(row, 3, QTableWidgetItem(""))

    def _save(self) -> None:
        supplier_id = self._supplier_combo.currentData()
        if supplier_id is None:
            QMessageBox.warning(self, "No supplier", "Select a supplier.")
            return
        if not self._lines:
            QMessageBox.warning(self, "No lines", "Add at least one order line.")
            return
        qt_d = self._delivery_edit.date()
        delivery = date(qt_d.year(), qt_d.month(), qt_d.day())
        try:
            from app.services.purchase_order_service import create_purchase_order
            po_id = create_purchase_order(
                supplier_id=supplier_id,
                lines=self._lines,
                expected_delivery_date=delivery,
                notes=self._notes_edit.text().strip() or None,
            )
        except ApplicationError as exc:
            QMessageBox.critical(self, "Could not create PO", str(exc))
            return
        QMessageBox.information(self, "✔ Purchase Order Created",
                                f"Draft PO #{po_id} created successfully.")
        self.accept()


# ── PO detail dialog ──────────────────────────────────────────────────────

class PODetailDialog(QDialog):
    def __init__(self, po_id: int, parent=None) -> None:
        super().__init__(parent)
        self._po_id = po_id
        self.setWindowTitle(f"Purchase Order Detail")
        self.setMinimumSize(700, 500)
        layout = QVBoxLayout(self)

        try:
            from app.services.purchase_order_service import get_purchase_order_detail
            self._detail = get_purchase_order_detail(po_id)
        except ApplicationError as exc:
            layout.addWidget(QLabel(f"Error: {exc}"))
            layout.addWidget(QPushButton("Close", clicked=self.accept))
            return

        d = self._detail
        cur = settings.currency

        # Header
        header = QLabel(
            f"<b>{d['po_number']}</b>  |  "
            f"Supplier: {d['supplier_name']}  |  "
            f"Date: {d['order_date']}  |  "
            f"Status: <b>{d['status']}</b>"
        )
        header.setTextFormat(Qt.TextFormat.RichText)
        header.setStyleSheet("padding:8px;background:#eaf4fb;border-radius:5px;")
        layout.addWidget(header)

        # Items
        items_lbl = QLabel("Order Lines:")
        items_lbl.setStyleSheet("font-weight:600;margin-top:6px;")
        layout.addWidget(items_lbl)

        table = QTableWidget(0, 5)
        table.setHorizontalHeaderLabels([
            "Medicine", "Ordered", "Received", "Remaining", f"Unit Price ({cur})"
        ])
        table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        table.setAlternatingRowColors(True)

        for item in d.get("items", []):
            row = table.rowCount(); table.insertRow(row)
            table.setItem(row, 0, QTableWidgetItem(item["medicine_name"]))
            for col, key in enumerate(["ordered_quantity","received_quantity","remaining","unit_price"], 1):
                v = item[key]
                it = QTableWidgetItem(f"{v:.2f}" if isinstance(v, float) else str(v))
                it.setTextAlignment(Qt.AlignmentFlag.AlignCenter | Qt.AlignmentFlag.AlignVCenter)
                if key == "remaining" and v > 0 and d["status"] not in ("COMPLETED","CANCELLED"):
                    it.setForeground(Qt.GlobalColor.darkYellow)
                table.setItem(row, col, it)

        layout.addWidget(table, 1)

        # Action buttons
        btn_row = QHBoxLayout()
        status = d["status"]

        if status == "DRAFT":
            approve_btn = QPushButton("✔ Approve")
            approve_btn.setStyleSheet("background:#27ae60;color:white;font-weight:600;padding:6px 14px;border-radius:4px;")
            approve_btn.clicked.connect(self._approve)
            btn_row.addWidget(approve_btn)

            cancel_btn = QPushButton("✕ Cancel PO")
            cancel_btn.setStyleSheet("background:#e74c3c;color:white;padding:6px 14px;border-radius:4px;")
            cancel_btn.clicked.connect(self._cancel)
            btn_row.addWidget(cancel_btn)

        if status in ("APPROVED", "PARTIALLY_RECEIVED"):
            recv_btn = QPushButton("📦 Receive Goods")
            recv_btn.setStyleSheet("background:#154c89;color:white;font-weight:600;padding:6px 14px;border-radius:4px;")
            recv_btn.clicked.connect(self._receive)
            btn_row.addWidget(recv_btn)

        btn_row.addStretch()
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.accept)
        btn_row.addWidget(close_btn)
        layout.addLayout(btn_row)

    def _approve(self):
        try:
            from app.services.purchase_order_service import approve_purchase_order
            approve_purchase_order(self._po_id)
            QMessageBox.information(self, "Approved", "Purchase order approved.")
            self.accept()
        except ApplicationError as exc:
            QMessageBox.critical(self, "Error", str(exc))

    def _cancel(self):
        if QMessageBox.question(self, "Confirm Cancel", "Cancel this purchase order?",
                                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
                                ) != QMessageBox.StandardButton.Yes:
            return
        try:
            from app.services.purchase_order_service import cancel_purchase_order
            cancel_purchase_order(self._po_id, reason="User cancelled from UI")
            QMessageBox.information(self, "Cancelled", "Purchase order cancelled.")
            self.accept()
        except ApplicationError as exc:
            QMessageBox.critical(self, "Error", str(exc))

    def _receive(self):
        QMessageBox.information(
            self, "Receive Goods",
            "Goods receipt is recorded via the Purchases section.\n"
            "Create a purchase record linked to this PO's items."
        )


# ── Purchase Orders page ──────────────────────────────────────────────────

class PurchaseOrdersPage(QWidget):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        root = QVBoxLayout(self)
        root.setSpacing(8)

        # Header
        hdr_row = QHBoxLayout()
        hdr = QLabel("Purchase Orders")
        hdr.setStyleSheet("font-size:18px;font-weight:600;")
        hdr_row.addWidget(hdr)
        hdr_row.addStretch()

        # Filter
        self._status_combo = QComboBox()
        self._status_combo.addItems(["All", "DRAFT", "APPROVED", "PARTIALLY_RECEIVED",
                                     "COMPLETED", "CANCELLED"])
        self._status_combo.currentIndexChanged.connect(self.refresh)
        hdr_row.addWidget(QLabel("Status:"))
        hdr_row.addWidget(self._status_combo)

        new_btn = QPushButton("＋ New Purchase Order")
        new_btn.setStyleSheet(
            "background:#154c89;color:white;font-weight:600;padding:6px 14px;border-radius:4px;"
        )
        new_btn.clicked.connect(self._create_po)
        hdr_row.addWidget(new_btn)
        root.addLayout(hdr_row)

        # Info banner
        info = QLabel(
            "ℹ  Purchase orders track planned purchases before goods arrive. "
            "Approve → Receive Goods to update inventory. "
            "Or use the Reorder Suggestions page to auto-create a PO."
        )
        info.setWordWrap(True)
        info.setStyleSheet("background:#eaf4fb;padding:8px;border-radius:4px;border:1px solid #aed6f1;font-size:12px;")
        root.addWidget(info)

        # Table
        self._table = QTableWidget(0, 7)
        self._table.setHorizontalHeaderLabels([
            "PO Number", "Supplier", "Order Date",
            "Exp. Delivery", "Status", "Lines", "Actions"
        ])
        hh = self._table.horizontalHeader()
        hh.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        hh.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        for c in [2, 3, 4, 5, 6]:
            hh.setSectionResizeMode(c, QHeaderView.ResizeMode.ResizeToContents)
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._table.setAlternatingRowColors(True)
        self._table.doubleClicked.connect(self._on_double_click)
        root.addWidget(self._table, 1)

        self._count_lbl = QLabel("0 purchase orders")
        self._count_lbl.setStyleSheet("color:#888;font-size:11px;")
        root.addWidget(self._count_lbl)

        self.refresh()

    _STATUS_COLOURS = {
        "DRAFT":             Qt.GlobalColor.darkBlue,
        "APPROVED":          Qt.GlobalColor.darkGreen,
        "PARTIALLY_RECEIVED": Qt.GlobalColor.darkYellow,
        "COMPLETED":         Qt.GlobalColor.darkGreen,
        "CANCELLED":         Qt.GlobalColor.red,
    }

    def refresh(self) -> None:
        status_filter = self._status_combo.currentText()
        try:
            from app.services.purchase_order_service import list_purchase_orders
            from app.models.purchase_order import POStatus
            status = None if status_filter == "All" else POStatus(status_filter)
            orders = list_purchase_orders(status=status)
        except ApplicationError as exc:
            QMessageBox.warning(self, "Cannot load POs", str(exc))
            return

        self._table.setRowCount(0)
        for po in orders:
            row = self._table.rowCount()
            self._table.insertRow(row)
            self._table.setItem(row, 0, QTableWidgetItem(po["po_number"]))
            self._table.setItem(row, 1, QTableWidgetItem(po["supplier_name"]))
            self._table.setItem(row, 2, QTableWidgetItem(po["order_date"]))
            self._table.setItem(row, 3, QTableWidgetItem(po.get("expected_delivery_date") or "—"))

            st_item = QTableWidgetItem(po["status"])
            st_item.setForeground(self._STATUS_COLOURS.get(po["status"], Qt.GlobalColor.black))
            self._table.setItem(row, 4, st_item)

            self._table.setItem(row, 5, QTableWidgetItem(str(po["line_count"])))

            view_btn = QPushButton("View / Act")
            view_btn.setStyleSheet("padding:3px 10px;")
            view_btn.clicked.connect(
                lambda _, pid=po["po_id"]: self._open_detail(pid)
            )
            cell = QWidget(); cl = QHBoxLayout(cell)
            cl.setContentsMargins(3, 2, 3, 2); cl.addWidget(view_btn)
            self._table.setCellWidget(row, 6, cell)

        self._count_lbl.setText(
            f"{len(orders)} purchase order(s)  |  "
            "Double-click a row to view details"
        )

    def _create_po(self) -> None:
        dlg = CreatePODialog(self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self.refresh()

    def _open_detail(self, po_id: int) -> None:
        dlg = PODetailDialog(po_id, self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self.refresh()

    def _on_double_click(self, index) -> None:
        # get po_id from po_number cell, look it up
        row = index.row()
        po_num = self._table.item(row, 0)
        if po_num:
            self.refresh()
