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

        self._cards: dict[str, _KpiCard] = {}

        self.refresh()

    def showEvent(self, event) -> None:
        """Auto-refresh whenever the dashboard becomes visible — ensures
        the expired count and badge always reflect the latest DB state
        without requiring the user to click Refresh manually."""
        super().showEvent(event)
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
