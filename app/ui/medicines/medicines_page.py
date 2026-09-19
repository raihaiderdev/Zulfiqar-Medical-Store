"""
Medicines page — full CRUD with live stock status and clean Update Stock dialog.
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


# ── Edit Batch Prices dialog ──────────────────────────────────────────────

class EditBatchDialog(QDialog):
    """Edit purchase price, selling price, expiry date of an existing batch."""

    def __init__(self, batch_id: int, batch_number: str,
                 medicine_name: str, parent=None) -> None:
        super().__init__(parent)
        self._batch_id = batch_id
        self.setWindowTitle(f"Edit Batch — {medicine_name}  [{batch_number}]")
        self.setMinimumWidth(420)
        layout = QFormLayout(self)

        try:
            detail = medicine_service.get_medicine_detail_by_batch(batch_id)
        except Exception:
            detail = None

        curr_buy  = f"{detail.get('purchase_price', 0.0):.2f}" if detail else ""
        curr_sell = f"{detail.get('selling_price',  0.0):.2f}" if detail else ""
        curr_exp  = detail.get("expiry_date", "")              if detail else ""
        curr_ward = detail.get("wardrobe", "")                 if detail else ""
        curr_rack = detail.get("rack", "")                     if detail else ""
        curr_shelf= detail.get("shelf", "")                    if detail else ""

        info = QLabel(
            f"<b>{medicine_name}</b>  —  Batch: <b>{batch_number}</b>"
        )
        info.setTextFormat(Qt.TextFormat.RichText)
        layout.addRow(info)

        self.purchase_price_edit = QLineEdit(curr_buy)
        layout.addRow("Purchase Price (Rs):", self.purchase_price_edit)

        self.selling_price_edit = QLineEdit(curr_sell)
        layout.addRow("Selling Price (Rs):", self.selling_price_edit)

        self.expiry_edit = QDateEdit(calendarPopup=True)
        if curr_exp:
            try:
                from datetime import datetime as _dt
                self.expiry_edit.setDate(_dt.strptime(curr_exp, "%Y-%m-%d").date())
            except Exception:
                self.expiry_edit.setDate(date.today() + timedelta(days=365))
        else:
            self.expiry_edit.setDate(date.today() + timedelta(days=365))
        layout.addRow("Expiry Date:", self.expiry_edit)

        layout.addRow(QLabel("Location (leave blank to keep current):"))
        self.wardrobe_edit = QLineEdit(curr_ward)
        self.rack_edit     = QLineEdit(curr_rack)
        self.shelf_edit    = QLineEdit(curr_shelf)
        layout.addRow("Wardrobe:", self.wardrobe_edit)
        layout.addRow("Rack:",     self.rack_edit)
        layout.addRow("Shelf:",    self.shelf_edit)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._save)
        buttons.rejected.connect(self.reject)
        layout.addRow(buttons)

    def _save(self) -> None:
        buy_text  = self.purchase_price_edit.text().strip()
        sell_text = self.selling_price_edit.text().strip()
        new_buy = new_sell = None
        if buy_text:
            try:
                new_buy = float(buy_text)
            except ValueError:
                QMessageBox.warning(self, "Invalid price", f"'{buy_text}' is not valid.")
                return
        if sell_text:
            try:
                new_sell = float(sell_text)
            except ValueError:
                QMessageBox.warning(self, "Invalid price", f"'{sell_text}' is not valid.")
                return

        qt_date    = self.expiry_edit.date()
        new_expiry = date(qt_date.year(), qt_date.month(), qt_date.day())

        # Warn if the new expiry date is still in the past
        if new_expiry < date.today():
            answer = QMessageBox.warning(
                self, "Expiry date is in the past",
                f"The expiry date you entered ({new_expiry.isoformat()}) is already past.\n\n"
                "This batch will still appear as EXPIRED.\n"
                "Did you mean to set a future date?",
                QMessageBox.StandardButton.Ok | QMessageBox.StandardButton.Cancel,
            )
            if answer == QMessageBox.StandardButton.Cancel:
                return
        w = self.wardrobe_edit.text().strip()
        r = self.rack_edit.text().strip()
        s = self.shelf_edit.text().strip()

        try:
            medicine_service.edit_batch(
                batch_id=self._batch_id,
                purchase_price=new_buy,
                selling_price=new_sell,
                expiry_date=new_expiry,
                wardrobe_code=w or None,
                rack_code=r or None,
                shelf_code=s or None,
            )
        except ApplicationError as exc:
            QMessageBox.critical(self, "Could not update batch", str(exc))
            return

        QMessageBox.information(self, "Batch Updated ✔",
                                "Prices, expiry and location saved.")
        self.accept()


# ── Medicine Detail Dialog ────────────────────────────────────────────────

class MedicineDetailDialog(QDialog):
    """Full detail view — shows batch table with Edit Prices button per row."""

    def __init__(self, medicine_id: int, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Medicine Detail")
        self.setMinimumSize(860, 520)
        self._medicine_id   = medicine_id
        self._medicine_name = ""
        layout = QVBoxLayout(self)

        from app.ui.common.medicine_search_widget import MedicineSearchWidget
        self._widget = MedicineSearchWidget(self, show_detail=True)
        self._widget.search_edit.setVisible(False)
        self._widget.results_list.setVisible(False)
        self._widget._load_detail(medicine_id)
        layout.addWidget(self._widget, 1)

        try:
            detail = medicine_service.get_medicine_detail(medicine_id)
            self._medicine_name = detail.get("name", "")
            self._inject_edit_buttons(detail)
        except Exception:
            pass

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        close_btn = QPushButton("Close")
        close_btn.setStyleSheet("padding: 6px 18px;")
        close_btn.clicked.connect(self.accept)
        btn_row.addWidget(close_btn)
        layout.addLayout(btn_row)

    def _inject_edit_buttons(self, detail: dict) -> None:
        table   = self._widget._batch_table
        batches = detail.get("batches", [])
        if not batches:
            return
        col = table.columnCount()
        table.setColumnCount(col + 1)
        table.setHorizontalHeaderItem(col, QTableWidgetItem("Edit Prices"))
        for row_idx, b in enumerate(batches):
            btn = QPushButton("✏ Edit Prices")
            btn.setFixedHeight(24)
            btn.setStyleSheet(
                "font-size: 11px; padding: 1px 8px; "
                "background-color: #d35400; color: white; border-radius: 3px;"
            )
            btn.clicked.connect(
                lambda _, bid=b["batch_id"], bnum=b["batch_number"]:
                    self._open_edit_batch(bid, bnum)
            )
            cell = QWidget()
            cl = QHBoxLayout(cell)
            cl.setContentsMargins(2, 1, 2, 1)
            cl.addWidget(btn)
            table.setCellWidget(row_idx, col, cell)
        table.resizeColumnsToContents()

    def _open_edit_batch(self, batch_id: int, batch_number: str) -> None:
        dlg = EditBatchDialog(batch_id, batch_number, self._medicine_name, self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            try:
                self._widget._load_detail(self._medicine_id)
                self._inject_edit_buttons(
                    medicine_service.get_medicine_detail(self._medicine_id)
                )
            except Exception:
                pass


# ── Add Medicine dialog ───────────────────────────────────────────────────

class AddMedicineDialog(QDialog):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Add Medicine")
        self.setMinimumWidth(500)
        layout = QFormLayout(self)

        self.name_edit           = QLineEdit()
        self.formula_edit        = QLineEdit()
        self.brand_edit          = QLineEdit()
        self.category_edit       = QLineEdit()
        self.manufacturer_edit   = QLineEdit()
        self.dosage_combo        = QComboBox()
        self.dosage_combo.addItems([f.value for f in DosageForm])
        self.strength_edit       = QLineEdit()
        self.pack_size_edit      = QLineEdit()
        self.base_unit_edit      = QLineEdit()
        self.base_unit_edit.setPlaceholderText("e.g. Tablet, Capsule, mL")
        self.pack_unit_edit      = QLineEdit()
        self.pack_unit_edit.setPlaceholderText("e.g. Strip, Box  (leave blank if N/A)")
        self.units_per_pack_spin = QSpinBox()
        self.units_per_pack_spin.setRange(1, 10_000)
        self.units_per_pack_spin.setValue(1)
        self.barcode_edit        = QLineEdit()
        self.min_stock_spin      = QSpinBox()
        self.min_stock_spin.setRange(0, 1_000_000)
        self.min_stock_spin.setValue(10)
        self.reorder_spin        = QSpinBox()
        self.reorder_spin.setRange(0, 1_000_000)
        self.reorder_spin.setValue(20)
        self.notes_edit          = QLineEdit()

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

        self.name_edit           = QLineEdit(v("name"))
        self.formula_edit        = QLineEdit(v("generic_formula"))
        self.brand_edit          = QLineEdit(v("brand_name"))
        self.dosage_combo        = QComboBox()
        self.dosage_combo.addItems([f.value for f in DosageForm])
        if detail:
            idx = self.dosage_combo.findText(v("dosage_form"))
            if idx >= 0:
                self.dosage_combo.setCurrentIndex(idx)
        self.strength_edit       = QLineEdit(v("strength"))
        self.pack_size_edit      = QLineEdit(v("pack_size"))
        self.base_unit_edit      = QLineEdit(v("base_unit"))
        self.pack_unit_edit      = QLineEdit(v("pack_unit"))
        self.units_per_pack_spin = QSpinBox()
        self.units_per_pack_spin.setRange(1, 10_000)
        self.units_per_pack_spin.setValue(int(detail.get("units_per_pack") or 1) if detail else 1)
        self.barcode_edit        = QLineEdit(v("barcode"))
        self.min_stock_spin      = QSpinBox()
        self.min_stock_spin.setRange(0, 1_000_000)
        self.min_stock_spin.setValue(int(detail.get("min_stock_level") or 10) if detail else 10)
        self.notes_edit          = QLineEdit()

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


# ── Update Stock dialog ───────────────────────────────────────────────────

class AddBatchDialog(QDialog):
    """
    Update Stock dialog.

    Shows:
      1. Medicine name + total stock (header)
      2. Table of existing batches — CLICK A ROW to select it
      3. Fields pre-filled: Qty to Add, Buy Price, Sell Price, Expiry Date
      4. One green "Update Stock" button

    Clean, no tabs, no dropdown, no clutter.
    """

    def __init__(self, medicine_id: int, medicine_name: str, parent=None) -> None:
        super().__init__(parent)
        self.medicine_id   = medicine_id
        self.medicine_name = medicine_name
        self._batches: list[dict] = []
        self._selected_row = -1
        self._mode = "update"            # "update" or "add_first"
        self._stock_op_mode = "add"      # "add" or "set"

        self.setWindowTitle(f"Update Stock — {medicine_name}")
        self.setMinimumWidth(700)
        self.setMinimumHeight(600)
        self.resize(740, 650)

        root = QVBoxLayout(self)
        root.setSpacing(14)
        root.setContentsMargins(18, 16, 18, 16)

        # ── 1. Medicine header ─────────────────────────────────────────────
        self._header_label = QLabel()
        self._header_label.setStyleSheet(
            "font-size: 15px; font-weight: 700; color: #154c89; "
            "padding: 8px 12px; background: #eaf4fb; "
            "border-radius: 6px; border: 1px solid #aed6f1;"
        )
        self._header_label.setTextFormat(Qt.TextFormat.RichText)
        root.addWidget(self._header_label)

        # ── 2. Existing batches table ──────────────────────────────────────
        self._lbl_select_batch = QLabel("Click a row below to select the batch you want to update:")
        self._lbl_select_batch.setStyleSheet("font-weight: 600; font-size: 13px; color: #333;")
        root.addWidget(self._lbl_select_batch)

        self._batch_table = QTableWidget(0, 5)
        self._batch_table.setHorizontalHeaderLabels([
            "Batch Number", "Current Stock", "Buy Price (Rs)",
            "Sell Price (Rs)", "Expiry Date"
        ])
        hh = self._batch_table.horizontalHeader()
        hh.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        for c in range(1, 5):
            hh.setSectionResizeMode(c, QHeaderView.ResizeMode.ResizeToContents)
        self._batch_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._batch_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._batch_table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self._batch_table.setAlternatingRowColors(True)
        self._batch_table.setMinimumHeight(150)
        self._batch_table.setMaximumHeight(200)
        self._batch_table.itemSelectionChanged.connect(self._on_row_selected)
        root.addWidget(self._batch_table)

        # ── 3. Divider ─────────────────────────────────────────────────────
        self._divider = QWidget()
        self._divider.setFixedHeight(1)
        self._divider.setStyleSheet("background: #ccc;")
        root.addWidget(self._divider)

        # ── 4. Edit fields ─────────────────────────────────────────────────
        self._lbl_fields = QLabel("Fields below are pre-filled from the selected batch — edit as needed:")
        self._lbl_fields.setStyleSheet("font-weight: 600; font-size: 13px; color: #333;")
        root.addWidget(self._lbl_fields)

        form = QFormLayout()
        form.setHorizontalSpacing(20)
        form.setVerticalSpacing(12)

        # Batch number field — only shown in "add_first" mode
        self._batch_number_lbl = QLabel("Batch Number *:")
        self._batch_number_lbl.setVisible(False)
        self._batch_number_edit = QLineEdit()
        self._batch_number_edit.setMinimumHeight(34)
        self._batch_number_edit.setStyleSheet("font-size: 13px;")
        self._batch_number_edit.setPlaceholderText("e.g. B-001  (from the medicine box)")
        self._batch_number_edit.setVisible(False)
        form.addRow(self._batch_number_lbl, self._batch_number_edit)

        self._qty_spin = QSpinBox()
        self._qty_spin.setRange(0, 1_000_000)
        self._qty_spin.setValue(1)
        self._qty_spin.setMinimumHeight(34)
        self._qty_spin.setStyleSheet("font-size: 13px;")
        self._qty_spin.valueChanged.connect(self._update_stock_preview)
        form.addRow("Quantity *:", self._qty_spin)

        # ── Stock operation mode ───────────────────────────────────────────
        # Two clear buttons: "Add to Stock" (increase) or "Set Stock To" (overwrite)
        mode_widget = QWidget()
        mode_layout = QHBoxLayout(mode_widget)
        mode_layout.setContentsMargins(0, 0, 0, 0)
        mode_layout.setSpacing(8)

        self._btn_add_mode = QPushButton("➕  Add to existing stock")
        self._btn_add_mode.setCheckable(True)
        self._btn_add_mode.setChecked(True)
        self._btn_add_mode.setMinimumHeight(30)
        self._btn_add_mode.setStyleSheet(
            "QPushButton { font-size: 12px; padding: 3px 12px; border-radius: 4px; "
            "border: 2px solid #27ae60; }"
            "QPushButton:checked { background: #27ae60; color: white; font-weight: 700; }"
            "QPushButton:!checked { background: white; color: #27ae60; }"
        )
        self._btn_set_mode = QPushButton("📋  Set stock to exact number")
        self._btn_set_mode.setCheckable(True)
        self._btn_set_mode.setChecked(False)
        self._btn_set_mode.setMinimumHeight(30)
        self._btn_set_mode.setStyleSheet(
            "QPushButton { font-size: 12px; padding: 3px 12px; border-radius: 4px; "
            "border: 2px solid #2980b9; }"
            "QPushButton:checked { background: #2980b9; color: white; font-weight: 700; }"
            "QPushButton:!checked { background: white; color: #2980b9; }"
        )
        self._btn_add_mode.clicked.connect(lambda: self._set_stock_op_mode("add"))
        self._btn_set_mode.clicked.connect(lambda: self._set_stock_op_mode("set"))
        mode_layout.addWidget(self._btn_add_mode)
        mode_layout.addWidget(self._btn_set_mode)
        mode_layout.addStretch()
        form.addRow("Stock Operation:", mode_widget)

        # Live result preview
        self._stock_preview_lbl = QLabel("")
        self._stock_preview_lbl.setStyleSheet(
            "font-size: 13px; font-weight: 700; color: #154c89; padding: 4px 0;"
        )
        form.addRow("Result:", self._stock_preview_lbl)

        self._buy_edit = QLineEdit()
        self._buy_edit.setMinimumHeight(34)
        self._buy_edit.setStyleSheet("font-size: 13px;")
        form.addRow("Purchase Price (Rs):", self._buy_edit)

        self._sell_edit = QLineEdit()
        self._sell_edit.setMinimumHeight(34)
        self._sell_edit.setStyleSheet("font-size: 13px;")
        form.addRow("Selling Price (Rs):", self._sell_edit)

        self._expiry_edit = QDateEdit(calendarPopup=True)
        self._expiry_edit.setMinimumHeight(34)
        self._expiry_edit.setStyleSheet("font-size: 13px;")
        self._expiry_edit.setDate(date.today() + timedelta(days=365))
        form.addRow("Expiry Date:", self._expiry_edit)

        root.addLayout(form)

        # ── 5. Status / info label ─────────────────────────────────────────
        self._status_lbl = QLabel(
            "ℹ  No batch selected — click a row in the table above."
        )
        self._status_lbl.setStyleSheet("color: #888; font-size: 12px;")
        self._status_lbl.setWordWrap(True)
        root.addWidget(self._status_lbl)

        root.addStretch()

        # ── 6. Buttons ─────────────────────────────────────────────────────
        btn_row = QHBoxLayout()

        cancel_btn = QPushButton("Cancel")
        cancel_btn.setMinimumHeight(42)
        cancel_btn.setStyleSheet("font-size: 13px; padding: 6px 20px; border-radius: 5px;")
        cancel_btn.clicked.connect(self.reject)

        self._update_btn = QPushButton("➕  Update Stock")
        self._update_btn.setMinimumHeight(42)
        self._update_btn.setStyleSheet(
            "background-color: #27ae60; color: white; font-weight: 700; "
            "font-size: 14px; padding: 6px 28px; border-radius: 5px;"
        )
        self._update_btn.setEnabled(False)
        self._update_btn.clicked.connect(self._save)

        btn_row.addStretch()
        btn_row.addWidget(cancel_btn)
        btn_row.addWidget(self._update_btn)
        root.addLayout(btn_row)

        self._load_medicine()

    # ── Load ──────────────────────────────────────────────────────────────

    def _load_medicine(self) -> None:
        try:
            detail = medicine_service.get_medicine_detail(self.medicine_id)
        except Exception:
            self._header_label.setText(f"<b>{self.medicine_name}</b>")
            return

        total  = detail.get("total_stock", 0)
        unit   = detail.get("base_unit") or "units"
        status = detail.get("overall_status", "")
        col    = {"IN STOCK": "#1e8449", "LOW STOCK": "#d35400",
                  "OUT OF STOCK": "#922b21"}.get(status, "#333")

        self._header_label.setText(
            f"<b>{detail['name']}</b>"
            + (f" — {detail['dosage_form']}" if detail.get("dosage_form") else "")
            + (f" ({detail['strength']})" if detail.get("strength") else "")
            + f"&nbsp;&nbsp;&nbsp;"
            f"<span style='color:{col}; font-size:15px; font-weight:700;'>"
            f"Total Stock: {total} {unit}</span>"
            + f"&nbsp;&nbsp;"
            f"<span style='background:{col}; color:white; padding:2px 10px; "
            f"border-radius:4px; font-size:12px;'>{status}</span>"
        )

        self._batches = detail.get("batches", [])

        # ── No batches yet → switch to "Add First Batch" mode ─────────────
        if not self._batches:
            self._switch_to_add_first_batch_mode()
            return

        # ── Has batches → normal Update Stock mode ─────────────────────────
        self._batch_table.setRowCount(0)
        for b in self._batches:
            row = self._batch_table.rowCount()
            self._batch_table.insertRow(row)
            self._batch_table.setItem(row, 0, QTableWidgetItem(b["batch_number"]))
            qty_item = QTableWidgetItem(str(b["quantity"]))
            qty_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter | Qt.AlignmentFlag.AlignVCenter)
            if b["quantity"] <= 0:
                qty_item.setForeground(Qt.GlobalColor.red)
            self._batch_table.setItem(row, 1, qty_item)
            for col_idx, key in enumerate(["purchase_price", "selling_price"], start=2):
                it = QTableWidgetItem(f"{b[key]:.2f}")
                it.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                self._batch_table.setItem(row, col_idx, it)
            self._batch_table.setItem(row, 4, QTableWidgetItem(b["expiry_date"]))

        # Auto-select if only one batch
        if len(self._batches) == 1:
            self._batch_table.selectRow(0)

    def _switch_to_add_first_batch_mode(self) -> None:
        """
        Called when the medicine has NO batches yet.
        Hides the batch-selection table and shows a simple 'Add First Batch' form.
        """
        # Hide the batch table section
        self._batch_table.setVisible(False)
        self._lbl_select_batch.setVisible(False)
        self._divider.setVisible(False)
        self._lbl_fields.setText("Enter the first batch details:")

        # Show the batch number field
        self._batch_number_edit.setVisible(True)
        self._batch_number_lbl.setVisible(True)

        # Show a clear info banner
        self._status_lbl.setText(
            "⚠  This medicine has <b>no batches yet</b>.<br>"
            "Fill in the details below to add the first batch and set the initial stock."
        )
        self._status_lbl.setTextFormat(Qt.TextFormat.RichText)
        self._status_lbl.setStyleSheet(
            "color: #856404; background: #fff3cd; padding: 8px 10px; "
            "border-radius: 5px; border: 1px solid #ffc107; font-size: 12px;"
        )

        # Change button
        self._update_btn.setText("✚  Add First Batch")
        self._update_btn.setStyleSheet(
            "background-color: #154c89; color: white; font-weight: 700; "
            "font-size: 14px; padding: 6px 28px; border-radius: 5px;"
        )
        self._update_btn.setEnabled(True)
        self._mode = "add_first"

    def _switch_to_add_first_batch_mode(self) -> None:
        """Called when the medicine has NO batches yet."""
        self._batch_table.setVisible(False)
        self._lbl_select_batch.setVisible(False)
        self._divider.setVisible(False)
        self._lbl_fields.setText("Enter the first batch details:")
        self._batch_number_edit.setVisible(True)
        self._batch_number_lbl.setVisible(True)
        self._status_lbl.setText(
            "⚠  This medicine has <b>no batches yet</b>.<br>"
            "Fill in the details below to add the first batch and set the initial stock."
        )
        self._status_lbl.setTextFormat(Qt.TextFormat.RichText)
        self._status_lbl.setStyleSheet(
            "color: #856404; background: #fff3cd; padding: 8px 10px; "
            "border-radius: 5px; border: 1px solid #ffc107; font-size: 12px;"
        )
        self._update_btn.setText("✚  Add First Batch")
        self._update_btn.setStyleSheet(
            "background-color: #154c89; color: white; font-weight: 700; "
            "font-size: 14px; padding: 6px 28px; border-radius: 5px;"
        )
        self._update_btn.setEnabled(True)
        self._mode = "add_first"

    # ── Stock operation mode toggle ────────────────────────────────────────

    def _set_stock_op_mode(self, mode: str) -> None:
        """mode = 'add'  (add qty to existing) or 'set' (overwrite to exact number)."""
        self._stock_op_mode = mode
        self._btn_add_mode.setChecked(mode == "add")
        self._btn_set_mode.setChecked(mode == "set")
        if mode == "add":
            self._qty_spin.setRange(1, 1_000_000)
            if self._qty_spin.value() < 1:
                self._qty_spin.setValue(1)
        else:
            self._qty_spin.setRange(0, 1_000_000)
        self._update_stock_preview()

    def _update_stock_preview(self) -> None:
        """Show a live 'After update: X units' label so the user knows the result."""
        if self._selected_row < 0 or self._selected_row >= len(self._batches):
            self._stock_preview_lbl.setText("")
            return
        b           = self._batches[self._selected_row]
        current     = b["quantity"]
        qty         = self._qty_spin.value()
        op          = getattr(self, "_stock_op_mode", "add")
        if op == "add":
            result  = current + qty
            arrow   = f"{current}  ＋  {qty}  →  {result}"
        else:
            result  = qty
            arrow   = f"{current}  →  {result}  (set directly)"
        colour = "#1e8449" if result > 0 else "#922b21"
        self._stock_preview_lbl.setText(
            f"<span style='color:{colour}; font-size:13px; font-weight:700;'>"
            f"{arrow} units</span>"
        )
        self._stock_preview_lbl.setTextFormat(Qt.TextFormat.RichText)

    # ── Row selected → pre-fill ────────────────────────────────────────────

    def _on_row_selected(self) -> None:
        row = self._batch_table.currentRow()
        if row < 0 or row >= len(self._batches):
            self._selected_row = -1
            self._update_btn.setEnabled(False)
            self._status_lbl.setText("ℹ  No batch selected — click a row in the table above.")
            self._status_lbl.setStyleSheet("color: #888; font-size: 12px;")
            return

        self._selected_row = row
        b = self._batches[row]

        self._buy_edit.setText(f"{b['purchase_price']:.2f}")
        self._sell_edit.setText(f"{b['selling_price']:.2f}")
        try:
            from datetime import datetime as _dt
            self._expiry_edit.setDate(_dt.strptime(b["expiry_date"], "%Y-%m-%d").date())
        except Exception:
            pass

        self._status_lbl.setText(
            f"✔  <b>Batch {b['batch_number']}</b> selected  —  "
            f"Current Stock: <b>{b['quantity']}</b> units"
        )
        self._status_lbl.setTextFormat(Qt.TextFormat.RichText)
        self._status_lbl.setStyleSheet("color: #1e8449; font-size: 12px; font-weight: 600;")
        self._update_btn.setEnabled(True)
        self._update_stock_preview()

    # ── Save ──────────────────────────────────────────────────────────────

    def _save(self) -> None:
        # ── Mode: Add First Batch (no batches exist) ───────────────────────
        if self._mode == "add_first":
            batch_num = self._batch_number_edit.text().strip()
            if not batch_num:
                QMessageBox.warning(self, "Missing field", "Batch number is required.")
                return

            buy_text  = self._buy_edit.text().strip()
            sell_text = self._sell_edit.text().strip()
            if not buy_text or not sell_text:
                QMessageBox.warning(self, "Missing fields",
                                    "Purchase price and selling price are required.")
                return
            try:
                new_buy  = float(buy_text)
                new_sell = float(sell_text)
            except ValueError:
                QMessageBox.warning(self, "Invalid price", "Prices must be numeric.")
                return

            qty    = self._qty_spin.value()
            qt_d   = self._expiry_edit.date()
            expiry = date(qt_d.year(), qt_d.month(), qt_d.day())

            try:
                medicine_service.add_manual_batch(
                    medicine_id=self.medicine_id,
                    batch_number=batch_num,
                    purchase_price=new_buy,
                    selling_price=new_sell,
                    quantity=qty,
                    expiry_date=expiry,
                )
            except ApplicationError as exc:
                QMessageBox.critical(self, "Could not add batch", str(exc))
                return

            QMessageBox.information(
                self, "✔  Batch Added",
                f"Batch '{batch_num}' added successfully.\n"
                f"Initial Stock: {qty} units\n"
                f"Selling Price: Rs {new_sell:.2f}\n"
                f"Expiry: {expiry.isoformat()}"
            )
            self.accept()
            return

        # ── Mode: Update existing batch ────────────────────────────────────
        if self._selected_row < 0 or self._selected_row >= len(self._batches):
            QMessageBox.warning(self, "No batch selected",
                                "Click a batch row above first.")
            return

        b            = self._batches[self._selected_row]
        batch_id     = b["batch_id"]
        batch_number = b["batch_number"]
        old_qty      = b["quantity"]
        qty          = self._qty_spin.value()

        new_buy = new_sell = None
        for text, name in [(self._buy_edit.text().strip(),  "purchase price"),
                           (self._sell_edit.text().strip(), "selling price")]:
            if text:
                try:
                    val = float(text)
                    if name == "purchase price":
                        new_buy = val
                    else:
                        new_sell = val
                except ValueError:
                    QMessageBox.warning(self, "Invalid price",
                                        f"'{text}' is not a valid {name}.")
                    return

        qt_d       = self._expiry_edit.date()
        new_expiry = date(qt_d.year(), qt_d.month(), qt_d.day())

        # Warn if expiry is still in the past
        if new_expiry < date.today():
            answer = QMessageBox.warning(
                self, "Expiry date is in the past",
                f"The date {new_expiry.isoformat()} has already passed.\n"
                "This batch will still appear as EXPIRED.\n\n"
                "Did you mean to enter a future date?",
                QMessageBox.StandardButton.Ok | QMessageBox.StandardButton.Cancel,
            )
            if answer == QMessageBox.StandardButton.Cancel:
                return

        expiry_changed = new_expiry.isoformat() != b["expiry_date"]

        changes: list[str] = []

        if new_buy or new_sell or expiry_changed:
            try:
                medicine_service.edit_batch(
                    batch_id=batch_id,
                    purchase_price=new_buy,
                    selling_price=new_sell,
                    expiry_date=new_expiry if expiry_changed else None,
                )
                if new_buy:        changes.append(f"Buy price → Rs {new_buy:.2f}")
                if new_sell:       changes.append(f"Sell price → Rs {new_sell:.2f}")
                if expiry_changed: changes.append(f"Expiry → {new_expiry.isoformat()}")
            except ApplicationError as exc:
                QMessageBox.critical(self, "Could not update", str(exc))
                return

        # ── Apply stock change based on mode ──────────────────────────────
        op = self._stock_op_mode
        if op == "add":
            # Add qty on top of existing stock
            try:
                medicine_service.add_stock_to_existing_batch(
                    medicine_id=self.medicine_id,
                    batch_number=batch_number,
                    quantity=qty,
                )
            except ApplicationError as exc:
                QMessageBox.critical(self, "Could not update stock", str(exc))
                return
            new_qty = old_qty + qty
            stock_msg = (
                f"Previous Stock: {old_qty} units\n"
                f"Added:          +{qty} units\n"
                f"New Stock:      {new_qty} units"
            )
        else:
            # Set stock to exact number — compute the delta needed
            delta = qty - old_qty
            if delta == 0:
                # Nothing to do for quantity
                new_qty = old_qty
                stock_msg = f"Stock unchanged: {old_qty} units"
            else:
                try:
                    from app.services import returns_service
                    returns_service.adjust_stock(
                        batch_id=batch_id,
                        delta=delta,
                        reason=f"Manual stock correction: set to {qty} (was {old_qty})",
                    )
                except ApplicationError as exc:
                    QMessageBox.critical(self, "Could not set stock", str(exc))
                    return
                new_qty = qty
                direction = f"+{delta}" if delta > 0 else str(delta)
                stock_msg = (
                    f"Previous Stock: {old_qty} units\n"
                    f"Adjustment:     {direction} units\n"
                    f"New Stock:      {new_qty} units"
                )

        msg = f"Batch: {batch_number}\n{stock_msg}"
        if changes:
            msg += "\n\nAlso updated:\n" + "\n".join(f"  • {c}" for c in changes)

        QMessageBox.information(self, "✔  Stock Updated", msg)
        self.accept()


# ── Medicines Page ────────────────────────────────────────────────────────

class MedicinesPage(QWidget):
    """Full-width table. Double-click a row for detail. + Batch opens Update Stock dialog."""

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

        # ── Table ──────────────────────────────────────────────────────────
        self.table = QTableWidget(0, 9)
        self.table.setHorizontalHeaderLabels([
            "ID", "Name", "Formula", "Brand", "Dosage Form",
            "Stock", "Status", "Min Stock", "Actions",
        ])
        hh = self.table.horizontalHeader()
        hh.setDefaultAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        hh.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        hh.setStretchLastSection(False)

        self.table.setColumnWidth(self._C_ID,       42)
        self.table.setColumnWidth(self._C_NAME,    175)
        self.table.setColumnWidth(self._C_FORMULA,  110)
        self.table.setColumnWidth(self._C_BRAND,     95)
        self.table.setColumnWidth(self._C_DOSAGE,   100)
        self.table.setColumnWidth(self._C_STOCK,     55)
        self.table.setColumnWidth(self._C_STATUS,   120)
        self.table.setColumnWidth(self._C_MINSTK,    78)
        self.table.setColumnWidth(self._C_ACTIONS,  308)

        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().setDefaultSectionSize(34)
        self.table.doubleClicked.connect(self._on_row_double_clicked)
        root.addWidget(self.table, 1)

        self._count_label = QLabel("")
        self._count_label.setStyleSheet("color: #888; font-size: 11px;")
        root.addWidget(self._count_label)

        self.refresh()

    # ── Search ────────────────────────────────────────────────────────────

    def _on_search_changed(self, text: str) -> None:
        self._debounce.stop()
        if not text.strip():
            self.refresh()
        else:
            self._debounce.start()

    def _on_row_double_clicked(self, index) -> None:
        id_item = self.table.item(index.row(), self._C_ID)
        if id_item:
            try:
                MedicineDetailDialog(int(id_item.text()), self).exec()
            except ValueError:
                pass

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
            self, f"Confirm {action.title()}",
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

            ctr = Qt.AlignmentFlag.AlignCenter

            self.table.setItem(row, self._C_ID,      cell(str(med.id), ctr))
            self.table.setItem(row, self._C_NAME,    cell(med.name))
            self.table.setItem(row, self._C_FORMULA, cell(med.generic_formula or ""))
            self.table.setItem(row, self._C_BRAND,   cell(med.brand_name or ""))
            self.table.setItem(row, self._C_DOSAGE,  cell(
                med.dosage_form.value if med.dosage_form else ""))
            self.table.setItem(row, self._C_STOCK,   cell(str(total_qty), ctr))

            st_item = QTableWidgetItem(status)
            st_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter | Qt.AlignmentFlag.AlignVCenter)
            st_item.setForeground(_STATUS_FG.get(status, Qt.GlobalColor.black))
            st_item.setFont(bold)
            self.table.setItem(row, self._C_STATUS, st_item)

            self.table.setItem(row, self._C_MINSTK, cell(str(med.min_stock_level), ctr))

            # ── Actions ───────────────────────────────────────────────────
            aw = QWidget()
            al = QHBoxLayout(aw)
            al.setContentsMargins(4, 3, 4, 3)
            al.setSpacing(4)

            def _btn(label: str, colour: str = "") -> QPushButton:
                b = QPushButton(label)
                b.setFixedHeight(26)
                b.setFixedWidth(72)
                s = ("font-size: 11px; padding: 0px; border-radius: 3px; "
                     "border: 1px solid rgba(0,0,0,0.15);")
                if colour:
                    s += f" background-color: {colour}; color: white;"
                b.setStyleSheet(s)
                return b

            det_btn = _btn("Detail", "#5d6d7e")
            det_btn.setToolTip("View full detail (or double-click row)")
            det_btn.clicked.connect(
                lambda _, mid=med.id: MedicineDetailDialog(mid, self).exec()
            )

            edt_btn = _btn("Edit", "#1a5276")
            edt_btn.clicked.connect(
                lambda _, mid=med.id: self._edit_medicine(mid)
            )

            bat_btn = _btn("+ Batch", "#117a65")
            bat_btn.setToolTip("Update stock / add new batch")
            bat_btn.clicked.connect(
                lambda _, mid=med.id, mn=med.name: self._add_batch(mid, mn)
            )

            is_active = med.is_active
            tog_btn = _btn("Deactivate" if is_active else "Reactivate",
                           "#922b21" if is_active else "#1e8449")
            tog_btn.clicked.connect(
                lambda _, mid=med.id, a=is_active: self._toggle_active(mid, a)
            )

            al.addWidget(det_btn)
            al.addWidget(edt_btn)
            al.addWidget(bat_btn)
            al.addWidget(tog_btn)
            self.table.setCellWidget(row, self._C_ACTIONS, aw)

        count = len(medicines)
        self._count_label.setText(
            f"{count} medicine{'s' if count != 1 else ''} found"
            + (" — double-click a row to see full batch & location detail" if count else "")
        )
