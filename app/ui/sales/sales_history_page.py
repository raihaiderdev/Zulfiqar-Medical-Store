"""
Sales History page — view all sales with date filter, per-sale detail,
and (for authorized users) an Edit Invoice action.
"""
from __future__ import annotations

from datetime import date

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDateEdit,
    QDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.config.settings import settings
from app.security.session_context import current_session
from app.services import sales_service
from app.utils.exceptions import ApplicationError


# ---------------------------------------------------------------------------
# Sale Detail dialog
# ---------------------------------------------------------------------------
class SaleDetailDialog(QDialog):
    def __init__(self, sale_id: int, invoice_number: str, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle(f"Invoice Detail — {invoice_number}")
        self.resize(700, 500)
        layout = QVBoxLayout(self)

        try:
            detail = sales_service.get_sale_detail(sale_id)
        except ApplicationError as exc:
            layout.addWidget(QLabel(f"Error loading sale: {exc}"))
            close_btn = QPushButton("Close")
            close_btn.clicked.connect(self.accept)
            layout.addWidget(close_btn)
            return

        # ── Summary row ───────────────────────────────────────────────────
        cur = settings.currency
        summary_row = QHBoxLayout()

        def _info(label: str, value: str) -> QVBoxLayout:
            col = QVBoxLayout()
            lbl = QLabel(label)
            lbl.setStyleSheet("font-size: 11px; color: #666;")
            val = QLabel(value)
            val.setStyleSheet("font-weight: 600; font-size: 13px;")
            col.addWidget(lbl)
            col.addWidget(val)
            return col

        summary_row.addLayout(_info("Invoice #",     detail["invoice_number"]))
        summary_row.addLayout(_info("Date",          detail["date"]))
        summary_row.addLayout(_info("Status",        detail["status"]))
        summary_row.addLayout(_info("Subtotal",      f"{cur} {detail['subtotal']:.2f}"))
        summary_row.addLayout(_info("Discount",      f"{cur} {detail['discount_total']:.2f}"))
        summary_row.addLayout(_info("Total",         f"{cur} {detail['total']:.2f}"))
        summary_row.addLayout(_info("Paid",          f"{cur} {detail['amount_paid']:.2f}"))
        summary_row.addLayout(_info("Change Due",    f"{cur} {detail['change_due']:.2f}"))
        layout.addLayout(summary_row)

        # divider
        div = QWidget()
        div.setFixedHeight(1)
        div.setStyleSheet("background: #ddd;")
        layout.addWidget(div)

        # ── Line items table ──────────────────────────────────────────────
        items_label = QLabel("Line Items")
        items_label.setStyleSheet("font-weight: 600; margin-top: 8px;")
        layout.addWidget(items_label)

        table = QTableWidget(0, 7)
        table.setHorizontalHeaderLabels([
            "Medicine", "Batch", "Qty", "Unit Price",
            "Unit Cost", "Discount", "Line Total"
        ])
        table.horizontalHeader().setStretchLastSection(True)
        table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        table.setAlternatingRowColors(True)
        layout.addWidget(table)

        for item in detail["items"]:
            row = table.rowCount()
            table.insertRow(row)
            table.setItem(row, 0, QTableWidgetItem(item["medicine_name"]))
            table.setItem(row, 1, QTableWidgetItem(item["batch_number"]))
            table.setItem(row, 2, QTableWidgetItem(str(item["quantity"])))
            table.setItem(row, 3, QTableWidgetItem(f"{item['unit_price']:.2f}"))
            table.setItem(row, 4, QTableWidgetItem(f"{item['unit_cost']:.2f}"))
            table.setItem(row, 5, QTableWidgetItem(f"{item['line_discount']:.2f}"))
            table.setItem(row, 6, QTableWidgetItem(f"{item['line_total']:.2f}"))

        table.resizeColumnsToContents()

        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.accept)
        layout.addWidget(close_btn)


