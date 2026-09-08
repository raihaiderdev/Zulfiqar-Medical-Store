"""
UI smoke tests. Runs Qt in offscreen mode (set via QT_QPA_PLATFORM below,
before PySide6 is imported anywhere) so this works in a headless CI/sandbox
environment with no real display. Not a substitute for manual visual
review, but it does catch import errors, detached-ORM-instance bugs (see
the selectinload fix in inventory_repository.py, caught exactly this way),
and basic wiring mistakes in every page and dialog.
"""
from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from datetime import date, timedelta

import pytest

from app.services import medicine_service, party_service, purchase_service, sales_service

QApplication = pytest.importorskip("PySide6.QtWidgets").QApplication


@pytest.fixture(scope="module")
def qt_app():
    app = QApplication.instance() or QApplication([])
    yield app


@pytest.fixture(autouse=True)
def _admin_session(admin_logged_in):
    yield


def test_setup_wizard_and_login_window_instantiate(qt_app):
    from app.ui.login.login_window import LoginWindow
    from app.ui.setup_wizard.wizard import SetupWizard

    wizard = SetupWizard()
    assert wizard.pageIds()

    login = LoginWindow()
    assert login.windowTitle()


def test_main_window_builds_pages_for_admin(qt_app):
    from app.ui.main.main_window import MainWindow

    win = MainWindow(on_logout=lambda: None)
    labels = [win.nav_list.item(i).text() for i in range(win.nav_list.count())]
    assert "Dashboard" in labels
    assert "Users" in labels
    assert "Settings" in labels


def test_dashboard_page_renders(qt_app):
    from app.ui.dashboard.dashboard_page import DashboardPage

    page = DashboardPage()
    assert page.kpi_grid.count() > 0


def test_medicines_page_add_dialog(qt_app):
    from app.ui.medicines.medicines_page import AddMedicineDialog, MedicinesPage

    page = MedicinesPage()
    dialog = AddMedicineDialog()
    dialog.name_edit.setText("UI Smoke Test Medicine")
    dialog.barcode_edit.setText("UISMOKE001")
    dialog._save()
    page.refresh()
    names = [page.table.item(r, 1).text() for r in range(page.table.rowCount())]
    assert "UI Smoke Test Medicine" in names


def test_pos_page_full_sale_flow(qt_app, monkeypatch):
    from PySide6.QtWidgets import QMessageBox

    from app.ui.sales.pos_page import SalesPOSPage

    med_id = medicine_service.add_medicine(name="POS Smoke Med", barcode="POSSMOKE1")
    medicine_service.add_manual_batch(
        medicine_id=med_id, batch_number="PS-1", purchase_price=10, selling_price=20,
        quantity=30, expiry_date=date.today() + timedelta(days=200),
    )

    monkeypatch.setattr(QMessageBox, "question", staticmethod(lambda *a, **k: QMessageBox.StandardButton.No))
    monkeypatch.setattr(QMessageBox, "information", staticmethod(lambda *a, **k: None))

    page = SalesPOSPage()
    page.search_edit.setText("POS Smoke Med")
    page._search()
    assert page.results_list.count() == 1

    page.results_list.setCurrentRow(0)
    page.quantity_spin.setValue(2)
    page._add_selected_to_cart()
    assert len(page.cart) == 1

    page.amount_paid_edit.setText("40")
    page._complete_sale()
    assert len(page.cart) == 0  # cleared after a successful sale


def test_purchases_page_submit(qt_app, monkeypatch):
    from PySide6.QtWidgets import QMessageBox

    from app.ui.purchases.purchases_page import PurchasesPage

    monkeypatch.setattr(QMessageBox, "information", staticmethod(lambda *a, **k: None))
    monkeypatch.setattr(QMessageBox, "warning", staticmethod(lambda *a, **k: None))
    monkeypatch.setattr(QMessageBox, "critical", staticmethod(lambda *a, **k: None))

    medicine_service.add_medicine(name="Purchase UI Med")
    party_service.add_supplier("Purchase UI Supplier")

    page = PurchasesPage()
    page._reload_dropdowns()
    idx = page.medicine_combo.findText("Purchase UI Med")
    assert idx >= 0
    page.medicine_combo.setCurrentIndex(idx)
    sup_idx = page.supplier_combo.findText("Purchase UI Supplier")
    page.supplier_combo.setCurrentIndex(sup_idx)

    page.batch_number_edit.setText("PUI-1")
    page.purchase_price_edit.setText("5")
    page.selling_price_edit.setText("8")
    page.quantity_spin.setValue(10)
    page._submit()
    assert page.history_table.rowCount() >= 1


def test_inventory_and_reports_pages_render(qt_app):
    from app.ui.inventory.inventory_page import InventoryPage
    from app.ui.reports.reports_page import ReportsPage

    inv = InventoryPage()
    inv.refresh()
    reports = ReportsPage()
    reports.refresh()  # should not raise even with sparse data


def test_users_and_settings_pages_admin_only(qt_app, monkeypatch):
    from PySide6.QtWidgets import QMessageBox

    from app.ui.settings.settings_page import SettingsPage
    from app.ui.users.users_page import AddUserDialog, UsersPage

    monkeypatch.setattr(QMessageBox, "information", staticmethod(lambda *a, **k: None))
    monkeypatch.setattr(QMessageBox, "warning", staticmethod(lambda *a, **k: None))
    monkeypatch.setattr(QMessageBox, "critical", staticmethod(lambda *a, **k: None))

    users_page = UsersPage()
    dialog = AddUserDialog()
    dialog.username_edit.setText("ui_smoke_user")
    dialog.password_edit.setText("UiSmokePass123!")
    dialog.permission_checkboxes["medicine.view"].setChecked(True)
    dialog._save()
    users_page.refresh()
    usernames = [users_page.table.item(r, 1).text() for r in range(users_page.table.rowCount())]
    assert "ui_smoke_user" in usernames

    settings_page = SettingsPage()
    settings_page.name_edit.setText("UI Smoke Pharmacy")
    settings_page._save()
    settings_page.refresh()
    assert settings_page.name_edit.text() == "UI Smoke Pharmacy"
