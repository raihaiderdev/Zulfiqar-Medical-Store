"""
Reports page (Phase 1 §21). Date-range sales/profit report, best-selling
medicines, and stock valuation — with working CSV export on each table.
"""
from __future__ import annotations

from datetime import date, timedelta

from PySide6.QtWidgets import (
    QDateEdit,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.config.settings import settings
from app.exports.data_exporter import export_to_csv
from app.reports import report_engine
from app.utils.exceptions import ApplicationError


class ReportsPage(QWidget):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._best_sellers_cache: list[dict] = []
        root = QVBoxLayout(self)

        header = QLabel("Reports")
        header.setStyleSheet("font-size: 18px; font-weight: 600;")
        root.addWidget(header)

        range_row = QHBoxLayout()
        self.start_edit = QDateEdit(calendarPopup=True)
        self.start_edit.setDate(date.today() - timedelta(days=30))
        self.end_edit = QDateEdit(calendarPopup=True)
        self.end_edit.setDate(date.today())
        run_button = QPushButton("Run Report")
        run_button.clicked.connect(self.refresh)
        range_row.addWidget(QLabel("From:"))
        range_row.addWidget(self.start_edit)
        range_row.addWidget(QLabel("To:"))
        range_row.addWidget(self.end_edit)
        range_row.addWidget(run_button)
        range_row.addStretch()
        root.addLayout(range_row)

        self.summary_label = QLabel("")
        self.summary_label.setStyleSheet("font-size: 13px; padding: 8px; background: #f5f6fa; border-radius: 6px;")
        root.addWidget(self.summary_label)

        best_sellers_row = QHBoxLayout()
        best_sellers_row.addWidget(QLabel("Best-Selling Medicines"))
        best_sellers_row.addStretch()
        export_button = QPushButton("Export CSV")
        export_button.clicked.connect(self._export_best_sellers)
        best_sellers_row.addWidget(export_button)
        root.addLayout(best_sellers_row)

        self.best_sellers_table = QTableWidget(0, 4)
        self.best_sellers_table.setHorizontalHeaderLabels(["Medicine", "Units Sold", "Revenue", "Profit"])
        self.best_sellers_table.horizontalHeader().setStretchLastSection(True)
        root.addWidget(self.best_sellers_table)

        root.addWidget(QLabel("Stock Valuation"))
        self.valuation_label = QLabel("")
        root.addWidget(self.valuation_label)

        self.refresh()

    def _get_range(self) -> tuple[date, date]:
        s, e = self.start_edit.date(), self.end_edit.date()
        return date(s.year(), s.month(), s.day()), date(e.year(), e.month(), e.day())

    def refresh(self) -> None:
        start, end = self._get_range()
        try:
            financials = report_engine.sales_and_profit_report(start, end)
            self._best_sellers_cache = report_engine.best_selling_medicines(start, end, limit=20)
            valuation = report_engine.stock_valuation_report()
        except ApplicationError as exc:
            QMessageBox.warning(self, "Cannot run report", str(exc))
            return

        cur = settings.currency
        self.summary_label.setText(
            f"Revenue: {cur} {financials.revenue:.2f}   |   COGS: {cur} {financials.cogs:.2f}   |   "
            f"Gross Profit: {cur} {financials.gross_profit:.2f}   |   Expenses: {cur} {financials.expenses:.2f}   |   "
            f"Net Profit: {cur} {financials.net_profit:.2f}   |   Returned Units: {financials.returned_units}"
        )

        self.best_sellers_table.setRowCount(0)
        for row_data in self._best_sellers_cache:
            row = self.best_sellers_table.rowCount()
            self.best_sellers_table.insertRow(row)
            self.best_sellers_table.setItem(row, 0, QTableWidgetItem(row_data["name"]))
            self.best_sellers_table.setItem(row, 1, QTableWidgetItem(str(row_data["units_sold"])))
            self.best_sellers_table.setItem(row, 2, QTableWidgetItem(f"{row_data['revenue']:.2f}"))
            self.best_sellers_table.setItem(row, 3, QTableWidgetItem(f"{row_data['profit']:.2f}"))

        self.valuation_label.setText(
            f"{valuation['batch_count']} batches, {valuation['total_units']} units — "
            f"Cost: {cur} {valuation['cost_value']:.2f}, Retail: {cur} {valuation['retail_value']:.2f}, "
            f"Potential Gross Profit: {cur} {valuation['potential_gross_profit']:.2f}"
        )

    def _export_best_sellers(self) -> None:
        if not self._best_sellers_cache:
            QMessageBox.information(self, "Nothing to export", "Run a report first.")
            return
        path, _ = QFileDialog.getSaveFileName(self, "Export Best Sellers", "best_sellers.csv", "CSV Files (*.csv)")
        if not path:
            return
        try:
            export_to_csv(self._best_sellers_cache, path)
            QMessageBox.information(self, "Exported", f"Saved to {path}")
        except Exception as exc:
            QMessageBox.critical(self, "Export failed", str(exc))