# ---------------------------------------------------------------------------
# Sales History page
# ---------------------------------------------------------------------------
class SalesHistoryPage(QWidget):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        root = QVBoxLayout(self)

        # ── Header ─────────────────────────────────────────────────────────
        header_row = QHBoxLayout()
        header = QLabel("Sales History")
        header.setStyleSheet("font-size: 18px; font-weight: 600;")
        header_row.addWidget(header)
        header_row.addStretch()
        self.total_label = QLabel("Total: Rs 0.00")
        self.total_label.setStyleSheet("font-weight: 600; font-size: 13px;")
        header_row.addWidget(self.total_label)
        root.addLayout(header_row)

        # ── Date filter ────────────────────────────────────────────────────
        filter_row = QHBoxLayout()
        filter_row.addWidget(QLabel("From:"))
        self.from_date = QDateEdit(calendarPopup=True)
        self.from_date.setDate(date.today().replace(day=1))
        filter_row.addWidget(self.from_date)
        filter_row.addWidget(QLabel("To:"))
        self.to_date = QDateEdit(calendarPopup=True)
        self.to_date.setDate(date.today())
        filter_row.addWidget(self.to_date)
        search_btn = QPushButton("Search")
        search_btn.clicked.connect(self.refresh)
        filter_row.addWidget(search_btn)
        filter_row.addStretch()
        root.addLayout(filter_row)

        # ── Table ─────────────────────────────────────────────────────────
        # Columns: Invoice #, Date, Total, Paid, Change, Status, View, Edit
        # "View" and "Edit" are separate columns so they never get squashed.
        can_edit = current_session.has_permission("sales.edit_invoice")
        col_count = 8 if can_edit else 7
        self.table = QTableWidget(0, col_count)
        headers = ["Invoice #", "Date", "Total (Rs)", "Paid (Rs)",
                   "Change (Rs)", "Status", "View"]
        if can_edit:
            headers.append("Edit")
        self.table.setHorizontalHeaderLabels(headers)
        self.table.horizontalHeader().setStretchLastSection(False)
        # Invoice # column stretches; action columns are fixed
        self.table.horizontalHeader().setSectionResizeMode(
            0, self.table.horizontalHeader().ResizeMode.Stretch
        )
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setAlternatingRowColors(True)
        root.addWidget(self.table)

        self._can_edit = can_edit
        self.refresh()

    def refresh(self) -> None:
        fd = self.from_date.date()
        td = self.to_date.date()
        date_from = date(fd.year(), fd.month(), fd.day())
        date_to   = date(td.year(), td.month(), td.day())

        try:
            sales = sales_service.list_sales(date_from=date_from, date_to=date_to)
        except ApplicationError as exc:
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.warning(self, "Cannot load sales", str(exc))
            return

        self.table.setRowCount(0)
        grand_total = 0.0

        STATUS_COLOURS = {
            "COMPLETED":         Qt.GlobalColor.darkGreen,
            "CANCELLED":         Qt.GlobalColor.red,
            "REFUNDED":          Qt.GlobalColor.darkMagenta,
            "PARTIALLY_REFUNDED": Qt.GlobalColor.darkYellow,
        }

        for s in sales:
            row = self.table.rowCount()
            self.table.insertRow(row)

            self.table.setItem(row, 0, QTableWidgetItem(s["invoice_number"]))
            self.table.setItem(row, 1, QTableWidgetItem(s["date"]))

            total_item = QTableWidgetItem(f"{s['total']:.2f}")
            total_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self.table.setItem(row, 2, total_item)

            paid_item = QTableWidgetItem(f"{s['amount_paid']:.2f}")
            paid_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self.table.setItem(row, 3, paid_item)

            change_item = QTableWidgetItem(f"{s['change_due']:.2f}")
            change_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self.table.setItem(row, 4, change_item)

            status = s["status"]
            status_item = QTableWidgetItem(status)
            status_item.setForeground(STATUS_COLOURS.get(status, Qt.GlobalColor.black))
            self.table.setItem(row, 5, status_item)

            # col 6 — View Details button
            view_btn = QPushButton("View Details")
            view_btn.setStyleSheet("padding: 3px 10px;")
            view_btn.clicked.connect(
                lambda _, sid=s["sale_id"], inv=s["invoice_number"]:
                    self._view_detail(sid, inv)
            )
            view_cell = QWidget()
            view_layout = QHBoxLayout(view_cell)
            view_layout.setContentsMargins(3, 2, 3, 2)
            view_layout.addWidget(view_btn)
            self.table.setCellWidget(row, 6, view_cell)

            # col 7 — Edit Invoice button (only when user has permission)
            if self._can_edit:
                edit_btn = QPushButton("✏  Edit Invoice")
                edit_btn.setStyleSheet(
                    "padding: 3px 10px; background-color: #2980b9; "
                    "color: white; font-weight: 600;"
                )
                edit_btn.clicked.connect(
                    lambda _, sid=s["sale_id"]: self._edit_invoice(sid)
                )
                edit_cell = QWidget()
                edit_layout = QHBoxLayout(edit_cell)
                edit_layout.setContentsMargins(3, 2, 3, 2)
                edit_layout.addWidget(edit_btn)
                self.table.setCellWidget(row, 7, edit_cell)

            grand_total += s["total"]

        self.total_label.setText(f"Total: {settings.currency} {grand_total:,.2f}")
        self.table.resizeColumnsToContents()

    def _view_detail(self, sale_id: int, invoice_number: str) -> None:
        dialog = SaleDetailDialog(sale_id, invoice_number, self)
        dialog.exec()

    def _edit_invoice(self, sale_id: int) -> None:
        from app.ui.sales.edit_invoice_dialog import EditInvoiceDialog
        dialog = EditInvoiceDialog(self, initial_sale_id=sale_id)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.refresh()
