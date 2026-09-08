"""
Medicines page — full CRUD with live stock status.

Layout:
  • Full-width table at all times — all columns always visible.
  • Clicking a row opens a detail DIALOG (not an inline panel) so the
    table is never squeezed.
  • Columns use Interactive resize so the user can drag them wider.
  • Minimum column widths prevent truncation.
"""
from __future__ import annotations

from datetime import date, timedelta

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QFont
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
    QScrollArea,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.models.enums import DosageForm
from app.services import medicine_service
from app.utils.exceptions import ApplicationError


# ── Status helpers ────────────────────────────────────────────────────────

_STATUS_FG = {
    "IN STOCK":           Qt.GlobalColor.darkGreen,
    "LOW STOCK":          Qt.GlobalColor.darkYellow,
    "OUT OF STOCK":       Qt.GlobalColor.red,
    "EXPIRING SOON":      Qt.GlobalColor.darkYellow,
    "EXPIRING VERY SOON": Qt.GlobalColor.red,
    "EXPIRED":            Qt.GlobalColor.red,
}

_STATUS_BG = {
    "IN STOCK":           "#eafaf1",
    "LOW STOCK":          "#fef9e7",
    "OUT OF STOCK":       "#fdedec",
    "EXPIRING SOON":      "#fef9e7",
    "EXPIRING VERY SOON": "#fdedec",
    "EXPIRED":            "#fdedec",
}


def _medicine_status(med) -> tuple[int, str]:
    today = date.today()
    total_qty = 0
    has_expired = False
    has_expiring = False
    for b in med.batches:
        if not b.is_active:
            continue
        total_qty += b.quantity
        days = (b.expiry_date - today).days
        if days < 0:
            has_expired = True
        elif days <= 214:
            has_expiring = True
    if has_expired and total_qty <= 0:
        return total_qty, "EXPIRED"
    if total_qty <= 0:
        return total_qty, "OUT OF STOCK"
    if total_qty <= med.min_stock_level:
        return total_qty, "LOW STOCK"
    if has_expired or has_expiring:
        return total_qty, "EXPIRING SOON"
    return total_qty, "IN STOCK"


# ── Medicine Detail Dialog ────────────────────────────────────────────────

