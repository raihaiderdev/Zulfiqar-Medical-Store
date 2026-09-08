from __future__ import annotations

from datetime import date, timedelta

import pytest

from app.services import (
    backup_service,
    dashboard_service,
    medicine_service,
    party_service,
    purchase_service,
    sales_service,
)
from app.reports import report_engine
from app.utils.exceptions import ValidationError


@pytest.fixture(autouse=True)
def _admin_session(admin_logged_in):
    yield


def _sell_something(name_suffix="", quantity=5, selling_price=100, purchase_price=60):
    med_id = medicine_service.add_medicine(name=f"Report Med {name_suffix}")
    medicine_service.add_manual_batch(
        medicine_id=med_id, batch_number=f"RM-{name_suffix}", purchase_price=purchase_price,
        selling_price=selling_price, quantity=100, expiry_date=date.today() + timedelta(days=200),
    )
    sales_service.complete_sale(lines=[{"medicine_id": med_id, "quantity": quantity}], amount_paid=selling_price * quantity)
    return med_id


def test_sales_and_profit_report_computes_correctly():
    _sell_something(name_suffix="A", quantity=5, selling_price=100, purchase_price=60)
    today = date.today()
    financials = report_engine.sales_and_profit_report(today, today)
    assert financials.revenue >= 500
    assert financials.cogs >= 300
    assert financials.gross_profit >= 200


def test_best_selling_medicines_report():
    _sell_something(name_suffix="B", quantity=10, selling_price=50, purchase_price=20)
    today = date.today()
    rows = report_engine.best_selling_medicines(today, today, limit=5)
    assert len(rows) >= 1
    assert all("units_sold" in r for r in rows)


def test_stock_valuation_report():
    med_id = medicine_service.add_medicine(name="Valuation Med")
    medicine_service.add_manual_batch(
        medicine_id=med_id, batch_number="VAL-1", purchase_price=10, selling_price=15,
        quantity=20, expiry_date=date.today() + timedelta(days=200),
    )
    valuation = report_engine.stock_valuation_report()
    assert valuation["total_units"] >= 20
    assert valuation["cost_value"] >= 200
    assert valuation["retail_value"] >= 300


def test_close_month_snapshot_roundtrip():
    _sell_something(name_suffix="C", quantity=2, selling_price=100, purchase_price=50)
    today = date.today()
    payload = report_engine.close_month(today.year, today.month)
    fetched = report_engine.get_month_snapshot(today.year, today.month)
    assert fetched == payload
    assert fetched["revenue"] >= 200


def test_admin_dashboard_kpis_shape():
    _sell_something(name_suffix="D")
    kpis = dashboard_service.admin_dashboard_kpis()
    assert "total_medicines" in kpis
    assert "sales" in kpis
    assert "today" in kpis["sales"]
    assert "stock_valuation" in kpis


def test_backup_and_restore_roundtrip(tmp_path):
    med_id = medicine_service.add_medicine(name="Backup Test Med", barcode="BACKUPTEST1")

    backup_dir = tmp_path / "backups"
    backup_path = backup_service.create_backup(destination_dir=backup_dir)
    assert backup_path.exists()

    backup_service.validate_backup_file(backup_path)  # should not raise

    # Add more data after the backup, then restore — the post-backup data
    # should disappear, proving the restore actually swapped the file.
    medicine_service.add_medicine(name="Added After Backup", barcode="AFTERBACKUP1")

    safety_backup = backup_service.restore_backup(backup_path)
    assert safety_backup.exists()

    results = medicine_service.search_medicines("Added After Backup")
    assert len(results) == 0  # gone — we restored to the point before it existed

    results2 = medicine_service.search_medicines("Backup Test Med")
    assert len(results2) == 1


def test_restore_rejects_invalid_file(tmp_path):
    bad_file = tmp_path / "not_a_database.db"
    bad_file.write_text("this is not a sqlite database")
    with pytest.raises(ValidationError):
        backup_service.restore_backup(bad_file)
