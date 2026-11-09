"""
Dashboard page.

Features implemented:
  F1 — Every KPI card is clickable and navigates to the correct section.
  F2 — Expiry alert badge shown on dashboard; alert fires once per session.
"""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.config.settings import settings
from app.services import dashboard_service
from app.ui.common.expiry_alert import ExpiryAlertManager
from app.utils.exceptions import ApplicationError


class _KpiCard(QFrame):
    """A clickable KPI card that emits `clicked` when the user presses it."""

    clicked = Signal()

    def __init__(self, title: str, value: str, *, clickable: bool = True,
                 accent_colour: str = "#f5f6fa") -> None:
        super().__init__()
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setStyleSheet(
            f"QFrame {{ background: {accent_colour}; border-radius: 8px; padding: 4px; }}"
            "QFrame:hover { background: #dce8f5; border: 1px solid #2288cc; }"
            if clickable else
            f"QFrame {{ background: {accent_colour}; border-radius: 8px; padding: 4px; }}"
        )
        if clickable:
            self.setCursor(Qt.CursorShape.PointingHandCursor)

        layout = QVBoxLayout(self)
        self.value_label = QLabel(value)
        self.value_label.setStyleSheet("font-size: 20px; font-weight: 700;")
        self.title_label = QLabel(title)
        self.title_label.setStyleSheet("color: #666; font-size: 11px;")
        layout.addWidget(self.value_label)
        layout.addWidget(self.title_label)

    def mousePressEvent(self, event) -> None:  # noqa: ANN001
        self.clicked.emit()
        super().mousePressEvent(event)

    def update_value(self, value: str) -> None:
        self.value_label.setText(value)