class MedicineDetailDialog(QDialog):
    """Full detail view for a medicine — opened when a row is clicked."""

    def __init__(self, medicine_id: int, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Medicine Detail")
        self.setMinimumSize(780, 480)
        layout = QVBoxLayout(self)

        try:
            from app.ui.common.medicine_search_widget import MedicineSearchWidget
            widget = MedicineSearchWidget(self, show_detail=True)
            # Hide the search bar — we drive it directly
            widget.search_edit.setVisible(False)
            widget.results_list.setVisible(False)
            widget._load_detail(medicine_id)
            layout.addWidget(widget, 1)
        except Exception as exc:
            layout.addWidget(QLabel(f"Could not load detail: {exc}"))

        close_btn = QPushButton("Close")
        close_btn.setStyleSheet("padding: 6px 18px;")
        close_btn.clicked.connect(self.accept)
        row = QHBoxLayout()
        row.addStretch()
        row.addWidget(close_btn)
        layout.addLayout(row)


# ── Add Medicine dialog ───────────────────────────────────────────────────

class AddMedicineDialog(QDialog):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Add Medicine")
        self.setMinimumWidth(500)
        layout = QFormLayout(self)

        self.name_edit         = QLineEdit()
        self.formula_edit      = QLineEdit()
        self.brand_edit        = QLineEdit()
        self.category_edit     = QLineEdit()
        self.manufacturer_edit = QLineEdit()
        self.dosage_combo      = QComboBox()
        self.dosage_combo.addItems([f.value for f in DosageForm])
        self.strength_edit     = QLineEdit()
        self.pack_size_edit    = QLineEdit()
        self.base_unit_edit    = QLineEdit()
        self.base_unit_edit.setPlaceholderText("e.g. Tablet, Capsule, mL")
        self.pack_unit_edit    = QLineEdit()
        self.pack_unit_edit.setPlaceholderText("e.g. Strip, Box  (leave blank if N/A)")
        self.units_per_pack_spin = QSpinBox()
        self.units_per_pack_spin.setRange(1, 10_000)
        self.units_per_pack_spin.setValue(1)
        self.barcode_edit      = QLineEdit()
        self.min_stock_spin    = QSpinBox()
        self.min_stock_spin.setRange(0, 1_000_000)
        self.min_stock_spin.setValue(10)
        self.reorder_spin      = QSpinBox()
        self.reorder_spin.setRange(0, 1_000_000)
        self.reorder_spin.setValue(20)
        self.notes_edit        = QLineEdit()

        layout.addRow("Name *",          self.name_edit)
        layout.addRow("Generic Formula", self.formula_edit)
        layout.addRow("Brand Name",      self.brand_edit)
        layout.addRow("Category",        self.category_edit)
        layout.addRow("Manufacturer",    self.manufacturer_edit)
        layout.addRow("Dosage Form",     self.dosage_combo)
        layout.addRow("Strength",        self.strength_edit)
        layout.addRow("Pack Size",       self.pack_size_edit)
        layout.addRow("Base Unit",       self.base_unit_edit)
        layout.addRow("Pack Unit",       self.pack_unit_edit)
        layout.addRow("Units per Pack",  self.units_per_pack_spin)
        layout.addRow("Barcode",         self.barcode_edit)
        layout.addRow("Min Stock Level", self.min_stock_spin)
        layout.addRow("Reorder Level",   self.reorder_spin)
        layout.addRow("Notes",           self.notes_edit)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._save)
        buttons.rejected.connect(self.reject)
        layout.addRow(buttons)

    def _save(self) -> None:
        if not self.name_edit.text().strip():
            QMessageBox.warning(self, "Missing field", "Medicine name is required.")
            return
        try:
            medicine_service.add_medicine(
                name=self.name_edit.text().strip(),
                generic_formula=self.formula_edit.text().strip() or None,
                brand_name=self.brand_edit.text().strip() or None,
                category_name=self.category_edit.text().strip() or None,
                manufacturer_name=self.manufacturer_edit.text().strip() or None,
                dosage_form=DosageForm(self.dosage_combo.currentText()),
                strength=self.strength_edit.text().strip() or None,
                pack_size=self.pack_size_edit.text().strip() or None,
                unit=self.base_unit_edit.text().strip() or None,
                base_unit=self.base_unit_edit.text().strip() or None,
                pack_unit=self.pack_unit_edit.text().strip() or None,
                units_per_pack=self.units_per_pack_spin.value(),
                barcode=self.barcode_edit.text().strip() or None,
                min_stock_level=self.min_stock_spin.value(),
                reorder_level=self.reorder_spin.value(),
                notes=self.notes_edit.text().strip() or None,
            )
        except ApplicationError as exc:
            QMessageBox.critical(self, "Could not add medicine", str(exc))
            return
        self.accept()


# ── Edit Medicine dialog ──────────────────────────────────────────────────

class EditMedicineDialog(QDialog):
    def __init__(self, medicine_id: int, parent=None) -> None:
        super().__init__(parent)
        self._medicine_id = medicine_id
        self.setWindowTitle("Edit Medicine")
        self.setMinimumWidth(500)
        layout = QFormLayout(self)

        try:
            detail = medicine_service.get_medicine_detail(medicine_id)
        except ApplicationError:
            detail = None

        def v(key, default=""):
            val = detail.get(key, default) if detail else default
            return str(val) if val is not None else ""

        self.name_edit        = QLineEdit(v("name"))
        self.formula_edit     = QLineEdit(v("generic_formula"))
        self.brand_edit       = QLineEdit(v("brand_name"))
        self.dosage_combo     = QComboBox()
        self.dosage_combo.addItems([f.value for f in DosageForm])
        if detail:
            idx = self.dosage_combo.findText(v("dosage_form"))
            if idx >= 0:
                self.dosage_combo.setCurrentIndex(idx)
        self.strength_edit    = QLineEdit(v("strength"))
        self.pack_size_edit   = QLineEdit(v("pack_size"))
        self.base_unit_edit   = QLineEdit(v("base_unit"))
        self.pack_unit_edit   = QLineEdit(v("pack_unit"))
        self.units_per_pack_spin = QSpinBox()
        self.units_per_pack_spin.setRange(1, 10_000)
        self.units_per_pack_spin.setValue(int(detail.get("units_per_pack") or 1) if detail else 1)
        self.barcode_edit     = QLineEdit(v("barcode"))
        self.min_stock_spin   = QSpinBox()
        self.min_stock_spin.setRange(0, 1_000_000)
        self.min_stock_spin.setValue(int(detail.get("min_stock_level") or 10) if detail else 10)
        self.notes_edit       = QLineEdit()

        layout.addRow("Name *",          self.name_edit)
        layout.addRow("Generic Formula", self.formula_edit)
        layout.addRow("Brand Name",      self.brand_edit)
        layout.addRow("Dosage Form",     self.dosage_combo)
        layout.addRow("Strength",        self.strength_edit)
        layout.addRow("Pack Size",       self.pack_size_edit)
        layout.addRow("Base Unit",       self.base_unit_edit)
        layout.addRow("Pack Unit",       self.pack_unit_edit)
        layout.addRow("Units per Pack",  self.units_per_pack_spin)
        layout.addRow("Barcode",         self.barcode_edit)
        layout.addRow("Min Stock Level", self.min_stock_spin)
        layout.addRow("Notes",           self.notes_edit)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._save)
        buttons.rejected.connect(self.reject)
        layout.addRow(buttons)

    def _save(self) -> None:
        if not self.name_edit.text().strip():
            QMessageBox.warning(self, "Missing field", "Medicine name is required.")
            return
        try:
            medicine_service.edit_medicine(
                self._medicine_id,
                name=self.name_edit.text().strip(),
                generic_formula=self.formula_edit.text().strip() or None,
                brand_name=self.brand_edit.text().strip() or None,
                dosage_form=DosageForm(self.dosage_combo.currentText()),
                strength=self.strength_edit.text().strip() or None,
                pack_size=self.pack_size_edit.text().strip() or None,
                unit=self.base_unit_edit.text().strip() or None,
                base_unit=self.base_unit_edit.text().strip() or None,
                pack_unit=self.pack_unit_edit.text().strip() or None,
                units_per_pack=self.units_per_pack_spin.value(),
                barcode=self.barcode_edit.text().strip() or None,
                min_stock_level=self.min_stock_spin.value(),
                notes=self.notes_edit.text().strip() or None,
            )
        except ApplicationError as exc:
            QMessageBox.critical(self, "Could not save changes", str(exc))
            return
        self.accept()


