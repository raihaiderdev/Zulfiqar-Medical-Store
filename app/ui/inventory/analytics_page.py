"""
Inventory Analytics page — Phase 1.4

ABC classification + inventory turnover ratio.
"""
from __future__ import annotations

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
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


class _ABCWorker(QThread):
    done  = Signal(list)
    error = Signal(str)

    def __init__(self, days, parent=None):
        super().__init__(parent)
        self._days = days

    def run(self):
        try:
            from app.services.inventory_intelligence_service import get_abc_classification
            self.done.emit(get_abc_classification(analysis_days=self._days))
        except Exception as exc:
            self.error.emit(str(exc))


class _TurnoverWorker(QThread):
    done  = Signal(dict)
    error = Signal(str)

    def __init__(self, days, parent=None):
        super().__init__(parent)
        self._days = days

    def run(self):
        try:
            from app.services.inventory_intelligence_service import get_inventory_turnover
            self.done.emit(get_inventory_turnover(analysis_days=self._days))
        except Exception as exc:
            self.error.emit(str(exc))


def _kpi_card(title: str, value: str, colour: str = "#f5f6fa") -> QFrame:
    card = QFrame()
    card.setFrameShape(QFrame.Shape.StyledPanel)
    card.setStyleSheet(f"QFrame{{background:{colour};border-radius:8px;padding:4px;}}")
    layout = QVBoxLayout(card)
    v_lbl = QLabel(value)
    v_lbl.setStyleSheet("font-size:18px;font-weight:700;")
    t_lbl = QLabel(title)
    t_lbl.setStyleSheet("color:#666;font-size:11px;")
    layout.addWidget(v_lbl)
    layout.addWidget(t_lbl)
    return card


class InventoryAnalyticsPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._abc_worker    = None
        self._turn_worker   = None
        root = QVBoxLayout(self)
        root.setSpacing(8)

        hdr = QLabel("Inventory Analytics")
        hdr.setStyleSheet("font-size:18px; font-weight:600;")
        root.addWidget(hdr)

        # Config
        cfg = QHBoxLayout()
        cfg.addWidget(QLabel("Analysis period (days):"))
        self._days_spin = QSpinBox()
        self._days_spin.setRange(30, 365)
        self._days_spin.setValue(90)
        cfg.addWidget(self._days_spin)
        cfg.addStretch()
        self._run_btn = QPushButton("▶  Run Analytics")
        self._run_btn.setStyleSheet(
            "background-color:#117a65;color:white;font-weight:600;padding:6px 14px;border-radius:4px;"
        )
        self._run_btn.clicked.connect(self._run_all)
        cfg.addWidget(self._run_btn)
        root.addLayout(cfg)

        # KPI summary cards
        self._kpi_row = QHBoxLayout()
        self._card_turnover  = _kpi_card("Inventory Turnover (annualised)", "—", "#eaf4fb")
        self._card_a_count   = _kpi_card("Class A Items (70% revenue)", "—", "#eafaf1")
        self._card_b_count   = _kpi_card("Class B Items", "—", "#fff8e1")
        self._card_c_count   = _kpi_card("Class C Items", "—", "#fdecea")
        for card in [self._card_turnover, self._card_a_count,
                     self._card_b_count, self._card_c_count]:
            self._kpi_row.addWidget(card)
        root.addLayout(self._kpi_row)

        # Turnover detail
        self._turnover_lbl = QLabel("")
        self._turnover_lbl.setWordWrap(True)
        self._turnover_lbl.setStyleSheet(
            "background:#f5f6fa;padding:8px;border-radius:4px;font-size:12px;"
        )
        root.addWidget(self._turnover_lbl)

        # Tabs: ABC table
        self._tabs = QTabWidget()

        # ABC tab
        abc_tab = QWidget()
        abc_layout = QVBoxLayout(abc_tab)
        self._abc_table = QTableWidget(0, 7)
        self._abc_table.setHorizontalHeaderLabels([
            "Class", "Medicine", "Dosage",
            "Units Sold", f"Revenue ({settings.currency})",
            "Revenue %", "Avg Daily Sales"
        ])
        hh = self._abc_table.horizontalHeader()
        hh.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        for c in [0, 2, 3, 4, 5, 6]:
            hh.setSectionResizeMode(c, QHeaderView.ResizeMode.ResizeToContents)
        self._abc_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._abc_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._abc_table.setAlternatingRowColors(True)
        abc_layout.addWidget(self._abc_table)
        self._abc_count_lbl = QLabel("")
        self._abc_count_lbl.setStyleSheet("color:#888;font-size:11px;")
        abc_layout.addWidget(self._abc_count_lbl)
        self._tabs.addTab(abc_tab, "ABC Classification")

        root.addWidget(self._tabs, 1)

    _ABC_COLOURS = {
        "A": ("#1e8449", "#eafaf1"),
        "B": ("#d35400", "#fff3cd"),
        "C": ("#555",    "#f5f6fa"),
    }

    def _run_all(self):
        if ((self._abc_worker and self._abc_worker.isRunning()) or
                (self._turn_worker and self._turn_worker.isRunning())):
            return
        self._run_btn.setEnabled(False)
        days = self._days_spin.value()

        self._abc_worker = _ABCWorker(days)
        self._abc_worker.done.connect(self._on_abc_done)
        self._abc_worker.error.connect(self._on_error)
        self._abc_worker.start()

        self._turn_worker = _TurnoverWorker(days)
        self._turn_worker.done.connect(self._on_turnover_done)
        self._turn_worker.error.connect(self._on_error)
        self._turn_worker.start()

    def _on_abc_done(self, data):
        self._populate_abc(data)
        self._maybe_re_enable()

    def _on_turnover_done(self, data):
        self._populate_turnover(data)
        self._maybe_re_enable()

    def _maybe_re_enable(self):
        abc_running  = self._abc_worker  and self._abc_worker.isRunning()
        turn_running = self._turn_worker and self._turn_worker.isRunning()
        if not abc_running and not turn_running:
            self._run_btn.setEnabled(True)

    def _on_error(self, msg):
        QMessageBox.warning(self, "Analytics failed", msg)
        self._run_btn.setEnabled(True)

    def _populate_turnover(self, data):
        cur = settings.currency
        t = data.get("annualized_turnover", 0)
        self._card_turnover.layout().itemAt(0).widget().setText(f"{t:.1f}×")
        self._turnover_lbl.setText(
            f"<b>Inventory Turnover</b>  ({data.get('period_start')} → {data.get('period_end')})<br>"
            f"COGS: {cur} {data.get('cogs', 0):,.2f}  |  "
            f"Avg Inventory Value: {cur} {data.get('average_inventory_value', 0):,.2f}  |  "
            f"Turnover Ratio: {data.get('turnover_ratio', 0):.4f}  |  "
            f"Annualised: {t:.1f}×<br>"
            f"<i>{data.get('interpretation', '')}</i>"
        )

    def _populate_abc(self, data):
        from PySide6.QtGui import QColor, QFont
        bold = QFont(); bold.setBold(True)
        self._abc_table.setRowCount(0)

        a_count = sum(1 for d in data if d["abc_class"] == "A")
        b_count = sum(1 for d in data if d["abc_class"] == "B")
        c_count = sum(1 for d in data if d["abc_class"] == "C")
        self._card_a_count.layout().itemAt(0).widget().setText(str(a_count))
        self._card_b_count.layout().itemAt(0).widget().setText(str(b_count))
        self._card_c_count.layout().itemAt(0).widget().setText(str(c_count))

        for item in data:
            row = self._abc_table.rowCount()
            self._abc_table.insertRow(row)
            cls  = item["abc_class"]
            fg, bg = self._ABC_COLOURS.get(cls, ("#333", "#f5f6fa"))

            cls_item = QTableWidgetItem(cls)
            cls_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter | Qt.AlignmentFlag.AlignVCenter)
            cls_item.setForeground(QColor(fg))
            cls_item.setBackground(QColor(bg))
            cls_item.setFont(bold)
            self._abc_table.setItem(row, 0, cls_item)

            self._abc_table.setItem(row, 1, QTableWidgetItem(item.get("name", "")))
            self._abc_table.setItem(row, 2, QTableWidgetItem(item.get("dosage_form", "")))

            for col, key in [(3, "units_sold"), (4, "revenue"),
                              (5, "cumulative_pct"), (6, "avg_daily_sales")]:
                v = item.get(key, 0)
                if key == "cumulative_pct":
                    text = f"{v*100:.1f}%"
                elif isinstance(v, float):
                    text = f"{v:,.2f}"
                else:
                    text = str(v)
                it = QTableWidgetItem(text)
                it.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                self._abc_table.setItem(row, col, it)

        cur = settings.currency
        self._abc_count_lbl.setText(
            f"{len(data)} medicines classified  |  A: {a_count}  B: {b_count}  C: {c_count}"
        )
