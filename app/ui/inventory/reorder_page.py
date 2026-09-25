"""
Smart Reorder Suggestions page  — Phase 1.1

Shows medicines that need reordering based on sales velocity,
lead time, and safety stock calculations.
All figures are computed deterministically from transactional history.
"""
from __future__ import annotations

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
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
from app.utils.exceptions import ApplicationError


# ── Background worker ─────────────────────────────────────────────────────

class _ReorderWorker(QThread):
    done    = Signal(list)
    error   = Signal(str)

    def __init__(self, analysis_days, lead_time_days,
                 safety_stock_days, only_below_rp, parent=None):
        super().__init__(parent)
        self._analysis_days    = analysis_days
        self._lead_time_days   = lead_time_days
        self._safety_stock_days = safety_stock_days
        self._only_below_rp    = only_below_rp

    def run(self) -> None:
        try:
            from app.services.inventory_intelligence_service import get_reorder_suggestions
            data = get_reorder_suggestions(
                analysis_days=self._analysis_days,
                lead_time_days=self._lead_time_days,
                safety_stock_days=self._safety_stock_days,
                only_below_reorder_point=self._only_below_rp,
            )
            self.done.emit(data)
        except Exception as exc:
            self.error.emit(str(exc))


# ── Detail dialog ─────────────────────────────────────────────────────────

class ReorderDetailDialog(QDialog):
    def __init__(self, item: dict, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle(f"Reorder Detail — {item['name']}")
        self.setMinimumWidth(520)
        layout = QVBoxLayout(self)
        cur = settings.currency

        def row(label: str, value: str) -> QHBoxLayout:
            h = QHBoxLayout()
            lbl = QLabel(label)
            lbl.setStyleSheet("font-weight:600; min-width:200px;")
            val = QLabel(value)
            val.setWordWrap(True)
            h.addWidget(lbl)
            h.addWidget(val, 1)
            return h

        layout.addLayout(row("Medicine:", item["name"]))
        layout.addLayout(row("Dosage Form:", item.get("dosage_form", "")))
        layout.addLayout(row("Unit:", item.get("unit", "")))
        layout.addLayout(row("Sellable Stock:", str(item["sellable_stock"])))
        layout.addLayout(row("Avg Daily Sales:", f"{item['avg_daily_sales']:.2f} units/day"))
        dr = item.get("days_remaining")
        layout.addLayout(row("Days of Stock Remaining:",
                             f"{dr:.0f} days" if dr is not None else "N/A (no sales)"))
        layout.addLayout(row("Lead Time:", f"{item['lead_time_days']} days"))
        layout.addLayout(row("Reorder Point:", f"{item['reorder_point']} units"))
        layout.addLayout(row("Target Stock Level:", f"{item['target_stock']} units"))
        layout.addLayout(row("Suggested Order Qty:", f"{item['suggested_qty']} units"))
        layout.addLayout(row("Analysis Period:", f"{item['analysis_days']} days"))

        div = QWidget(); div.setFixedHeight(1)
        div.setStyleSheet("background:#ddd;")
        layout.addWidget(div)

        expl_lbl = QLabel("Recommendation:")
        expl_lbl.setStyleSheet("font-weight:600;")
        layout.addWidget(expl_lbl)
        expl = QLabel(item.get("explanation", ""))
        expl.setWordWrap(True)
        expl.setStyleSheet("padding:8px; background:#f5f6fa; border-radius:4px;")
        layout.addWidget(expl)

        formula_lbl = QLabel(
            "<small><b>Formulas used:</b><br>"
            "ADS = units_sold / analysis_days<br>"
            "Reorder Point = ADS × lead_time + safety_stock<br>"
            "Target Stock = ADS × (lead_time + review_period) + safety_stock<br>"
            "Suggested Qty = max(0, target_stock − sellable_stock)</small>"
        )
        formula_lbl.setTextFormat(Qt.TextFormat.RichText)
        formula_lbl.setStyleSheet("color:#888; font-size:11px; padding:4px 0;")
        layout.addWidget(formula_lbl)

        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.accept)
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        btn_row.addWidget(close_btn)
        layout.addLayout(btn_row)


