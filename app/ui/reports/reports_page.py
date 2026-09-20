"""
Reports page — date-range financial summary with separate Discounts section,
best-selling medicines, and stock valuation.
"""
from __future__ import annotations

from datetime import date, timedelta

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDateEdit,
    QFileDialog,
    QFrame,
    QGridLayout,
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


def _summary_card(title: str, value: str, colour: str = "#f5f6fa",
                  text_colour: str = "#333") -> QFrame:
    """A small coloured summary card for the financial overview grid."""
    card = QFrame()
    card.setFrameShape(QFrame.Shape.StyledPanel)
    card.setStyleSheet(
        f"QFrame {{ background: {colour}; border-radius: 8px; padding: 6px; }}"
    )
    layout = QVBoxLayout(card)
    layout.setContentsMargins(10, 8, 10, 8)
    layout.setSpacing(2)

    val_lbl = QLabel(value)
    val_lbl.setStyleSheet(
        f"font-size: 17px; font-weight: 700; color: {text_colour};"
    )
    title_lbl = QLabel(title)
    title_lbl.setStyleSheet("color: #666; font-size: 11px;")
    layout.addWidget(val_lbl)
    layout.addWidget(title_lbl)
    return card


class ReportsPage(QWidget):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._best_sellers_cache: list[dict] = []
        root = QVBoxLayout(self)
        root.setSpacing(10)

        # ── Header ────────────────────────────────────────────────────────
        header = QLabel("Reports")
        header.setStyleSheet("font-size: 18px; font-weight: 600;")
        root.addWidget(header)

        # ── Date range ────────────────────────────────────────────────────
        range_row = QHBoxLayout()
        self.start_edit = QDateEdit(calendarPopup=True)
        self.start_edit.setDate(date.today() - timedelta(days=30))
        self.end_edit = QDateEdit(calendarPopup=True)
        self.end_edit.setDate(date.today())
        run_button = QPushButton("▶  Run Report")
        run_button.setStyleSheet(
            "background-color: #154c89; color: white; "
            "padding: 6px 16px; font-weight: 600; border-radius: 4px;"
        )
        run_button.clicked.connect(self.refresh)
        range_row.addWidget(QLabel("From:"))
        range_row.addWidget(self.start_edit)
        range_row.addWidget(QLabel("To:"))
        range_row.addWidget(self.end_edit)
        range_row.addWidget(run_button)
        range_row.addStretch()
        root.addLayout(range_row)

        # ── Financial summary grid ────────────────────────────────────────
        summary_label = QLabel("Financial Summary")
        summary_label.setStyleSheet("font-weight: 600; font-size: 13px;")
        root.addWidget(summary_label)

        self._summary_grid = QGridLayout()
        self._summary_grid.setSpacing(8)
        root.addLayout(self._summary_grid)

        # Cards are rebuilt on each refresh — store references to update values
        self._cards: dict[str, QFrame] = {}

        # ── Separator ─────────────────────────────────────────────────────
        sep1 = QWidget(); sep1.setFixedHeight(1)
        sep1.setStyleSheet("background: #ddd;")
        root.addWidget(sep1)

        # ── Discount section ──────────────────────────────────────────────
        disc_header_row = QHBoxLayout()
        disc_title = QLabel("🏷  Discounts Given")
        disc_title.setStyleSheet("font-weight: 600; font-size: 13px;")
        disc_header_row.addWidget(disc_title)
        disc_header_row.addStretch()
        root.addLayout(disc_header_row)

        self._discount_frame = QFrame()
        self._discount_frame.setStyleSheet(
            "QFrame { background: #fff8e1; border-radius: 8px; "
            "border: 1px solid #f9a825; padding: 4px; }"
        )
        disc_layout = QHBoxLayout(self._discount_frame)
        disc_layout.setContentsMargins(14, 10, 14, 10)
        disc_layout.setSpacing(40)

        self._total_discount_lbl  = QLabel(f"Total Discount: {settings.currency} 0.00")
        self._total_discount_lbl.setStyleSheet(
            "font-size: 16px; font-weight: 700; color: #e65100;"
        )
        self._gross_before_disc_lbl = QLabel(f"Gross Sales (before discount): {settings.currency} 0.00")
        self._gross_before_disc_lbl.setStyleSheet("font-size: 12px; color: #555;")
        self._net_revenue_lbl = QLabel(f"Net Revenue (after discount): {settings.currency} 0.00")
        self._net_revenue_lbl.setStyleSheet("font-size: 12px; font-weight: 600; color: #1e8449;")

        disc_layout.addWidget(self._total_discount_lbl)
        disc_layout.addWidget(self._gross_before_disc_lbl)
        disc_layout.addWidget(self._net_revenue_lbl)
        disc_layout.addStretch()
        root.addWidget(self._discount_frame)

        # ── Separator ─────────────────────────────────────────────────────
        sep2 = QWidget(); sep2.setFixedHeight(1)
        sep2.setStyleSheet("background: #ddd;")
        root.addWidget(sep2)

        # ── Best-selling medicines ─────────────────────────────────────────
        best_row = QHBoxLayout()
        best_row.addWidget(QLabel("Best-Selling Medicines"))
        best_row.addStretch()
        export_btn = QPushButton("Export CSV")
        export_btn.clicked.connect(self._export_best_sellers)
        best_row.addWidget(export_btn)
        root.addLayout(best_row)

        self.best_sellers_table = QTableWidget(0, 4)
        self.best_sellers_table.setHorizontalHeaderLabels([
            "Medicine", "Units Sold",
            f"Revenue ({settings.currency})",
            f"Profit ({settings.currency})"
        ])
        self.best_sellers_table.horizontalHeader().setStretchLastSection(True)
        self.best_sellers_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.best_sellers_table.setAlternatingRowColors(True)
        root.addWidget(self.best_sellers_table)

        # ── Stock valuation ────────────────────────────────────────────────
        root.addWidget(QLabel("Stock Valuation"))
        self.valuation_label = QLabel("")
        self.valuation_label.setStyleSheet(
            "font-size: 12px; padding: 6px; background: #f5f6fa; border-radius: 5px;"
        )
        root.addWidget(self.valuation_label)

        self.refresh()

    # ── Date helpers ──────────────────────────────────────────────────────

    def _get_range(self) -> tuple[date, date]:
        s, e = self.start_edit.date(), self.end_edit.date()
        return (date(s.year(), s.month(), s.day()),
                date(e.year(), e.month(), e.day()))

    # ── Refresh ───────────────────────────────────────────────────────────

    def refresh(self) -> None:
        start, end = self._get_range()
        try:
            financials = report_engine.sales_and_profit_report(start, end)
            self._best_sellers_cache = report_engine.best_selling_medicines(
                start, end, limit=20
            )
            valuation = report_engine.stock_valuation_report()
        except ApplicationError as exc:
            QMessageBox.warning(self, "Cannot run report", str(exc))
            return

        cur = settings.currency

        # ── Rebuild financial summary cards ────────────────────────────────
        # Clear old cards
        while self._summary_grid.count():
            item = self._summary_grid.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self._cards.clear()

        # Gross sales = revenue + discounts already deducted
        gross_sales = financials.revenue + financials.total_discount

        card_specs = [
            # (title, value, bg_colour, text_colour)
            ("Gross Sales (before disc.)",
             f"{cur} {gross_sales:.2f}", "#f0f4ff", "#154c89"),

            ("Total Discounts Given",
             f"- {cur} {financials.total_discount:.2f}", "#fff8e1", "#e65100"),

            ("Net Revenue (after disc.)",
             f"{cur} {financials.revenue:.2f}", "#eafaf1", "#1e8449"),

            ("Cost of Goods Sold (COGS)",
             f"{cur} {financials.cogs:.2f}", "#fdecea", "#c0392b"),

            ("Gross Profit",
             f"{cur} {financials.gross_profit:.2f}", "#eafaf1", "#1e8449"),

            ("Expenses",
             f"{cur} {financials.expenses:.2f}", "#fdecea", "#c0392b"),

            ("Net Profit",
             f"{cur} {financials.net_profit:.2f}",
             "#eafaf1" if financials.net_profit >= 0 else "#fdecea",
             "#1e8449" if financials.net_profit >= 0 else "#c0392b"),

            ("Returned Units",
             str(financials.returned_units), "#f5f6fa", "#555"),
        ]

        for idx, (title, value, bg, fg) in enumerate(card_specs):
            card = _summary_card(title, value, bg, fg)
            self._summary_grid.addWidget(card, idx // 4, idx % 4)

        # ── Discount section ───────────────────────────────────────────────
        self._total_discount_lbl.setText(
            f"Total Discount Given:  {cur} {financials.total_discount:.2f}"
        )
        self._gross_before_disc_lbl.setText(
            f"Gross Sales (before discount):  {cur} {gross_sales:.2f}"
        )
        self._net_revenue_lbl.setText(
            f"Net Revenue (after discount):  {cur} {financials.revenue:.2f}"
        )

        # ── Best sellers ───────────────────────────────────────────────────
        self.best_sellers_table.setRowCount(0)
        for row_data in self._best_sellers_cache:
            row = self.best_sellers_table.rowCount()
            self.best_sellers_table.insertRow(row)
            self.best_sellers_table.setItem(row, 0, QTableWidgetItem(row_data["name"]))

            units_item = QTableWidgetItem(str(row_data["units_sold"]))
            units_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter | Qt.AlignmentFlag.AlignVCenter)
            self.best_sellers_table.setItem(row, 1, units_item)

            rev_item = QTableWidgetItem(f"{row_data['revenue']:.2f}")
            rev_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self.best_sellers_table.setItem(row, 2, rev_item)

            profit_item = QTableWidgetItem(f"{row_data['profit']:.2f}")
            profit_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            if row_data["profit"] < 0:
                profit_item.setForeground(Qt.GlobalColor.red)
            self.best_sellers_table.setItem(row, 3, profit_item)

        self.best_sellers_table.resizeColumnsToContents()

        # ── Valuation ──────────────────────────────────────────────────────
        self.valuation_label.setText(
            f"{valuation['batch_count']} batches  |  "
            f"{valuation['total_units']} units  —  "
            f"Cost: {cur} {valuation['cost_value']:.2f}  |  "
            f"Retail: {cur} {valuation['retail_value']:.2f}  |  "
            f"Potential Gross Profit: {cur} {valuation['potential_gross_profit']:.2f}"
        )

    # ── Export ────────────────────────────────────────────────────────────

    def _export_best_sellers(self) -> None:
        if not self._best_sellers_cache:
            QMessageBox.information(self, "Nothing to export", "Run a report first.")
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "Export Best Sellers", "best_sellers.csv", "CSV Files (*.csv)"
        )
        if not path:
            return
        try:
            export_to_csv(self._best_sellers_cache, path)
            QMessageBox.information(self, "Exported", f"Saved to {path}")
        except Exception as exc:
            QMessageBox.critical(self, "Export failed", str(exc))