# ── Add Batch dialog ──────────────────────────────────────────────────────

class AddBatchDialog(QDialog):
    def __init__(self, medicine_id: int, medicine_name: str, parent=None) -> None:
        super().__init__(parent)
        self.medicine_id = medicine_id
        self.setWindowTitle(f"Add Batch — {medicine_name}")
        layout = QFormLayout(self)

        self.batch_number_edit   = QLineEdit()
        self.purchase_price_edit = QLineEdit()
        self.selling_price_edit  = QLineEdit()
        self.quantity_spin       = QSpinBox()
        self.quantity_spin.setRange(0, 1_000_000)
        self.expiry_edit = QDateEdit(calendarPopup=True)
        self.expiry_edit.setDate(date.today() + timedelta(days=365))
        self.wardrobe_edit = QLineEdit()
        self.rack_edit     = QLineEdit()
        self.shelf_edit    = QLineEdit()

        layout.addRow("Batch Number *",   self.batch_number_edit)
        layout.addRow("Purchase Price *", self.purchase_price_edit)
        layout.addRow("Selling Price *",  self.selling_price_edit)
        layout.addRow("Quantity *",       self.quantity_spin)
        layout.addRow("Expiry Date *",    self.expiry_edit)
        layout.addRow("Wardrobe",         self.wardrobe_edit)
        layout.addRow("Rack",             self.rack_edit)
        layout.addRow("Shelf",            self.shelf_edit)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._save)
        buttons.rejected.connect(self.reject)
        layout.addRow(buttons)

    def _save(self) -> None:
        try:
            purchase_price = float(self.purchase_price_edit.text())
            selling_price  = float(self.selling_price_edit.text())
        except ValueError:
            QMessageBox.warning(self, "Invalid input", "Prices must be numeric.")
            return
        if not self.batch_number_edit.text().strip():
            QMessageBox.warning(self, "Missing field", "Batch number is required.")
            return
        qt_date = self.expiry_edit.date()
        expiry = date(qt_date.year(), qt_date.month(), qt_date.day())
        try:
            medicine_service.add_manual_batch(
                medicine_id=self.medicine_id,
                batch_number=self.batch_number_edit.text().strip(),
                purchase_price=purchase_price,
                selling_price=selling_price,
                quantity=self.quantity_spin.value(),
                expiry_date=expiry,
                wardrobe_code=self.wardrobe_edit.text().strip() or None,
                rack_code=self.rack_edit.text().strip() or None,
                shelf_code=self.shelf_edit.text().strip() or None,
            )
        except ApplicationError as exc:
            QMessageBox.critical(self, "Could not add batch", str(exc))
            return
        self.accept()


# ── Medicines Page ────────────────────────────────────────────────────────

