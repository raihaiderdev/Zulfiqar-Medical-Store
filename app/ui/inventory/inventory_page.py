"""
Inventory page.

Features implemented:
  F8  — Clear search removes stale results instantly.
  F9  — Full search bar + filter combo + complete column table.
        Columns: Medicine, Formula, Batch, Qty, Unit, Buy Price,
                 Sell Price, Expiry, Wardrobe, Rack, Shelf, Status.
        Filters: All | In Stock | Low Stock | Out of Stock |
                 Expiring Soon | Expired.
"""
from __future__ import annotations

from datetime import date

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.config.settings import settings
from app.services import medicine_service, returns_service
from app.utils.exceptions import ApplicationError


# ── helpers ───────────────────────────────────────────────────────────────

def _months_between(d1: date, d2: date) -> float:
    m = (d2.year - d1.year) * 12 + (d2.month - d1.month)
    if d2.day < d1.day:
        m -= 1
    return m


def _batch_status(qty: int, expiry: date, min_stock: int, today: date) -> str:
    if expiry < today:
        return "EXPIRED"
    months = _months_between(today, expiry)
    if months <= 1:
        return "EXPIRING VERY SOON"
    if months <= 7:
        return "EXPIRING SOON"
    if qty <= 0:
        return "OUT OF STOCK"
    if qty <= min_stock:
        return "LOW STOCK"
    return "IN STOCK"


_STATUS_FG = {
    "IN STOCK": Qt.GlobalColor.darkGreen,
    "LOW STOCK": Qt.GlobalColor.darkYellow,
    "OUT OF STOCK": Qt.GlobalColor.red,
    "EXPIRING SOON": Qt.GlobalColor.darkYellow,
    "EXPIRING VERY SOON": Qt.GlobalColor.red,
    "EXPIRED": Qt.GlobalColor.red,
}


# ── Adjust Stock Dialog ────────────────────────────────────────────────────

class AdjustStockDialog(QDialog):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Manual Stock Adjustment")
        self.setMinimumWidth(420)
        layout = QFormLayout(self)

        self.medicine_combo = QComboBox()
        self.medicine_combo.currentIndexChanged.connect(self._on_medicine_changed)
        layout.addRow("Medicine *", self.medicine_combo)

        self.batch_combo = QComboBox()
        layout.addRow("Batch *", self.batch_combo)

        self.delta_spin = QSpinBox()
        self.delta_spin.setRange(-1_000_000, 1_000_000)
        layout.addRow("Quantity Change (+/-) *", self.delta_spin)

        self.reason_edit = QLineEdit()
        layout.addRow("Reason *", self.reason_edit)

        note = QLabel("Positive = stock in, negative = stock out. A reason is required.")
        note.setWordWrap(True)
        layout.addRow(note)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._save)
        buttons.rejected.connect(self.reject)
        layout.addRow(buttons)

        self._load_medicines()

    def _load_medicines(self) -> None:
        try:
            medicines = medicine_service.search_medicines("")
        except ApplicationError as exc:
            QMessageBox.warning(self, "Cannot load medicines", str(exc))
            return
        self.medicine_combo.clear()
        for m in medicines:
            self.medicine_combo.addItem(m.name, m)
        self._on_medicine_changed()

    def _on_medicine_changed(self) -> None:
        self.batch_combo.clear()
        medicine = self.medicine_combo.currentData()
        if medicine is None:
            return
        active_batches = [b for b in medicine.batches if b.is_active]
        if not active_batches:
            self.batch_combo.addItem("— no active batches —", None)
            return
        for b in active_batches:
            label = f"{b.batch_number}  (qty: {b.quantity}, exp: {b.expiry_date})"
            self.batch_combo.addItem(label, b.id)

    def _save(self) -> None:
        batch_id = self.batch_combo.currentData()
        if batch_id is None:
            QMessageBox.warning(self, "Missing selection", "Select a batch.")
            return
        if self.delta_spin.value() == 0:
            QMessageBox.warning(self, "Invalid delta", "Quantity change cannot be zero.")
            return
        if not self.reason_edit.text().strip():
            QMessageBox.warning(self, "Missing reason", "A reason is required.")
            return
        try:
            returns_service.adjust_stock(
                batch_id=batch_id,
                delta=self.delta_spin.value(),
                reason=self.reason_edit.text().strip(),
            )
        except ApplicationError as exc:
            QMessageBox.critical(self, "Adjustment failed", str(exc))
            return
        self.accept()


# ── Inventory Page ────────────────────────────────────────────────────────

