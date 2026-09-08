"""
Shared smart medicine search widget (Features 4, 7, 8).

MedicineSearchWidget provides:
  • Debounced prefix-aware search as you type (textChanged).
  • Dropdown popup with highlighted matches and keyboard navigation.
  • Auto-clears results when the search field is emptied (F8 fix).
  • Emits `medicine_selected(medicine_id, medicine_name)` signal.
  • Optional detail panel below the search bar showing complete batch
    information for the selected medicine (F7).

Usage:
    widget = MedicineSearchWidget(show_detail=True)
    widget.medicine_selected.connect(my_slot)
    layout.addWidget(widget)
"""
from __future__ import annotations

from PySide6.QtCore import QTimer, Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QAbstractItemView,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QSizePolicy,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.utils.exceptions import ApplicationError


class MedicineSearchWidget(QWidget):
    """
    Self-contained search-bar + dropdown + optional detail panel.
    """

    medicine_selected = Signal(int, str)  # (medicine_id, medicine_name)

    _STATUS_COLOURS = {
        "IN STOCK": "#27ae60",
        "LOW STOCK": "#f39c12",
        "OUT OF STOCK": "#e74c3c",
        "EXPIRING SOON": "#e67e22",
        "EXPIRING VERY SOON": "#c0392b",
        "EXPIRED": "#8e1010",
    }

    def __init__(self, parent=None, *, show_detail: bool = True,
                 placeholder: str = "Type medicine name, formula or barcode…") -> None:
        super().__init__(parent)
        self._show_detail = show_detail
        self._last_results: list = []
        self._selected_medicine_id: int | None = None

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(4)

        # -- Search bar row --
        search_row = QHBoxLayout()
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText(placeholder)
        self.search_edit.setClearButtonEnabled(True)
        search_row.addWidget(self.search_edit)
        root.addLayout(search_row)

        # -- Dropdown results --
        self.results_list = QListWidget()
        self.results_list.setMaximumHeight(160)
        self.results_list.setVisible(False)
        self.results_list.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.results_list.setStyleSheet(
            "QListWidget { border: 1px solid #aaa; background: white; font-size: 13px; }"
            "QListWidget::item { padding: 6px 10px; }"
            "QListWidget::item:selected { background: #2288cc; color: white; }"
            "QListWidget::item:hover { background: #dce8f5; }"
        )
        root.addWidget(self.results_list)

        # -- Detail panel --
        if show_detail:
            self.detail_frame = QFrame()
            self.detail_frame.setFrameShape(QFrame.Shape.StyledPanel)
            self.detail_frame.setStyleSheet(
                "QFrame { background: #f9fafb; border-radius: 6px; border: 1px solid #dee2e6; }"
            )
            self.detail_frame.setVisible(False)
            detail_layout = QVBoxLayout(self.detail_frame)
            detail_layout.setContentsMargins(10, 10, 10, 10)
            detail_layout.setSpacing(6)

            # ── Medicine name / strength / form ───────────────────────────
            self._name_label = QLabel()
            self._name_label.setStyleSheet(
                "font-size: 15px; font-weight: 700; color: #154c89;"
            )
            detail_layout.addWidget(self._name_label)

            # ── Formula | Brand  +  Total Stock  +  Status badge ──────────
            meta_row = QHBoxLayout()
            self._formula_label = QLabel()
            self._formula_label.setStyleSheet("color: #555; font-size: 12px;")
            self._status_label = QLabel()
            self._status_label.setStyleSheet(
                "font-weight: 700; font-size: 12px; padding: 2px 8px; border-radius: 4px;"
            )
            self._stock_label = QLabel()
            self._stock_label.setStyleSheet("font-size: 12px; font-weight: 600;")
            meta_row.addWidget(self._formula_label)
            meta_row.addStretch()
            meta_row.addWidget(self._stock_label)
            meta_row.addWidget(self._status_label)
            detail_layout.addLayout(meta_row)

            # ── Thin divider ──────────────────────────────────────────────
            div = QWidget()
            div.setFixedHeight(1)
            div.setStyleSheet("background: #dee2e6;")
            detail_layout.addWidget(div)

            # ── Location summary row (shown below formula / stock line) ───
            # Updated per-batch with the first in-stock batch's location.
            self._location_label = QLabel()
            self._location_label.setStyleSheet(
                "font-size: 12px; color: #154c89; font-weight: 600; padding: 2px 0;"
            )
            self._location_label.setWordWrap(True)
            self._location_label.setVisible(False)
            detail_layout.addWidget(self._location_label)

            # ── Batch table (9 cols — now with Wardrobe / Rack / Shelf) ───
            batch_label = QLabel("Batches (FEFO order):")
            batch_label.setStyleSheet(
                "font-weight: 600; font-size: 12px; margin-top: 2px;"
            )
            detail_layout.addWidget(batch_label)

            self._batch_table = QTableWidget(0, 9)
            self._batch_table.setHorizontalHeaderLabels([
                "Batch", "Qty", "Sell Price",
                "Expiry", "Days Left",
                "Wardrobe", "Rack", "Shelf",
                "Status"
            ])
            self._batch_table.horizontalHeader().setStretchLastSection(True)
            self._batch_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
            self._batch_table.setMaximumHeight(150)
            self._batch_table.setAlternatingRowColors(True)
            self._batch_table.setSelectionBehavior(
                QTableWidget.SelectionBehavior.SelectRows
            )
            detail_layout.addWidget(self._batch_table)

            root.addWidget(self.detail_frame)

        # -- Debounce timer --
        self._debounce = QTimer()
        self._debounce.setSingleShot(True)
        self._debounce.setInterval(200)  # 200 ms debounce
        self._debounce.timeout.connect(self._do_search)

        # -- Signals --
        self.search_edit.textChanged.connect(self._on_text_changed)
        self.search_edit.returnPressed.connect(self._on_return_pressed)
        self.results_list.itemClicked.connect(self._on_item_clicked)
        self.results_list.itemActivated.connect(self._on_item_clicked)

    # ------------------------------------------------------------------ API

    def clear_search(self) -> None:
        """Programmatically clear the search field and all results."""
        self.search_edit.blockSignals(True)
        self.search_edit.clear()
        self.search_edit.blockSignals(False)
        self._clear_results()

    def set_focus(self) -> None:
        self.search_edit.setFocus()

    def get_selected_medicine_id(self) -> int | None:
        return self._selected_medicine_id

    # ------------------------------------------------------------------ slots

    def _on_text_changed(self, text: str) -> None:
        if not text.strip():
            # F8: immediately clear when field is empty
            self._clear_results()
            return
        self._debounce.start()

    def _on_return_pressed(self) -> None:
        self._debounce.stop()
        self._do_search()
        # If exactly one result, auto-select it
        if self.results_list.count() == 1:
            self._select_item(self.results_list.item(0))

    def _on_item_clicked(self, item: QListWidgetItem) -> None:
        self._select_item(item)

    def _select_item(self, item: QListWidgetItem) -> None:
        if item is None:
            return
        medicine_id = item.data(Qt.ItemDataRole.UserRole)
        medicine_name = item.data(Qt.ItemDataRole.UserRole + 1)
        self._selected_medicine_id = medicine_id
        # Put selected name in search box
        self.search_edit.blockSignals(True)
        self.search_edit.setText(medicine_name)
        self.search_edit.blockSignals(False)
        self.results_list.setVisible(False)
        self.medicine_selected.emit(medicine_id, medicine_name)
        if self._show_detail:
            self._load_detail(medicine_id)

    def _clear_results(self) -> None:
        self._last_results = []
        self._selected_medicine_id = None
        self.results_list.clear()
        self.results_list.setVisible(False)
        if self._show_detail:
            self.detail_frame.setVisible(False)

    # ------------------------------------------------------------------ search

    def _do_search(self) -> None:
        term = self.search_edit.text().strip()
        if not term:
            self._clear_results()
            return

        try:
            from app.services.medicine_service import search_medicines
            results = search_medicines(term)
        except ApplicationError:
            results = []

        self._last_results = results
        self.results_list.clear()

        if not results:
            placeholder = QListWidgetItem("No medicines found")
            placeholder.setFlags(Qt.ItemFlag.NoItemFlags)
            placeholder.setForeground(QColor("#999"))
            self.results_list.addItem(placeholder)
            self.results_list.setVisible(True)
            return

        for med in results:
            # Total stock across active batches
            total_qty = sum(b.quantity for b in med.batches if b.is_active)
            price = float(med.batches[0].selling_price) if med.batches else 0.0
            label = f"{med.name}"
            if med.generic_formula:
                label += f"  ({med.generic_formula})"
            label += f"  —  Qty: {total_qty}  —  Rs {price:.2f}"

            item = QListWidgetItem(label)
            item.setData(Qt.ItemDataRole.UserRole, med.id)
            item.setData(Qt.ItemDataRole.UserRole + 1, med.name)

            # Colour-code low/out of stock
            if total_qty <= 0:
                item.setForeground(QColor("#e74c3c"))
            elif total_qty <= med.min_stock_level:
                item.setForeground(QColor("#f39c12"))

            self.results_list.addItem(item)

        self.results_list.setVisible(True)

        # Barcode exact-match → auto-select
        if len(results) == 1 and results[0].barcode and term == results[0].barcode:
            self._select_item(self.results_list.item(0))

    # ------------------------------------------------------------------ detail

    def _load_detail(self, medicine_id: int) -> None:
        try:
            from app.services.medicine_service import get_medicine_detail
            detail = get_medicine_detail(medicine_id)
        except ApplicationError:
            self.detail_frame.setVisible(False)
            return

        from PySide6.QtGui import QFont, QColor as _QColor

        status = detail["overall_status"]
        colour = self._STATUS_COLOURS.get(status, "#333")

        # ── Header labels ────────────────────────────────────────────────
        self._name_label.setText(
            f"{detail['name']}"
            + (f"  {detail['strength']}" if detail["strength"] else "")
            + (f"  ({detail['dosage_form']})" if detail["dosage_form"] else "")
        )

        formula_parts = []
        if detail["generic_formula"]:
            formula_parts.append(f"Formula: {detail['generic_formula']}")
        if detail["brand_name"]:
            formula_parts.append(f"Brand: {detail['brand_name']}")
        self._formula_label.setText("  |  ".join(formula_parts))

        self._status_label.setText(f"  {status}  ")
        self._status_label.setStyleSheet(
            f"font-weight: 700; font-size: 12px; padding: 2px 8px; "
            f"border-radius: 4px; background: {colour}; color: white;"
        )
        self._stock_label.setText(
            f"Total Stock: {detail['total_stock']} "
            f"{detail.get('base_unit') or 'units'}"
        )

        # ── Location summary — show unique locations across all batches ──
        locations: list[str] = []
        seen: set[str] = set()
        for b in detail["batches"]:
            w = b.get("wardrobe") or ""
            r = b.get("rack") or ""
            s = b.get("shelf") or ""
            if w or r or s:
                parts = []
                if w:
                    parts.append(f"Wardrobe: {w}")
                if r:
                    parts.append(f"Rack: {r}")
                if s:
                    parts.append(f"Shelf: {s}")
                loc_str = "  |  ".join(parts)
                if loc_str not in seen:
                    seen.add(loc_str)
                    batch_tag = f"[Batch {b['batch_number']}]"
                    locations.append(f"{batch_tag}  {loc_str}")

        if locations:
            self._location_label.setText(
                "📍 " + "     ".join(locations)
            )
            self._location_label.setVisible(True)
        else:
            self._location_label.setVisible(False)

        # ── Batch table (9 cols) ─────────────────────────────────────────
        bold_font = QFont(self.font().family(), -1, QFont.Weight.Bold)

        self._batch_table.setRowCount(0)
        for b in detail["batches"]:
            row = self._batch_table.rowCount()
            self._batch_table.insertRow(row)

            # col 0 — Batch number
            self._batch_table.setItem(row, 0, QTableWidgetItem(b["batch_number"]))

            # col 1 — Qty
            qty_item = QTableWidgetItem(str(b["quantity"]))
            qty_item.setTextAlignment(
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
            )
            self._batch_table.setItem(row, 1, qty_item)

            # col 2 — Sell Price
            price_item = QTableWidgetItem(f"Rs {b['selling_price']:.2f}")
            price_item.setTextAlignment(
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
            )
            self._batch_table.setItem(row, 2, price_item)

            # col 3 — Expiry
            self._batch_table.setItem(row, 3, QTableWidgetItem(b["expiry_date"]))

            # col 4 — Days Left
            days = b["days_until_expiry"]
            if days < 0:
                days_text = f"Expired ({abs(days)}d ago)"
                days_fg = QColor("#c0392b")
            elif days == 0:
                days_text = "Expires TODAY"
                days_fg = QColor("#c0392b")
            elif days <= 30:
                days_text = f"{days}d"
                days_fg = QColor("#e67e22")
            else:
                days_text = f"{days}d"
                days_fg = QColor("#27ae60")
            days_item = QTableWidgetItem(days_text)
            days_item.setForeground(days_fg)
            self._batch_table.setItem(row, 4, days_item)

            # col 5 — Wardrobe
            wardrobe_val = b.get("wardrobe") or "—"
            w_item = QTableWidgetItem(wardrobe_val)
            w_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            if wardrobe_val != "—":
                w_item.setForeground(QColor("#154c89"))
                w_item.setFont(bold_font)
            self._batch_table.setItem(row, 5, w_item)

            # col 6 — Rack
            rack_val = b.get("rack") or "—"
            r_item = QTableWidgetItem(rack_val)
            r_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            if rack_val != "—":
                r_item.setForeground(QColor("#154c89"))
                r_item.setFont(bold_font)
            self._batch_table.setItem(row, 6, r_item)

            # col 7 — Shelf
            shelf_val = b.get("shelf") or "—"
            s_item = QTableWidgetItem(shelf_val)
            s_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            if shelf_val != "—":
                s_item.setForeground(QColor("#154c89"))
                s_item.setFont(bold_font)
            self._batch_table.setItem(row, 7, s_item)

            # col 8 — Status
            st_item = QTableWidgetItem(b["status"])
            st_colour = self._STATUS_COLOURS.get(b["status"], "#333")
            st_item.setForeground(QColor(st_colour))
            st_item.setFont(bold_font)
            self._batch_table.setItem(row, 8, st_item)

        self._batch_table.resizeColumnsToContents()
        self.detail_frame.setVisible(True)