class DashboardPage(QWidget):
    # Signal emitted when user clicks a card — the main window listens to
    # navigate to the right page.
    navigate_to = Signal(str)   # page label e.g. "Medicines", "Inventory"

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        root = QVBoxLayout(self)

        # ── Header ─────────────────────────────────────────────────────────
        header_row = QHBoxLayout()
        header = QLabel("Dashboard")
        header.setStyleSheet("font-size: 18px; font-weight: 600;")
        header_row.addWidget(header)
        header_row.addStretch()

        # F2: Expiry alert button / badge
        self._expiry_badge = QPushButton("⚠ Loading expiry data…")
        self._expiry_badge.setStyleSheet(
            "background: #e67e22; color: white; font-weight: 700; "
            "padding: 4px 12px; border-radius: 4px; font-size: 12px;"
        )
        self._expiry_badge.clicked.connect(self._show_expiry_alert)
        self._expiry_badge.setVisible(False)
        header_row.addWidget(self._expiry_badge)

        # Quick restore button on dashboard
        restore_btn = QPushButton("📂  Restore Backup")
        restore_btn.setStyleSheet(
            "background: #2980b9; color: white; font-weight: 600; "
            "padding: 4px 12px; border-radius: 4px; font-size: 12px;"
        )
        restore_btn.setToolTip("Restore database from a backup file")
        restore_btn.clicked.connect(self._restore_backup)
        header_row.addWidget(restore_btn)

        refresh_btn = QPushButton("Refresh")
        refresh_btn.clicked.connect(self.refresh)
        header_row.addWidget(refresh_btn)
        root.addLayout(header_row)

        # ── Scroll area ─────────────────────────────────────────────────────
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        content = QWidget()
        self.content_layout = QVBoxLayout(content)
        scroll.setWidget(content)
        root.addWidget(scroll)

        self.kpi_grid_container = QWidget()
        self.kpi_grid = QGridLayout(self.kpi_grid_container)
        self.kpi_grid.setSpacing(12)
        self.content_layout.addWidget(self.kpi_grid_container)

        self.content_layout.addWidget(QLabel("Sales by period"))
        self.sales_table = QTableWidget(0, 4)
        self.sales_table.setHorizontalHeaderLabels(["Period", "Sales (Net)", "Discount Given", "Gross Profit"])
        self.sales_table.horizontalHeader().setStretchLastSection(True)
        self.sales_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.content_layout.addWidget(self.sales_table)

        # ── Today's Sales Summary strip ────────────────────────────────────
        today_header = QLabel("📊  Today's Sales Summary")
        today_header.setStyleSheet("font-size: 13px; font-weight: 700; margin-top: 8px;")
        self.content_layout.addWidget(today_header)

        self._today_frame = QFrame()
        self._today_frame.setStyleSheet(
            "QFrame { background: #eafaf1; border-radius: 8px; "
            "border: 1px solid #a9dfbf; padding: 6px; }"
        )
        today_layout = QHBoxLayout(self._today_frame)
        today_layout.setContentsMargins(16, 10, 16, 10)
        today_layout.setSpacing(40)

        def _summary_label(title: str, value: str = "—", colour: str = "#1e8449") -> QVBoxLayout:
            v = QVBoxLayout()
            v.setSpacing(2)
            val_lbl = QLabel(value)
            val_lbl.setStyleSheet(f"font-size: 18px; font-weight: 700; color: {colour};")
            ttl_lbl = QLabel(title)
            ttl_lbl.setStyleSheet("font-size: 11px; color: #666;")
            v.addWidget(val_lbl)
            v.addWidget(ttl_lbl)
            return v, val_lbl   # return layout + the mutable label

        lay_sales, self._today_sales_lbl     = _summary_label("Total Sales (Net)",    colour="#1e8449")
        lay_disc,  self._today_disc_lbl      = _summary_label("Total Discount",       colour="#e65100")
        lay_cost,  self._today_cogs_lbl      = _summary_label("Cost of Goods (COGS)", colour="#c0392b")
        lay_profit,self._today_profit_lbl    = _summary_label("Gross Profit",         colour="#154c89")
        lay_orders,self._today_orders_lbl    = _summary_label("No. of Orders",        colour="#555")
        lay_fees,  self._today_fees_lbl      = _summary_label("Doctor Fees",          colour="#7d6608")

        for lay in (lay_sales, lay_disc, lay_cost, lay_profit, lay_orders, lay_fees):
            today_layout.addLayout(lay)
        today_layout.addStretch()
        self.content_layout.addWidget(self._today_frame)

        # ── Last Completed Order panel ────────────────────────────────────
        last_order_header = QLabel("🧾  Last Completed Order")
        last_order_header.setStyleSheet("font-size: 13px; font-weight: 700; margin-top: 8px;")
        self.content_layout.addWidget(last_order_header)

        self._last_order_frame = QFrame()
        self._last_order_frame.setStyleSheet(
            "QFrame { background: #f9fafb; border-radius: 8px; "
            "border: 1px solid #dee2e6; padding: 6px; }"
        )
        last_order_outer = QVBoxLayout(self._last_order_frame)
        last_order_outer.setContentsMargins(12, 8, 12, 8)
        last_order_outer.setSpacing(6)

        # Invoice header row
        self._order_header_lbl = QLabel("No sale recorded yet today")
        self._order_header_lbl.setWordWrap(True)
        self._order_header_lbl.setStyleSheet(
            "font-size: 12px; font-weight: 600; color: #154c89; "
            "background: #eaf4fb; border-radius: 4px; padding: 6px 10px; "
            "border: 1px solid #aed6f1;"
        )
        last_order_outer.addWidget(self._order_header_lbl)

        # Items table
        self._order_table = QTableWidget(0, 5)
        self._order_table.setHorizontalHeaderLabels([
            "Medicine", "Qty",
            f"Unit Price ({settings.currency})",
            f"Discount ({settings.currency})",
            f"Line Total ({settings.currency})"
        ])

        hh = self._order_table.horizontalHeader()
        hh.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)          # Medicine — fills space
        hh.setSectionResizeMode(1, QHeaderView.ResizeMode.Fixed)             # Qty
        hh.setSectionResizeMode(2, QHeaderView.ResizeMode.Fixed)             # Unit Price
        hh.setSectionResizeMode(3, QHeaderView.ResizeMode.Fixed)             # Discount
        hh.setSectionResizeMode(4, QHeaderView.ResizeMode.Fixed)             # Line Total
        self._order_table.setColumnWidth(1, 55)                              # Qty
        self._order_table.setColumnWidth(2, 130)                             # Unit Price
        self._order_table.setColumnWidth(3, 120)                             # Discount
        self._order_table.setColumnWidth(4, 120)                             # Line Total

        self._order_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._order_table.setSelectionMode(QTableWidget.SelectionMode.NoSelection)
        self._order_table.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._order_table.setAlternatingRowColors(True)
        self._order_table.verticalHeader().setVisible(False)
        self._order_table.setShowGrid(True)
        self._order_table.setStyleSheet(
            "QTableWidget { border: 1px solid #dee2e6; border-radius: 4px; "
            "font-size: 12px; gridline-color: #e9ecef; }"
            "QHeaderView::section { background: #f8f9fa; border: none; "
            "border-bottom: 2px solid #dee2e6; padding: 5px 8px; "
            "font-weight: 600; font-size: 12px; color: #495057; }"
            "QTableWidget::item { padding: 5px 8px; }"
        )
        self._order_table.setMinimumHeight(80)
        self._order_table.setMaximumHeight(220)
        last_order_outer.addWidget(self._order_table)

        # Totals strip — styled card row below the table
        totals_strip = QFrame()
        totals_strip.setStyleSheet(
            "QFrame { background: #f8f9fa; border-radius: 6px; "
            "border: 1px solid #dee2e6; padding: 2px; }"
        )
        totals_row = QHBoxLayout(totals_strip)
        totals_row.setContentsMargins(14, 8, 14, 8)
        totals_row.setSpacing(0)

        def _order_kpi(title: str, colour: str = "#333"):
            """Returns (outer QFrame, mutable value QLabel)."""
            card = QFrame()
            card.setStyleSheet("QFrame { border: none; }")
            v = QVBoxLayout(card)
            v.setContentsMargins(12, 4, 12, 4)
            v.setSpacing(2)
            val = QLabel("—")
            val.setStyleSheet(
                f"font-weight: 700; font-size: 15px; color: {colour};"
            )
            lbl = QLabel(title)
            lbl.setStyleSheet("font-size: 11px; color: #888;")
            v.addWidget(val)
            v.addWidget(lbl)
            return card, val

        # Vertical divider helper
        def _vdiv():
            d = QFrame()
            d.setFrameShape(QFrame.Shape.VLine)
            d.setStyleSheet("color: #dee2e6;")
            return d

        card_ot,   self._order_total_lbl  = _order_kpi(f"Total ({settings.currency})", "#154c89")
        card_od,   self._order_disc_lbl   = _order_kpi(f"Discount ({settings.currency})", "#e65100")
        card_ofee, self._order_fee_lbl    = _order_kpi(f"Doctor Fee ({settings.currency})", "#7d6608")
        card_op,   self._order_profit_lbl = _order_kpi(f"Profit ({settings.currency})", "#1e8449")
        card_oc,   self._order_change_lbl = _order_kpi("Change Due",                    "#555")

        for i, card in enumerate((card_ot, card_od, card_ofee, card_op, card_oc)):
            totals_row.addWidget(card)
            if i < 4:
                totals_row.addWidget(_vdiv())
        totals_row.addStretch()

        last_order_outer.addWidget(totals_strip)

        self.content_layout.addWidget(self._last_order_frame)
        self.content_layout.addStretch()

        self._cards: dict[str, _KpiCard] = {}
        self._last_refresh_time: float = 0.0  # epoch seconds; 0 = never refreshed

        # Connect to the sale event bus so the last-order panel updates live
        try:
            from app.ui.common.sale_event_bus import sale_bus
            sale_bus.sale_completed.connect(self._on_sale_completed)
        except Exception:
            pass

        self.refresh()

    def showEvent(self, event) -> None:
        """Auto-refresh when the dashboard becomes visible, but only if the
        data is stale (older than 10 seconds) to avoid an expensive reload
        on every rapid sidebar click."""
        super().showEvent(event)
        import time
        if time.monotonic() - self._last_refresh_time > 10:
            self.refresh()

    def refresh(self) -> None:
        try:
            kpis = dashboard_service.admin_dashboard_kpis()
        except ApplicationError as exc:
            QMessageBox.warning(self, "Cannot load dashboard", str(exc))
            return

        # ── KPI cards ──────────────────────────────────────────────────────
        cur = settings.currency
        card_specs = [
            ("Total Medicines",    str(kpis["total_medicines"]),        "Medicines",  "#eaf4fb"),
            ("Total Stock Units",  str(kpis["total_stock_quantity"]),   "Inventory",  "#eaf4fb"),
            ("Low Stock Items",    str(kpis["low_stock_count"]),        "Inventory",  "#fff8e1"),
            ("Expired Batches",    str(kpis["expired_count"]),          "Inventory",  "#fdecea"),
            ("Expiring Soon",      str(kpis["expiring_soon_count"]),    "Inventory",  "#fff3e0"),
            ("Active Users",       str(kpis["active_user_count"]),      "Users",      "#eaf4fb"),
            ("Total Purchases",    f"{cur} {kpis['total_purchases_value']:.2f}",
             "Purchases", "#eaf4fb"),
            ("Stock Value (Cost)", f"{cur} {kpis['stock_valuation']['cost_value']:.2f}",
             "Inventory",  "#eaf4fb"),
            ("Stock Value (Retail)", f"{cur} {kpis['stock_valuation']['retail_value']:.2f}",
             "Inventory",  "#eaf4fb"),
        ]

        # ── Phase 1: Intelligence summary cards (admin only) ───────────────
        intel = kpis.get("intelligence")
        if intel:
            waste_val = intel.get("potential_waste_value", 0)
            card_specs += [
                ("📦 Need Reorder",
                 str(intel.get("items_needing_reorder", 0)),
                 "📦 Reorder Suggestions", "#e8f4fd"),
                ("💤 Dead Stock Items",
                 str(intel.get("dead_stock_count", 0)),
                 "💤 Dead Stock", "#fdecea"),
                (f"⚠ Potential Waste",
                 f"{cur} {waste_val:,.0f}",
                 "⚠ Expiry Risk", "#fff3e0"),
            ]

        # Rebuild grid
        while self.kpi_grid.count():
            item = self.kpi_grid.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self._cards.clear()

        for idx, (title, value, nav_target, colour) in enumerate(card_specs):
            card = _KpiCard(title, value, clickable=True, accent_colour=colour)
            card.clicked.connect(lambda t=nav_target: self.navigate_to.emit(t))
            self.kpi_grid.addWidget(card, idx // 3, idx % 3)
            self._cards[title] = card

        # ── Sales table ────────────────────────────────────────────────────
        self.sales_table.setRowCount(0)
        for period_label, values in kpis["sales"].items():
            row = self.sales_table.rowCount()
            self.sales_table.insertRow(row)
            self.sales_table.setItem(row, 0, QTableWidgetItem(
                period_label.replace("_", " ").title()
            ))
            self.sales_table.setItem(row, 1, QTableWidgetItem(
                f"{cur} {values['sales']:.2f}"
            ))
            disc_item = QTableWidgetItem(f"- {cur} {values.get('discount', 0):.2f}")
            disc_item.setForeground(__import__("PySide6.QtCore", fromlist=["Qt"]).Qt.GlobalColor.darkYellow)
            self.sales_table.setItem(row, 2, disc_item)
            self.sales_table.setItem(row, 3, QTableWidgetItem(
                f"{cur} {values['profit']:.2f}"
            ))

        # ── Expiry badge (F2) ──────────────────────────────────────────────
        counts = ExpiryAlertManager.alert_count()
        if counts["total"] > 0:
            parts = []
            if counts["expired"]:
                parts.append(f"{counts['expired']} expired")
            if counts["very_soon"]:
                parts.append(f"{counts['very_soon']} expiring very soon")
            if counts["soon"]:
                parts.append(f"{counts['soon']} expiring soon")
            self._expiry_badge.setText(f"⚠  {' | '.join(parts)}  — Click to view")
            self._expiry_badge.setVisible(True)
        else:
            self._expiry_badge.setVisible(False)

        import time
        self._last_refresh_time = time.monotonic()

        # Update today's summary strip using the already-loaded KPI data
        self._update_today_summary(kpis["sales"].get("today", {}))

    # ── Today's Summary + Last Order ─────────────────────────────────────

    def _update_today_summary(self, today_kpi: dict) -> None:
        """Refresh the Today's Sales strip from KPI data (no extra DB call)."""
        cur = settings.currency
        sales   = today_kpi.get("sales", 0.0)
        disc    = today_kpi.get("discount", 0.0)
        profit  = today_kpi.get("profit", 0.0)
        # COGS = sales - profit  (from the aggregate query)
        cogs    = round(sales - profit, 2)
        fees    = today_kpi.get("doctor_fees", 0.0)

        # Order count — lightweight query
        try:
            from datetime import date
            from app.database.session import session_scope
            from app.models import Sale
            from app.models.enums import SaleStatus
            from sqlalchemy import func
            with session_scope() as session:
                orders_today = int(
                    session.query(func.count(Sale.id))
                    .filter(Sale.sale_date == date.today(), Sale.status == SaleStatus.COMPLETED)
                    .scalar() or 0
                )
        except Exception:
            orders_today = 0

        self._today_sales_lbl.setText(f"{cur} {sales:,.2f}")
        self._today_disc_lbl.setText(f"- {cur} {disc:,.2f}")
        self._today_cogs_lbl.setText(f"{cur} {cogs:,.2f}")
        self._today_profit_lbl.setText(f"{cur} {profit:,.2f}")
        self._today_orders_lbl.setText(str(orders_today))
        self._today_fees_lbl.setText(f"{cur} {fees:,.2f}")

    def _on_sale_completed(self, sale_id: int) -> None:
        """Called immediately when a sale is completed from the POS page.
        Updates ALL dashboard sections so totals are current right away."""
        # Always update the last order panel
        self._update_last_order(sale_id)

        # Rerun the full refresh so Sales by Period table, KPI cards,
        # and Today's Summary all reflect the new sale instantly.
        # Reset the cooldown timer so showEvent also allows an immediate refresh.
        self._last_refresh_time = 0.0
        self.refresh()

    def _update_last_order(self, sale_id: int) -> None:
        """Load and display the detail of the most recently completed sale."""
        try:
            from app.services.sales_service import get_sale_detail
            detail = get_sale_detail(sale_id)
        except Exception:
            return

        cur = settings.currency
        inv = detail.get("invoice_number", "")
        sale_date = detail.get("date", "")
        total     = float(detail.get("total", 0))
        disc      = float(detail.get("discount_total", 0))
        paid      = float(detail.get("amount_paid", 0))
        change    = float(detail.get("change_due", 0))
        items     = detail.get("items", [])

        # Compute profit from line items
        profit = sum(
            float(i.get("line_profit", 0)) for i in items
        )

        # Doctor fee for this sale (linked by invoice number)
        doc_fee = 0.0
        try:
            from app.services.doctor_fee_service import list_doctor_fees
            fees = list_doctor_fees()
            for f in fees:
                if f.get("sale_reference") == inv and f.get("status") == "ACTIVE":
                    doc_fee += float(f.get("amount", 0))
        except Exception:
            pass

        # Update header
        self._order_header_lbl.setText(
            f"📋  Invoice: {inv}   |   Date: {sale_date}   |   "
            f"Paid: {cur} {paid:.2f}   |   Change: {cur} {change:.2f}"
        )

        # Populate items table
        self._order_table.setUpdatesEnabled(False)
        self._order_table.setRowCount(0)
        for item in items:
            row = self._order_table.rowCount()
            self._order_table.insertRow(row)
            self._order_table.setItem(row, 0, QTableWidgetItem(item.get("medicine_name", "")))

            qty_item = QTableWidgetItem(str(item.get("quantity", 0)))
            qty_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter | Qt.AlignmentFlag.AlignVCenter)
            self._order_table.setItem(row, 1, qty_item)

            price_item = QTableWidgetItem(f"{float(item.get('unit_price', 0)):.2f}")
            price_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self._order_table.setItem(row, 2, price_item)

            disc_item = QTableWidgetItem(f"{float(item.get('line_discount', 0)):.2f}")
            disc_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self._order_table.setItem(row, 3, disc_item)

            line_total = float(item.get("unit_price", 0)) * item.get("quantity", 0) - float(item.get("line_discount", 0))
            lt_item = QTableWidgetItem(f"{line_total:.2f}")
            lt_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self._order_table.setItem(row, 4, lt_item)

        # Add doctor fee as an extra row if present
        if doc_fee > 0:
            from PySide6.QtGui import QColor
            row = self._order_table.rowCount()
            self._order_table.insertRow(row)
            fee_name = QTableWidgetItem("👨‍⚕️  Doctor Fee")
            fee_name.setForeground(QColor("#7d6608"))
            self._order_table.setItem(row, 0, fee_name)
            self._order_table.setItem(row, 1, QTableWidgetItem("—"))
            self._order_table.setItem(row, 2, QTableWidgetItem("—"))
            self._order_table.setItem(row, 3, QTableWidgetItem("—"))
            fee_amt = QTableWidgetItem(f"{doc_fee:.2f}")
            fee_amt.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            from PySide6.QtGui import QFont
            f = QFont(); f.setBold(True)
            fee_amt.setFont(f)
            fee_amt.setForeground(QColor("#7d6608"))
            self._order_table.setItem(row, 4, fee_amt)

        self._order_table.setUpdatesEnabled(True)

        # Update totals
        self._order_total_lbl.setText(f"{cur} {total:.2f}")
        self._order_disc_lbl.setText(f"- {cur} {disc:.2f}" if disc > 0 else "—")
        self._order_fee_lbl.setText(f"{cur} {doc_fee:.2f}" if doc_fee > 0 else "—")
        self._order_profit_lbl.setText(f"{cur} {profit:.2f}")
        self._order_change_lbl.setText(f"{cur} {change:.2f}")

    def _show_expiry_alert(self) -> None:
        ExpiryAlertManager.show_alert_forced(self)

    def _restore_backup(self) -> None:
        from PySide6.QtWidgets import QFileDialog
        from app.services import backup_service
        from pathlib import Path
        from app.config.settings import BACKUP_DIR

        path, _ = QFileDialog.getOpenFileName(
            self, "Select Backup File to Restore",
            str(BACKUP_DIR), "SQLite Database (*.db);;All Files (*)"
        )
        if not path:
            return

        confirm = QMessageBox.warning(
            self, "Confirm Restore",
            "Restoring will replace the CURRENT database with the selected backup.\n\n"
            "A safety copy of the current database will be saved first.\n\n"
            f"Backup file: {path}\n\n"
            "Continue?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return

        try:
            safety = backup_service.restore_backup(Path(path))
        except ApplicationError as exc:
            QMessageBox.critical(self, "Restore failed", str(exc))
            return

        QMessageBox.information(
            self, "✔  Database Restored",
            f"Database successfully restored from:\n{path}\n\n"
            f"Safety backup of previous data saved to:\n{safety}\n\n"
            "Please restart the application for all changes to take effect."
        )
        self.refresh()
