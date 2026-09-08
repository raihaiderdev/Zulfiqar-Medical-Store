from __future__ import annotations

from datetime import date, timedelta

import pytest

from app.database.session import session_scope
from app.services import medicine_service, party_service, purchase_service
from app.utils.exceptions import ValidationError


@pytest.fixture(autouse=True)
def _admin_session(admin_logged_in):
    yield


def test_purchase_creates_new_batch_and_stock():
    med_id = medicine_service.add_medicine(name="Purchase Test Med")
    supplier_id = party_service.add_supplier("Purchase Test Supplier")

    purchase_id = purchase_service.record_purchase(
        supplier_id=supplier_id,
        supplier_invoice_number="SUP-INV-001",
        lines=[
            {
                "medicine_id": med_id,
                "batch_number": "PT-001",
                "quantity": 150,
                "purchase_price": 20,
                "selling_price": 30,
                "expiry_date": date.today() + timedelta(days=300),
            }
        ],
    )
    assert isinstance(purchase_id, int)

    from app.models import MedicineBatch, StockTransaction

    with session_scope() as session:
        batch = session.query(MedicineBatch).filter_by(medicine_id=med_id, batch_number="PT-001").one()
        assert batch.quantity == 150
        txns = session.query(StockTransaction).filter_by(batch_id=batch.id).all()
        assert len(txns) == 1
        assert txns[0].txn_type.value == "PURCHASE"


def test_purchase_tops_up_existing_batch():
    med_id = medicine_service.add_medicine(name="TopUp Test Med")
    supplier_id = party_service.add_supplier("TopUp Test Supplier")

    purchase_service.record_purchase(
        supplier_id=supplier_id,
        lines=[{
            "medicine_id": med_id, "batch_number": "TU-1", "quantity": 50,
            "purchase_price": 10, "selling_price": 15, "expiry_date": date.today() + timedelta(days=300),
        }],
    )
    purchase_service.record_purchase(
        supplier_id=supplier_id,
        lines=[{
            "medicine_id": med_id, "batch_number": "TU-1", "quantity": 25,
            "purchase_price": 11, "selling_price": 16, "expiry_date": date.today() + timedelta(days=300),
        }],
    )

    from app.models import MedicineBatch

    with session_scope() as session:
        batch = session.query(MedicineBatch).filter_by(medicine_id=med_id, batch_number="TU-1").one()
        assert batch.quantity == 75
        assert float(batch.purchase_price) == 11  # refreshed to latest purchase terms


def test_purchase_rejects_negative_quantity():
    med_id = medicine_service.add_medicine(name="BadQty Med")
    supplier_id = party_service.add_supplier("BadQty Supplier")
    with pytest.raises(ValidationError):
        purchase_service.record_purchase(
            supplier_id=supplier_id,
            lines=[{
                "medicine_id": med_id, "batch_number": "BQ-1", "quantity": -5,
                "purchase_price": 10, "selling_price": 15, "expiry_date": date.today() + timedelta(days=100),
            }],
        )


def test_failed_purchase_line_rolls_back_entire_transaction():
    """A multi-line purchase where line 2 is invalid must not leave line 1's
    stock change committed — the whole thing rolls back (Phase 1 §28)."""
    med_id = medicine_service.add_medicine(name="Rollback Med")
    supplier_id = party_service.add_supplier("Rollback Supplier")

    with pytest.raises(ValidationError):
        purchase_service.record_purchase(
            supplier_id=supplier_id,
            lines=[
                {
                    "medicine_id": med_id, "batch_number": "RB-GOOD", "quantity": 40,
                    "purchase_price": 5, "selling_price": 8, "expiry_date": date.today() + timedelta(days=200),
                },
                {
                    "medicine_id": med_id, "batch_number": "RB-BAD", "quantity": -10,  # invalid
                    "purchase_price": 5, "selling_price": 8, "expiry_date": date.today() + timedelta(days=200),
                },
            ],
        )

    from app.models import MedicineBatch

    with session_scope() as session:
        good_batch = (
            session.query(MedicineBatch).filter_by(medicine_id=med_id, batch_number="RB-GOOD").one_or_none()
        )
        assert good_batch is None  # rolled back along with the bad line


def test_supplier_purchase_history():
    med_id = medicine_service.add_medicine(name="History Med")
    supplier_id = party_service.add_supplier("History Supplier")
    purchase_service.record_purchase(
        supplier_id=supplier_id,
        supplier_invoice_number="HIST-1",
        lines=[{
            "medicine_id": med_id, "batch_number": "H-1", "quantity": 10,
            "purchase_price": 5, "selling_price": 8, "expiry_date": date.today() + timedelta(days=100),
        }],
    )
    history = purchase_service.supplier_purchase_history(supplier_id)
    assert len(history) == 1
    assert history[0]["invoice_number"] == "HIST-1"
    assert history[0]["total_cost"] == 50