class MedicinesPage(QWidget):
    """
    Full-width table — 10 columns, all always visible.
    Clicking a row opens a MedicineDetailDialog popup.
    """

    # column indices  (Barcode removed)
    _C_ID      = 0
    _C_NAME    = 1
    _C_FORMULA = 2
    _C_BRAND   = 3
    _C_DOSAGE  = 4
    _C_STOCK   = 5
    _C_STATUS  = 6
    _C_MINSTK  = 7
    _C_ACTIONS = 8

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        root = QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(6)

        # ── Header ─────────────────────────────────────────────────────────
        header_row = QHBoxLayout()
        title = QLabel("Medicines")
        title.setStyleSheet("font-size: 18px; font-weight: 600;")
        header_row.addWidget(title)
        header_row.addStretch()
        add_btn = QPushButton("＋ Add Medicine")
        add_btn.setStyleSheet(
            "background-color: #27ae60; color: white; "
            "padding: 6px 16px; font-weight: 600; border-radius: 4px;"
        )
        add_btn.clicked.connect(self._add_medicine)
        header_row.addWidget(add_btn)
        root.addLayout(header_row)

        # ── Search ─────────────────────────────────────────────────────────
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText(
            "Search by name, formula, brand or barcode…"
        )
        self.search_edit.setClearButtonEnabled(True)
        self.search_edit.setStyleSheet("padding: 5px; font-size: 13px;")
        self._debounce = QTimer()
        self._debounce.setSingleShot(True)
        self._debounce.setInterval(300)
        self._debounce.timeout.connect(self.refresh)
        self.search_edit.textChanged.connect(self._on_search_changed)
        root.addWidget(self.search_edit)

        # ── Table — full width, 10 columns ─────────────────────────────────
        self.table = QTableWidget(0, 9)
        self.table.setHorizontalHeaderLabels([
            "ID", "Name", "Formula", "Brand", "Dosage Form",
            "Stock", "Status", "Min Stock", "Actions",
        ])

        hh = self.table.horizontalHeader()
        hh.setDefaultAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)

        # Interactive: user can drag column edges; Name stretches
        hh.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        hh.setStretchLastSection(False)

        # Set sensible default widths
        self.table.setColumnWidth(self._C_ID,      42)
        self.table.setColumnWidth(self._C_NAME,   175)
        self.table.setColumnWidth(self._C_FORMULA, 110)
        self.table.setColumnWidth(self._C_BRAND,   95)
        self.table.setColumnWidth(self._C_DOSAGE,  100)
        self.table.setColumnWidth(self._C_STOCK,    55)
        self.table.setColumnWidth(self._C_STATUS,  120)
        self.table.setColumnWidth(self._C_MINSTK,   78)
        # Actions: 4 × 72px + 3 × 4px gap = 300px
        self.table.setColumnWidth(self._C_ACTIONS, 308)

        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().setDefaultSectionSize(34)
        self.table.setShowGrid(True)
        self.table.setSortingEnabled(False)

        # Double-click row → detail popup
        self.table.doubleClicked.connect(self._on_row_double_clicked)

        root.addWidget(self.table, 1)

        # ── Row count label ─────────────────────────────────────────────────
        self._count_label = QLabel("")
        self._count_label.setStyleSheet("color: #888; font-size: 11px;")
        root.addWidget(self._count_label)

        self.refresh()

    # ── Search ────────────────────────────────────────────────────────────

    def _on_search_changed(self, text: str) -> None:
        self._debounce.stop()
        if not text.strip():
            self.refresh()   # immediate clear
        else:
            self._debounce.start()

    # ── Row double-click → detail dialog ──────────────────────────────────

    def _on_row_double_clicked(self, index) -> None:
        row = index.row()
        id_item = self.table.item(row, self._C_ID)
        if id_item is None:
            return
        try:
            mid = int(id_item.text())
        except ValueError:
            return
        MedicineDetailDialog(mid, self).exec()

    # ── CRUD ──────────────────────────────────────────────────────────────

    def _add_medicine(self) -> None:
        if AddMedicineDialog(self).exec() == QDialog.DialogCode.Accepted:
            self.refresh()

    def _edit_medicine(self, medicine_id: int) -> None:
        if EditMedicineDialog(medicine_id, self).exec() == QDialog.DialogCode.Accepted:
            self.refresh()

    def _add_batch(self, medicine_id: int, medicine_name: str) -> None:
        if AddBatchDialog(medicine_id, medicine_name, self).exec() == QDialog.DialogCode.Accepted:
            self.refresh()

    def _toggle_active(self, medicine_id: int, currently_active: bool) -> None:
        action = "deactivate" if currently_active else "reactivate"
        if QMessageBox.question(
            self,
            f"Confirm {action.title()}",
            f"Are you sure you want to {action} this medicine?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        ) != QMessageBox.StandardButton.Yes:
            return
        try:
            medicine_service.edit_medicine(medicine_id, is_active=not currently_active)
        except ApplicationError as exc:
            QMessageBox.critical(self, "Action failed", str(exc))
            return
        self.refresh()

    # ── Refresh ───────────────────────────────────────────────────────────

    def refresh(self) -> None:
        term = self.search_edit.text().strip()
        try:
            medicines = medicine_service.search_medicines(term)
        except ApplicationError as exc:
            QMessageBox.warning(self, "Cannot load medicines", str(exc))
            return

        self.table.setRowCount(0)
        bold = QFont()
        bold.setBold(True)

        for med in medicines:
            total_qty, status = _medicine_status(med)
            row = self.table.rowCount()
            self.table.insertRow(row)

            def cell(text: str, align=Qt.AlignmentFlag.AlignLeft) -> QTableWidgetItem:
                item = QTableWidgetItem(str(text))
                item.setTextAlignment(align | Qt.AlignmentFlag.AlignVCenter)
                return item

            center = Qt.AlignmentFlag.AlignCenter

            self.table.setItem(row, self._C_ID,      cell(str(med.id), center))
            self.table.setItem(row, self._C_NAME,    cell(med.name))
            self.table.setItem(row, self._C_FORMULA, cell(med.generic_formula or ""))
            self.table.setItem(row, self._C_BRAND,   cell(med.brand_name or ""))
            self.table.setItem(row, self._C_DOSAGE,  cell(
                med.dosage_form.value if med.dosage_form else "")
            )

            qty_item = cell(str(total_qty), center)
            self.table.setItem(row, self._C_STOCK, qty_item)

            st_item = QTableWidgetItem(status)
            st_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter | Qt.AlignmentFlag.AlignVCenter)
            st_item.setForeground(_STATUS_FG.get(status, Qt.GlobalColor.black))
            st_item.setFont(bold)
            self.table.setItem(row, self._C_STATUS, st_item)

            self.table.setItem(row, self._C_MINSTK,  cell(str(med.min_stock_level), center))

            # ── Actions ───────────────────────────────────────────────────
            actions_widget = QWidget()
            al = QHBoxLayout(actions_widget)
            al.setContentsMargins(4, 3, 4, 3)
            al.setSpacing(4)

            def _btn(label: str, colour: str = "") -> QPushButton:
                b = QPushButton(label)
                b.setFixedHeight(26)
                b.setFixedWidth(72)
                style = (
                    "font-size: 11px; padding: 0px; border-radius: 3px; "
                    "border: 1px solid rgba(0,0,0,0.15);"
                )
                if colour:
                    style += f" background-color: {colour}; color: white;"
                b.setStyleSheet(style)
                return b

            detail_btn = _btn("Detail", "#5d6d7e")
            detail_btn.setToolTip("View full batch & location detail (or double-click row)")
            detail_btn.clicked.connect(
                lambda _, mid=med.id: MedicineDetailDialog(mid, self).exec()
            )

            edit_btn = _btn("Edit", "#1a5276")
            edit_btn.clicked.connect(lambda _, mid=med.id: self._edit_medicine(mid))

            batch_btn = _btn("+ Batch", "#117a65")
            batch_btn.setToolTip("Add a new batch / stock entry")
            batch_btn.clicked.connect(
                lambda _, mid=med.id, mn=med.name: self._add_batch(mid, mn)
            )

            is_active = med.is_active
            toggle_label = "Deactivate" if is_active else "Reactivate"
            toggle_colour = "#922b21" if is_active else "#1e8449"
            toggle_btn = _btn(toggle_label, toggle_colour)
            toggle_btn.clicked.connect(
                lambda _, mid=med.id, a=is_active: self._toggle_active(mid, a)
            )

            al.addWidget(detail_btn)
            al.addWidget(edit_btn)
            al.addWidget(batch_btn)
            al.addWidget(toggle_btn)
            self.table.setCellWidget(row, self._C_ACTIONS, actions_widget)

        count = len(medicines)
        self._count_label.setText(
            f"{count} medicine{'s' if count != 1 else ''} found"
            + (" — double-click a row to see full batch & location detail" if count else "")
        )
