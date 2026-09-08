from __future__ import annotations

from datetime import date, timedelta

import pandas as pd
import pytest

from app.database.session import session_scope
from app.imports import excel_importer
from app.services import auth_service, medicine_service, party_service, user_service
from app.utils.exceptions import ConflictError, ValidationError

from tests.conftest import ADMIN_USERNAME, ADMIN_PASSWORD


@pytest.fixture(autouse=True)
def _admin_session(admin_logged_in):
    """Every test in this module runs as the shared admin. Function-scoped
    (not module-scoped) so it stays compatible with conftest's per-test
    session reset."""
    yield


def test_add_medicine_and_search():
    med_id = medicine_service.add_medicine(name="Brufen 400mg", generic_formula="Ibuprofen", barcode="BR400X")
    results = medicine_service.search_medicines("Brufen")
    assert any(m.id == med_id for m in results)


def test_duplicate_barcode_rejected():
    medicine_service.add_medicine(name="Flagyl", generic_formula="Metronidazole", barcode="FLG001")
    with pytest.raises(ConflictError):
        medicine_service.add_medicine(name="Flagyl Duplicate", barcode="FLG001")


def test_manual_batch_creates_stock_transaction():
    med_id = medicine_service.add_medicine(name="Augmentin", generic_formula="Amoxicillin+Clavulanate")
    batch_id = medicine_service.add_manual_batch(
        medicine_id=med_id,
        batch_number="AUG-001",
        purchase_price=50,
        selling_price=70,
        quantity=100,
        expiry_date=date.today() + timedelta(days=400),
        wardrobe_code="W-01",
        rack_code="R-01",
        shelf_code="S-01",
    )
    with session_scope() as session:
        from app.models import MedicineBatch, StockTransaction

        batch = session.get(MedicineBatch, batch_id)
        assert batch.quantity == 100
        txns = session.query(StockTransaction).filter_by(batch_id=batch_id).all()
        assert len(txns) == 1
        assert txns[0].new_quantity == 100


def test_cannot_add_already_expired_batch():
    med_id = medicine_service.add_medicine(name="Expired Test Med")
    with pytest.raises(ValidationError):
        medicine_service.add_manual_batch(
            medicine_id=med_id,
            batch_number="EXP-001",
            purchase_price=10,
            selling_price=15,
            quantity=10,
            expiry_date=date.today() - timedelta(days=1),
        )


def test_fefo_orders_by_earliest_expiry_first():
    med_id = medicine_service.add_medicine(name="FEFO Test Med")
    medicine_service.add_manual_batch(
        medicine_id=med_id, batch_number="LATE", purchase_price=1, selling_price=2,
        quantity=10, expiry_date=date.today() + timedelta(days=500),
    )
    medicine_service.add_manual_batch(
        medicine_id=med_id, batch_number="EARLY", purchase_price=1, selling_price=2,
        quantity=10, expiry_date=date.today() + timedelta(days=30),
    )
    from app.repositories.inventory_repository import MedicineBatchRepository

    with session_scope() as session:
        candidates = MedicineBatchRepository(session).fefo_candidates(med_id)
        assert [b.batch_number for b in candidates] == ["EARLY", "LATE"]


def test_low_stock_report_flags_below_minimum():
    med_id = medicine_service.add_medicine(name="LowStock Med", min_stock_level=50)
    medicine_service.add_manual_batch(
        medicine_id=med_id, batch_number="LS-1", purchase_price=1, selling_price=2,
        quantity=10, expiry_date=date.today() + timedelta(days=200),
    )
    report = medicine_service.low_stock_report()
    assert any(r["medicine_id"] == med_id and r["current_quantity"] == 10 for r in report)


def test_expiry_report_buckets_correctly():
    med_id = medicine_service.add_medicine(name="Expiry Bucket Med")
    medicine_service.add_manual_batch(
        medicine_id=med_id, batch_number="SOON", purchase_price=1, selling_price=2,
        quantity=5, expiry_date=date.today() + timedelta(days=10),
    )
    report = medicine_service.expiry_report(warning_days=30)
    assert any(row["batch_number"] == "SOON" for row in report["expiring_soon"])
    assert not any(row["batch_number"] == "SOON" for row in report["expired"])


def test_supplier_and_customer_management():
    supplier_id = party_service.add_supplier("Demo Distributors", phone="0300-1112222")
    suppliers = party_service.list_suppliers()
    assert any(s.id == supplier_id for s in suppliers)

    customer_id = party_service.add_customer("Ali Khan", phone="0333-4445555")
    customers = party_service.list_customers()
    assert any(c.id == customer_id for c in customers)
    assert party_service.customer_purchase_history(customer_id) == []


def test_non_permitted_user_cannot_add_medicine():
    user_service.create_user(username="viewer_only", password="ViewerPass123!", permission_keys=["medicine.view"])
    auth_service.logout()
    auth_service.login("viewer_only", "ViewerPass123!")
    from app.utils.exceptions import AuthorizationError

    with pytest.raises(AuthorizationError):
        medicine_service.add_medicine(name="Should Not Be Added")
    auth_service.logout()


def test_excel_import_end_to_end(tmp_path):
    file_path = tmp_path / "stock_import.xlsx"
    future_date = (date.today() + timedelta(days=365)).strftime("%Y-%m-%d")
    df = pd.DataFrame(
        [
            {"Drug Name": "Disprin", "Generic": "Aspirin", "Batch": "DIS-1", "Qty": 100,
             "Buy Price": 5, "Sale Price": 8, "Expiry": future_date, "Rack No": "R1",
             "Wardrobe No": "W1", "Shelf No": "S1"},
            {"Drug Name": "", "Generic": "Bad Row", "Batch": "BAD-1", "Qty": -5,
             "Buy Price": 5, "Sale Price": 8, "Expiry": "not-a-date", "Rack No": "R1",
             "Wardrobe No": "W1", "Shelf No": "S1"},
            {"Drug Name": "Disprin", "Generic": "Aspirin", "Batch": "DIS-1", "Qty": 100,
             "Buy Price": 5, "Sale Price": 8, "Expiry": future_date, "Rack No": "R1",
             "Wardrobe No": "W1", "Shelf No": "S1"},  # duplicate of row 1
        ]
    )
    df.to_excel(file_path, index=False)

    mapping = {
        "Drug Name": "medicine_name",
        "Generic": "formula",
        "Batch": "batch_number",
        "Qty": "quantity",
        "Buy Price": "purchase_price",
        "Sale Price": "selling_price",
        "Expiry": "expiry_date",
        "Rack No": "rack",
        "Wardrobe No": "wardrobe",
        "Shelf No": "shelf",
    }

    preview = excel_importer.preview_import(str(file_path), mapping)
    assert preview.total_rows == 3
    assert len(preview.valid_rows) == 1
    assert len(preview.invalid_rows) == 1
    assert len(preview.duplicate_rows) == 1

    result = excel_importer.commit_import(preview)
    assert result.imported_rows == 1
    assert result.created_medicines == 1
    assert result.created_batches == 1

    found = medicine_service.search_medicines("Disprin")
    assert len(found) == 1
    with session_scope() as session:
        from app.models import Medicine

        medicine = session.query(Medicine).filter_by(name="Disprin").one()
        assert medicine.batches[0].quantity == 100
