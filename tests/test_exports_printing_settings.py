from __future__ import annotations

from datetime import date, timedelta

import pytest

from app.exports import data_exporter
from app.printing import pdf_documents
from app.services import medicine_service, sales_service, settings_service


@pytest.fixture(autouse=True)
def _admin_session(admin_logged_in):
    yield


def test_csv_export(tmp_path):
    rows = [{"name": "Panadol", "qty": 100}, {"name": "Brufen", "qty": 50}]
    path = data_exporter.export_to_csv(rows, tmp_path / "out.csv")
    assert path.exists()
    assert "Panadol" in path.read_text()


def test_excel_export(tmp_path):
    rows = [{"name": "Panadol", "qty": 100}]
    path = data_exporter.export_to_excel(rows, tmp_path / "out.xlsx")
    assert path.exists()


def test_invoice_pdf_generation(tmp_path):
    med_id = medicine_service.add_medicine(name="PDF Test Med")
    medicine_service.add_manual_batch(
        medicine_id=med_id, batch_number="PDF-1", purchase_price=10, selling_price=20,
        quantity=10, expiry_date=date.today() + timedelta(days=200),
    )
    result = sales_service.complete_sale(lines=[{"medicine_id": med_id, "quantity": 2}], amount_paid=40)
    detail = sales_service.get_sale_detail(result.sale_id)

    pdf_path = pdf_documents.render_invoice_pdf(detail, tmp_path / "invoice.pdf", pharmacy_name="Test Pharmacy")
    assert pdf_path.exists()
    assert pdf_path.stat().st_size > 0


def test_tabular_report_pdf_generation(tmp_path):
    pdf_path = pdf_documents.render_tabular_report_pdf(
        "Low Stock Report", ["Medicine", "Quantity"], [["Panadol", "5"], ["Brufen", "2"]], tmp_path / "report.pdf"
    )
    assert pdf_path.exists()


def test_settings_roundtrip():
    settings_service.set_setting("pharmacy.name", "Al-Shifa Pharmacy")
    assert settings_service.get_setting("pharmacy.name") == "Al-Shifa Pharmacy"
    all_settings = settings_service.get_all_settings()
    assert all_settings["pharmacy.name"] == "Al-Shifa Pharmacy"


def test_get_setting_default_when_missing():
    assert settings_service.get_setting("nonexistent.key", default="fallback") == "fallback"
