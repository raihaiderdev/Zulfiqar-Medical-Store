"""
Dead Stock Detection page — Phase 1.3

Medicines with stock on hand but no sales over a configurable period.
"""
from __future__ import annotations

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtWidgets import (
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.config.settings import settings


class _Worker(QThread):
    done  = Signal(list)
    error = Signal(str)

    def __init__(self, dead_stock_days, parent=None):
        super().__init__(parent)
        self._days = dead_stock_days

    def run(self):
        try:
            from app.services.inventory_intelligence_service import get_dead_stock
            self.done.emit(get_dead_stock(dead_stock_days=self._days))
        except Exception as exc:
            self.error.emit(str(exc))


class DeadStockPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._data: list[dict] = []
        self._worker = None
        root = QVBoxLayout(self)
        root.setSpacing(8)

        hdr = QLabel("Dead Stock Detection")
        hdr.setStyleSheet("font-size:18px; font-weight:600;")
        root.addWidget(hdr)

        cfg = QHBoxLayout()
        cfg.setSpacing(14)
        cfg.addWidget(QLabel("No sales for (days):"))
        self._days_spin = QSpinBox()
        self._days_spin.setRange(14, 365)
        self._days_spin.setValue(90)
        cfg.addWidget(self._days_spin)
        cfg.addStretch()

        self._status_lbl = QLabel("")
        self._status_lbl.setStyleSheet("color:#555; font-size:12px;")
        cfg.addWidget(self._status_lbl)

        self._run_btn = QPushButton("▶  Detect Dead Stock")
        self._run_btn.setStyleSheet(
            "background-color:#922b21;color:white;font-weight:600;padding:6px 14px;border-radius:4px;"
        )
        self._run_btn.clicked.connect(self._run)
        cfg.addWidget(self._run_btn)
        root.addLayout(cfg)

        info = QLabel(
            "ℹ  Dead stock = medicines with available quantity but zero sales "
            "over the configured period. Only non-expired stock is counted."
        )
        info.setWordWrap(True)
        info.setStyleSheet(
            "background:#fdecea;padding:8px;border-radius:4px;"
            "border:1px solid #e74c3c;font-size:12px;color:#333;"
        )
        root.addWidget(info)

        self._table = QTableWidget(0, 7)
        self._table.setHorizontalHeaderLabels([
            "Medicine", "Dosage", "Last Sale",
            "Days Without Sales", "Stock",
            f"Stock Value ({settings.currency})",
            "Suggested Action"
        ])
        hh = self._table.horizontalHeader()
        hh.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        hh.setSectionResizeMode(6, QHeaderView.ResizeMode.Stretch)
        for c in [1, 2, 3, 4, 5]:
            hh.setSectionResizeMode(c, QHeaderView.ResizeMode.ResizeToContents)
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._table.setAlternatingRowColors(True)
        root.addWidget(self._table, 1)

        self._count_lbl = QLabel("")
        self._count_lbl.setStyleSheet("color:#888; font-size:11px;")
        root.addWidget(self._count_lbl)

    def _run(self):
        if self._worker and self._worker.isRunning():
            return
        self._run_btn.setEnabled(False)
        self._status_lbl.setText("⏳ Detecting…")
        self._table.setRowCount(0)
        self._worker = _Worker(self._days_spin.value())
        self._worker.done.connect(self._on_done)
        self._worker.error.connect(self._on_error)
        self._worker.start()

    def _on_done(self, data):
        self._data = data
        self._populate(data)
        self._run_btn.setEnabled(True)
        self._status_lbl.setText("")

    def _on_error(self, msg):
        QMessageBox.warning(self, "Detection failed", msg)
        self._run_btn.setEnabled(True)
        self._status_lbl.setText("Error")

    def _populate(self, data):
        from PySide6.QtGui import QFont
        bold = QFont(); bold.setBold(True)
        self._table.setRowCount(0)
        total_val = 0.0

        for item in data:
            row = self._table.rowCount()
            self._table.insertRow(row)

            self._table.setItem(row, 0, QTableWidgetItem(item["name"]))
            self._table.setItem(row, 1, QTableWidgetItem(item.get("dosage_form", "")))
            self._table.setItem(row, 2, QTableWidgetItem(
                item["last_sale_date"] or "Never sold"
            ))

            days = item.get("days_without_sales")
            days_text = str(days) if days is not None else "Never sold"
            days_item = QTableWidgetItem(days_text)
            days_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter | Qt.AlignmentFlag.AlignVCenter)
            if days is None or days > 180:
                days_item.setForeground(Qt.GlobalColor.red)
                days_item.setFont(bold)
            elif days > 90:
                days_item.setForeground(Qt.GlobalColor.darkYellow)
            self._table.setItem(row, 3, days_item)

            stock_item = QTableWidgetItem(str(item["sellable_stock"]))
            stock_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter | Qt.AlignmentFlag.AlignVCenter)
            self._table.setItem(row, 4, stock_item)

            val = item.get("stock_value", 0.0)
            val_item = QTableWidgetItem(f"{val:,.2f}")
            val_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self._table.setItem(row, 5, val_item)
            total_val += val

            self._table.setItem(row, 6, QTableWidgetItem(item.get("suggested_action", "")))

        cur = settings.currency
        self._count_lbl.setText(
            f"{len(data)} dead stock items  |  "
            f"Total value: {cur} {total_val:,.2f}  |  "
            f"Threshold: {self._days_spin.value()} days"
        )