class InventoryPage(QWidget):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._all_rows: list[dict] = []   # full flat row cache for in-memory filtering
        root = QVBoxLayout(self)

        # ── Header ─────────────────────────────────────────────────────────
        top_row = QHBoxLayout()
        header = QLabel("Inventory")
        header.setStyleSheet("font-size: 18px; font-weight: 600;")
        top_row.addWidget(header)
        top_row.addStretch()
        refresh_btn = QPushButton("Refresh")
        refresh_btn.clicked.connect(self.refresh)
        adjust_btn = QPushButton("Adjust Stock…")
        adjust_btn.clicked.connect(self._open_adjust_dialog)
        top_row.addWidget(refresh_btn)
        top_row.addWidget(adjust_btn)
        root.addLayout(top_row)

        # ── Search + filter row (F9) ────────────────────────────────────────
        filter_row = QHBoxLayout()
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText(
            "Search by medicine, formula, brand, batch, barcode, wardrobe, rack, shelf…"
        )
        self.search_edit.setClearButtonEnabled(True)
        # F8: clear search removes stale results immediately
        self.search_edit.textChanged.connect(self._apply_filter)
        filter_row.addWidget(self.search_edit, 3)

        self.filter_combo = QComboBox()
        self.filter_combo.addItems([
            "All", "In Stock", "Low Stock", "Out of Stock",
            "Expiring Soon", "Expired"
        ])
        self.filter_combo.currentIndexChanged.connect(self._apply_filter)
        filter_row.addWidget(QLabel("Show:"))
        filter_row.addWidget(self.filter_combo)
        root.addLayout(filter_row)

        # ── Full inventory table (F9 columns) ──────────────────────────────
        self.inv_table = QTableWidget(0, 13)
        self.inv_table.setHorizontalHeaderLabels([
            "Medicine", "Formula", "Batch", "Qty",
            "Unit", "Buy Price", "Sell Price",
            "Expiry", "Wardrobe", "Rack", "Shelf", "Supplier", "Status"
        ])
        self.inv_table.horizontalHeader().setStretchLastSection(True)
        self.inv_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.inv_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.inv_table.setAlternatingRowColors(True)
        root.addWidget(self.inv_table, 1)

        self.row_count_label = QLabel("0 items")
        self.row_count_label.setStyleSheet("color: #666; font-size: 11px;")
        root.addWidget(self.row_count_label)

        self.refresh()

    def _open_adjust_dialog(self) -> None:
        dialog = AdjustStockDialog(self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.refresh()

    def refresh(self) -> None:
        """Reload all batch data from services and rebuild the flat row cache."""
        try:
            medicines = medicine_service.search_medicines("")
        except ApplicationError as exc:
            QMessageBox.warning(self, "Cannot load inventory", str(exc))
            return

        today = date.today()
        rows: list[dict] = []

        for med in medicines:
            for b in med.batches:
                if not b.is_active:
                    continue
                # Location
                wardrobe = rack = shelf = ""
                if b.shelf:
                    try:
                        shelf = b.shelf.code
                        rack = b.shelf.rack.code
                        wardrobe = b.shelf.rack.wardrobe.code
                    except Exception:
                        pass

                supplier = b.supplier.name if b.supplier else ""
                status = _batch_status(b.quantity, b.expiry_date, med.min_stock_level, today)

                rows.append({
                    "medicine": med.name,
                    "formula": med.generic_formula or "",
                    "batch": b.batch_number,
                    "qty": b.quantity,
                    "unit": med.unit or "",
                    "buy_price": float(b.purchase_price),
                    "sell_price": float(b.selling_price),
                    "expiry": b.expiry_date.isoformat(),
                    "wardrobe": wardrobe,
                    "rack": rack,
                    "shelf": shelf,
                    "supplier": supplier,
                    "status": status,
                })

        self._all_rows = rows
        self._apply_filter()

    def _apply_filter(self) -> None:
        """Filter the cached rows by search term and status filter, then render."""
        term = self.search_edit.text().strip().lower()
        status_filter = self.filter_combo.currentText()

        # Map combo text → status key(s)
        filter_map = {
            "All": None,
            "In Stock": {"IN STOCK"},
            "Low Stock": {"LOW STOCK"},
            "Out of Stock": {"OUT OF STOCK"},
            "Expiring Soon": {"EXPIRING SOON", "EXPIRING VERY SOON"},
            "Expired": {"EXPIRED"},
        }
        allowed_statuses = filter_map.get(status_filter)

        visible = []
        for row in self._all_rows:
            if allowed_statuses and row["status"] not in allowed_statuses:
                continue
            if term:
                haystack = " ".join([
                    row["medicine"], row["formula"], row["batch"],
                    row["wardrobe"], row["rack"], row["shelf"],
                    row["supplier"],
                ]).lower()
                if term not in haystack:
                    continue
            visible.append(row)

        self._populate_table(visible)

    def _populate_table(self, rows: list[dict]) -> None:
        self.inv_table.setRowCount(0)
        cur = settings.currency

        for row_data in rows:
            row = self.inv_table.rowCount()
            self.inv_table.insertRow(row)

            self.inv_table.setItem(row, 0, QTableWidgetItem(row_data["medicine"]))
            self.inv_table.setItem(row, 1, QTableWidgetItem(row_data["formula"]))
            self.inv_table.setItem(row, 2, QTableWidgetItem(row_data["batch"]))

            qty_item = QTableWidgetItem(str(row_data["qty"]))
            qty_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self.inv_table.setItem(row, 3, qty_item)

            self.inv_table.setItem(row, 4, QTableWidgetItem(row_data["unit"]))

            buy_item = QTableWidgetItem(f"{row_data['buy_price']:.2f}")
            buy_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self.inv_table.setItem(row, 5, buy_item)

            sell_item = QTableWidgetItem(f"{row_data['sell_price']:.2f}")
            sell_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self.inv_table.setItem(row, 6, sell_item)

            self.inv_table.setItem(row, 7, QTableWidgetItem(row_data["expiry"]))
            self.inv_table.setItem(row, 8, QTableWidgetItem(row_data["wardrobe"]))
            self.inv_table.setItem(row, 9, QTableWidgetItem(row_data["rack"]))
            self.inv_table.setItem(row, 10, QTableWidgetItem(row_data["shelf"]))
            self.inv_table.setItem(row, 11, QTableWidgetItem(row_data["supplier"]))

            status = row_data["status"]
            status_item = QTableWidgetItem(status)
            status_item.setForeground(_STATUS_FG.get(status, Qt.GlobalColor.black))
            self.inv_table.setItem(row, 12, status_item)

        self.inv_table.resizeColumnsToContents()
        self.row_count_label.setText(f"{len(rows)} item(s) shown")
