"""
Main window — sidebar navigation + permission-gated pages.

Features implemented:
  F1 — DashboardPage.navigate_to signal wired to navigate_to_label().
       Every sidebar entry is already functional (QListWidget → QStackedWidget).
  F2 — Expiry alert fires on first load via DashboardPage (session-once).
"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon, QPixmap
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from app.security.session_context import current_session
from app.services import auth_service
from app.utils.assets import asset_path


class MainWindow(QMainWindow):
    def __init__(self, on_logout) -> None:
        super().__init__()
        self._on_logout = on_logout
        self._page_labels: list[str] = []       # parallel list to nav_list rows
        self.setWindowTitle("Zulfiqar Medical Store — Pharmacy Management")
        self.resize(1280, 800)
        self.setWindowIcon(QIcon(asset_path("assets/icons/app.ico")))

        central = QWidget()
        root_layout = QHBoxLayout(central)

        # ── Sidebar ────────────────────────────────────────────────────────
        sidebar = QWidget()
        sidebar.setFixedWidth(210)
        sidebar.setStyleSheet("background-color: #f0f4f8;")
        sidebar_layout = QVBoxLayout(sidebar)
        sidebar_layout.setContentsMargins(0, 0, 0, 0)
        sidebar_layout.setSpacing(0)

        logo_label = QLabel()
        logo_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        logo_pixmap = QPixmap(asset_path("assets/icons/logo_64.png"))
        if not logo_pixmap.isNull():
            logo_label.setPixmap(
                logo_pixmap.scaled(
                    56, 56,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
            )
        logo_label.setStyleSheet("padding: 10px 0 4px 0;")
        sidebar_layout.addWidget(logo_label)

        store_label = QLabel("Zulfiqar Medical Store")
        store_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        store_label.setWordWrap(True)
        store_label.setStyleSheet(
            "font-size: 11px; font-weight: 700; color: #154c89; padding: 0 6px 6px 6px;"
        )
        sidebar_layout.addWidget(store_label)

        div1 = QWidget()
        div1.setFixedHeight(1)
        div1.setStyleSheet("background-color: #c8d6e5;")
        sidebar_layout.addWidget(div1)

        role = "Administrator" if current_session.is_admin else "User"
        who_label = QLabel(f"{current_session.username}\n({role})")
        who_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        who_label.setStyleSheet(
            "font-weight: 600; font-size: 12px; padding: 8px; color: #333;"
        )
        sidebar_layout.addWidget(who_label)

        div2 = QWidget()
        div2.setFixedHeight(1)
        div2.setStyleSheet("background-color: #c8d6e5;")
        sidebar_layout.addWidget(div2)

        self.nav_list = QListWidget()
        self.nav_list.setStyleSheet("""
            QListWidget { border: none; background: transparent; font-size: 13px; }
            QListWidget::item { padding: 10px 14px; }
            QListWidget::item:selected {
                background-color: #2288cc; color: white; border-radius: 4px;
            }
            QListWidget::item:hover:!selected { background-color: #dce8f5; }
        """)
        sidebar_layout.addWidget(self.nav_list, 1)

        logout_button = QPushButton("⏻  Logout")
        logout_button.setStyleSheet("""
            QPushButton {
                background-color: #e74c3c; color: white; border: none;
                padding: 10px; font-size: 13px; font-weight: 600;
            }
            QPushButton:hover { background-color: #c0392b; }
        """)
        logout_button.clicked.connect(self._logout)
        sidebar_layout.addWidget(logout_button)

        root_layout.addWidget(sidebar)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        # ── Page stack ─────────────────────────────────────────────────────
        self.stack = QStackedWidget()
        root_layout.addWidget(self.stack, 1)

        self.setCentralWidget(central)

        self._build_pages()
        self.nav_list.currentRowChanged.connect(self.stack.setCurrentIndex)
        if self.nav_list.count():
            self.nav_list.setCurrentRow(0)

    # ── Page construction ─────────────────────────────────────────────────

    def _add_page(self, label: str, widget: QWidget) -> None:
        self._page_labels.append(label)
        self.nav_list.addItem(QListWidgetItem(label))
        self.stack.addWidget(widget)

    def _build_pages(self) -> None:
        has_perm = current_session.has_permission

        if current_session.is_admin:
            from app.ui.dashboard.dashboard_page import DashboardPage
            dash = DashboardPage()
            # F1: connect dashboard card clicks → sidebar navigation
            dash.navigate_to.connect(self.navigate_to_label)
            self._add_page("Dashboard", dash)

        if has_perm("medicine.view"):
            from app.ui.medicines.medicines_page import MedicinesPage
            self._add_page("Medicines", MedicinesPage())

        if has_perm("stock.view"):
            from app.ui.inventory.inventory_page import InventoryPage
            self._add_page("Inventory", InventoryPage())

        # ── Phase 1: Smart Inventory Intelligence pages ────────────────────
        if has_perm("stock.intelligence"):
            from app.ui.inventory.reorder_page import ReorderPage
            self._add_page("📦 Reorder Suggestions", ReorderPage())

            from app.ui.inventory.expiry_risk_page import ExpiryRiskPage
            self._add_page("⚠ Expiry Risk", ExpiryRiskPage())

            from app.ui.inventory.dead_stock_page import DeadStockPage
            self._add_page("💤 Dead Stock", DeadStockPage())

            from app.ui.inventory.analytics_page import InventoryAnalyticsPage
            self._add_page("📊 Inv. Analytics", InventoryAnalyticsPage())

        if has_perm("sales.create"):
            from app.ui.sales.pos_page import SalesPOSPage
            self._add_page("Sales / POS", SalesPOSPage())

        if has_perm("sales.view"):
            from app.ui.sales.sales_history_page import SalesHistoryPage
            self._add_page("Sales History", SalesHistoryPage())

        if has_perm("purchases.manage"):
            from app.ui.purchases.purchases_page import PurchasesPage
            self._add_page("Purchases", PurchasesPage())

        # Phase 2: Purchase Orders
        if has_perm("purchase_orders.create"):
            from app.ui.purchase_orders.purchase_orders_page import PurchaseOrdersPage
            self._add_page("📋 Purchase Orders", PurchaseOrdersPage())

        if has_perm("customers.manage"):
            from app.ui.customers.customers_page import CustomersPage
            self._add_page("Customers", CustomersPage())

        if has_perm("suppliers.manage"):
            from app.ui.suppliers.suppliers_page import SuppliersPage
            self._add_page("Suppliers", SuppliersPage())

        if has_perm("purchases.manage"):
            from app.ui.expenses.expenses_page import ExpensesPage
            self._add_page("Expenses", ExpensesPage())

        if has_perm("reports.view"):
            from app.ui.reports.reports_page import ReportsPage
            self._add_page("Reports", ReportsPage())

        if current_session.is_admin:
            from app.ui.users.users_page import UsersPage
            from app.ui.settings.settings_page import SettingsPage
            self._add_page("Users", UsersPage())
            self._add_page("Settings", SettingsPage())

        if self.nav_list.count() == 0:
            self._add_page("Home", _NoAccessPage())

    # ── Navigation ────────────────────────────────────────────────────────

    def navigate_to_label(self, label: str) -> None:
        """Navigate to a sidebar page by its label string.
        Called by dashboard card clicks (F1) and any future code that needs
        programmatic navigation.
        """
        for idx, page_label in enumerate(self._page_labels):
            if page_label == label or page_label.startswith(label):
                self.nav_list.setCurrentRow(idx)
                return
        # Fuzzy fallback: partial match
        label_lower = label.lower()
        for idx, page_label in enumerate(self._page_labels):
            if label_lower in page_label.lower():
                self.nav_list.setCurrentRow(idx)
                return

    # ── Logout ────────────────────────────────────────────────────────────

    def _logout(self) -> None:
        from app.ui.common.expiry_alert import ExpiryAlertManager
        ExpiryAlertManager.reset_for_session()
        auth_service.logout()
        self._on_logout()


class _NoAccessPage(QWidget):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        label = QLabel(
            "Your account doesn't have any permissions assigned yet.\n"
            "Please contact an administrator."
        )
        label.setWordWrap(True)
        layout.addWidget(label)
