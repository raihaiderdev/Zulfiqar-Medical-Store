"""
Expiry Risk Intelligence page — Phase 1.2

Enhanced expiry risk report with financial context:
  - Purchase value at risk
  - Estimated waste units/value based on sales velocity
  - Risk classification (HIGH / MODERATE / LOW)
"""
from __future__ import annotations

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtWidgets import (
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


class _Worker(QThread):
    done  = Signal(list)
    error = Signal(str)

    def __init__(self, warning_days, analysis_days, parent=None):
        super().__init__(parent)
        self._warning_days  = warning_days
        self._analysis_days = analysis_days

    def run(self):
        try:
            from app.services.inventory_intelligence_service import get_expiry_risk_report
            self.done.emit(get_expiry_risk_report(
                warning_days=self._warning_days,
                analysis_days=self._analysis_days,
            ))
        except Exception as exc:
            self.error.emit(str(exc))


class ExpiryRiskPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._data: list[dict] = []
        self._worker = None
        root = QVBoxLayout(self)
        root.setSpacing(8)

        # Header
        hdr = QLabel("Expiry Risk Intelligence")
        hdr.setStyleSheet("font-size:18px; font-weight:600;")
        root.addWidget(hdr)

        # Config
        cfg = QHBoxLayout()
        cfg.setSpacing(14)
        cfg.addWidget(QLabel("Warning window (days):"))
        self._warn_spin = QSpinBox()
        self._warn_spin.setRange(30, 365)
        self._warn_spin.setValue(214)
        cfg.addWidget(self._warn_spin)

        cfg.addWidget(QLabel("Sales analysis (days):"))
        self._analysis_spin = QSpinBox()
        self._analysis_spin.setRange(7, 365)
        self._analysis_spin.setValue(90)
        cfg.addWidget(self._analysis_spin)

        cfg.addWidget(QLabel("Risk filter:"))
        self._risk_combo = QComboBox()
        self._risk_combo.addItems(["All", "HIGH", "MODERATE", "LOW", "EXPIRED"])
        self._risk_combo.currentIndexChanged.connect(self._apply_filter)
        cfg.addWidget(self._risk_combo)

        cfg.addStretch()
        self._status_lbl = QLabel("")
        self._status_lbl.setStyleSheet("color:#555; font-size:12px;")
        cfg.addWidget(self._status_lbl)

        self._run_btn = QPushButton("▶  Analyse")
        self._run_btn.setStyleSheet(
            "background-color:#154c89;color:white;font-weight:600;padding:6px 14px;border-radius:4px;"
        )
        self._run_btn.clicked.connect(self._run)
        cfg.addWidget(self._run_btn)
        root.addLayout(cfg)

        # Info
        info = QLabel(
            "ℹ  Estimated waste is based on average daily sales velocity. "
            "HIGH risk = waste value > PKR 1,000 or expires ≤ 30 days. "
            "MODERATE = waste > PKR 200 or ≤ 90 days. "
            "These are estimates — actual results depend on future sales."
        )
        info.setWordWrap(True)
        info.setStyleSheet(
            "background:#fff3cd;padding:8px;border-radius:4px;"
            "border:1px solid #ffc107;font-size:12px;color:#333;"
        )
        root.addWidget(info)

        # Table
        self._table = QTableWidget(0, 10)
        self._table.setHorizontalHeaderLabels([
            "Risk", "Medicine", "Batch", "Expiry",
            "Days Left", "Qty", f"Value ({settings.currency})",
            "ADS", f"Est. Waste ({settings.currency})", "Location"
        ])
        hh = self._table.horizontalHeader()
        hh.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        for c in [0, 2, 3, 4, 5, 6, 7, 8, 9]:
            hh.setSectionResizeMode(c, QHeaderView.ResizeMode.ResizeToContents)
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._table.setAlternatingRowColors(True)
        root.addWidget(self._table, 1)

        self._count_lbl = QLabel("")
        self._count_lbl.setStyleSheet("color:#888; font-size:11px;")
        root.addWidget(self._count_lbl)

    _RISK_COLOURS = {
        "EXPIRED":  ("#8e1010", "#fdecea"),
        "HIGH":     ("#c0392b", "#fdecea"),
        "MODERATE": ("#d35400", "#fff3cd"),
        "LOW":      ("#1e8449", "#eafaf1"),
    }

    def _run(self):
        if self._worker and self._worker.isRunning():
            return
        self._run_btn.setEnabled(False)
        self._status_lbl.setText("⏳ Analysing…")
        self._table.setRowCount(0)
        self._worker = _Worker(self._warn_spin.value(), self._analysis_spin.value())
        self._worker.done.connect(self._on_done)
        self._worker.error.connect(self._on_error)
        self._worker.start()

    def _on_done(self, data):
        self._data = data
        self._apply_filter()
        self._run_btn.setEnabled(True)
        self._status_lbl.setText("")

    def _on_error(self, msg):
        QMessageBox.warning(self, "Analysis failed", msg)
        self._run_btn.setEnabled(True)
        self._status_lbl.setText("Error")

    def _apply_filter(self):
        risk_filter = self._risk_combo.currentText()
        visible = [d for d in self._data
                   if risk_filter == "All" or d["risk_level"] == risk_filter]
        self._populate(visible)

    def _populate(self, data):
        from PySide6.QtGui import QColor, QFont
        bold = QFont(); bold.setBold(True)
        self._table.setRowCount(0)
        cur = settings.currency
        total_waste = 0.0

        for item in data:
            row = self._table.rowCount()
            self._table.insertRow(row)
            risk = item["risk_level"]
            fg, bg = self._risk_colours_tuple(risk)

            risk_item = QTableWidgetItem(risk)
            risk_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter | Qt.AlignmentFlag.AlignVCenter)
            risk_item.setForeground(QColor(fg))
            risk_item.setBackground(QColor(bg))
            risk_item.setFont(bold)
            self._table.setItem(row, 0, risk_item)

            self._table.setItem(row, 1, QTableWidgetItem(item["medicine_name"]))
            self._table.setItem(row, 2, QTableWidgetItem(item["batch_number"]))
            self._table.setItem(row, 3, QTableWidgetItem(item["expiry_date"]))

            days = item["days_to_expiry"]
            days_item = QTableWidgetItem(
                str(days) if days >= 0 else f"Expired {abs(days)}d ago"
            )
            days_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter | Qt.AlignmentFlag.AlignVCenter)
            if days < 0:
                days_item.setForeground(Qt.GlobalColor.red)
            elif days <= 30:
                days_item.setForeground(Qt.GlobalColor.darkRed)
            self._table.setItem(row, 4, days_item)

            for col, key, right_align in [
                (5, "quantity",           True),
                (6, "purchase_value",     True),
                (7, "avg_daily_sales",    True),
                (8, "estimated_waste_value", True),
            ]:
                v = item[key]
                text = f"{v:.2f}" if isinstance(v, float) else str(v)
                it = QTableWidgetItem(text)
                if right_align:
                    it.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                if key == "estimated_waste_value" and float(v) > 0:
                    it.setForeground(QColor("#c0392b"))
                    it.setFont(bold)
                self._table.setItem(row, col, it)

            self._table.setItem(row, 9, QTableWidgetItem(item.get("location", "")))
            total_waste += item.get("estimated_waste_value", 0.0)

        cur = settings.currency
        high = sum(1 for d in data if d["risk_level"] == "HIGH")
        mod  = sum(1 for d in data if d["risk_level"] == "MODERATE")
        self._count_lbl.setText(
            f"{len(data)} batches  |  HIGH: {high}  MODERATE: {mod}  |  "
            f"Total estimated waste: {cur} {total_waste:,.2f}"
        )

    def _risk_colours_tuple(self, risk):
        return self._RISK_COLOURS.get(risk, ("#333", "#f5f6fa"))