# ── Main page ─────────────────────────────────────────────────────────────

class ReorderPage(QWidget):
    """Smart Reorder Suggestions — Phase 1.1"""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._data: list[dict] = []
        self._worker: _ReorderWorker | None = None

        root = QVBoxLayout(self)
        root.setSpacing(8)

        # ── Header ────────────────────────────────────────────────────────
        header_row = QHBoxLayout()
        header = QLabel("Smart Reorder Suggestions")
        header.setStyleSheet("font-size:18px; font-weight:600;")
        header_row.addWidget(header)
        header_row.addStretch()

        self._status_lbl = QLabel("")
        self._status_lbl.setStyleSheet("color:#555; font-size:12px;")
        header_row.addWidget(self._status_lbl)
        root.addLayout(header_row)

        # ── Config row ────────────────────────────────────────────────────
        cfg_row = QHBoxLayout()
        cfg_row.setSpacing(16)

        cfg_row.addWidget(QLabel("Analysis period (days):"))
        self._analysis_spin = QSpinBox()
        self._analysis_spin.setRange(7, 365)
        self._analysis_spin.setValue(90)
        self._analysis_spin.setMinimumWidth(60)
        cfg_row.addWidget(self._analysis_spin)

        cfg_row.addWidget(QLabel("Lead time (days):"))
        self._lead_spin = QSpinBox()
        self._lead_spin.setRange(1, 90)
        self._lead_spin.setValue(7)
        self._lead_spin.setMinimumWidth(50)
        cfg_row.addWidget(self._lead_spin)

        cfg_row.addWidget(QLabel("Safety stock (days):"))
        self._safety_spin = QSpinBox()
        self._safety_spin.setRange(0, 60)
        self._safety_spin.setValue(14)
        self._safety_spin.setMinimumWidth(50)
        cfg_row.addWidget(self._safety_spin)

        self._only_below_cb = QCheckBox("Show only items needing reorder")
        self._only_below_cb.setChecked(False)
        cfg_row.addWidget(self._only_below_cb)

        cfg_row.addStretch()

        self._run_btn = QPushButton("▶  Calculate")
        self._run_btn.setStyleSheet(
            "background-color:#154c89; color:white; "
            "font-weight:600; padding:6px 16px; border-radius:4px;"
        )
        self._run_btn.clicked.connect(self._run)
        cfg_row.addWidget(self._run_btn)
        root.addLayout(cfg_row)

        # ── Info banner ───────────────────────────────────────────────────
        info = QLabel(
            "ℹ  Suggestions are based on average daily sales, configured lead time, "
            "and safety stock. Only non-expired stock counts as available. "
            "Review suggestions before placing orders — do not order automatically."
        )
        info.setWordWrap(True)
        info.setStyleSheet(
            "background:#eaf4fb; padding:8px; border-radius:4px; "
            "border:1px solid #aed6f1; font-size:12px; color:#333;"
        )
        root.addWidget(info)

        # ── Table ─────────────────────────────────────────────────────────
        self._table = QTableWidget(0, 9)
        self._table.setHorizontalHeaderLabels([
            "Medicine", "Unit", "Sellable Stock",
            "Avg Daily Sales", "Days Left",
            "Lead Time", "Reorder Point",
            "Suggested Qty", "Status"
        ])
        hh = self._table.horizontalHeader()
        hh.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        for c in range(1, 9):
            hh.setSectionResizeMode(c, QHeaderView.ResizeMode.ResizeToContents)
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._table.setAlternatingRowColors(True)
        self._table.doubleClicked.connect(self._on_row_double_clicked)
        root.addWidget(self._table, 1)

        self._count_lbl = QLabel("0 medicines — click Calculate to load suggestions")
        self._count_lbl.setStyleSheet("color:#888; font-size:11px;")
        root.addWidget(self._count_lbl)

    # ── Run ───────────────────────────────────────────────────────────────

    def _run(self) -> None:
        if self._worker and self._worker.isRunning():
            return

        self._run_btn.setEnabled(False)
        self._status_lbl.setText("⏳ Calculating…")
        self._table.setRowCount(0)

        self._worker = _ReorderWorker(
            analysis_days=self._analysis_spin.value(),
            lead_time_days=self._lead_spin.value(),
            safety_stock_days=self._safety_spin.value(),
            only_below_rp=self._only_below_cb.isChecked(),
        )
        self._worker.done.connect(self._on_done)
        self._worker.error.connect(self._on_error)
        self._worker.start()

    def _on_done(self, data: list[dict]) -> None:
        self._data = data
        self._populate(data)
        self._run_btn.setEnabled(True)
        self._status_lbl.setText("")

    def _on_error(self, msg: str) -> None:
        QMessageBox.warning(self, "Calculation failed", msg)
        self._run_btn.setEnabled(True)
        self._status_lbl.setText("Error — see message above")

    # ── Populate ──────────────────────────────────────────────────────────

    def _populate(self, data: list[dict]) -> None:
        self._table.setRowCount(0)

        for item in data:
            row = self._table.rowCount()
            self._table.insertRow(row)

            self._table.setItem(row, 0, QTableWidgetItem(item["name"]))
            self._table.setItem(row, 1, QTableWidgetItem(item.get("unit", "")))

            stock_item = QTableWidgetItem(str(item["sellable_stock"]))
            stock_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter | Qt.AlignmentFlag.AlignVCenter)
            if item["sellable_stock"] == 0:
                stock_item.setForeground(Qt.GlobalColor.red)
            self._table.setItem(row, 2, stock_item)

            ads_item = QTableWidgetItem(f"{item['avg_daily_sales']:.2f}")
            ads_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self._table.setItem(row, 3, ads_item)

            dr = item.get("days_remaining")
            days_text = f"{dr:.0f}" if dr is not None else "N/A"
            days_item = QTableWidgetItem(days_text)
            days_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter | Qt.AlignmentFlag.AlignVCenter)
            if dr is not None:
                if dr <= item["lead_time_days"]:
                    days_item.setForeground(Qt.GlobalColor.red)
                elif dr <= item["lead_time_days"] + 14:
                    days_item.setForeground(Qt.GlobalColor.darkYellow)
                else:
                    days_item.setForeground(Qt.GlobalColor.darkGreen)
            self._table.setItem(row, 4, days_item)

            self._table.setItem(row, 5, QTableWidgetItem(str(item["lead_time_days"])))
            self._table.setItem(row, 6, QTableWidgetItem(str(item["reorder_point"])))

            sq_item = QTableWidgetItem(str(item["suggested_qty"]))
            sq_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter | Qt.AlignmentFlag.AlignVCenter)
            if item["suggested_qty"] > 0:
                sq_item.setForeground(Qt.GlobalColor.darkBlue)
                from PySide6.QtGui import QFont
                f = QFont(); f.setBold(True)
                sq_item.setFont(f)
            self._table.setItem(row, 7, sq_item)

            needs = item["needs_reorder"]
            status_text = "⚠ Reorder" if needs else "✔ OK"
            status_item = QTableWidgetItem(status_text)
            status_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter | Qt.AlignmentFlag.AlignVCenter)
            status_item.setForeground(
                Qt.GlobalColor.red if needs else Qt.GlobalColor.darkGreen
            )
            self._table.setItem(row, 8, status_item)

        needs_count = sum(1 for i in data if i["needs_reorder"])
        self._count_lbl.setText(
            f"{len(data)} medicines analysed  |  "
            f"{needs_count} need reordering  |  "
            "Double-click a row for full details"
        )

    def _on_row_double_clicked(self, index) -> None:
        row = index.row()
        if row < 0 or row >= len(self._data):
            return
        ReorderDetailDialog(self._data[row], self).exec()
