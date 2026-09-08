from __future__ import annotations

from datetime import date, timedelta

import pytest

from app.database.session import session_scope
from app.services import medicine_service, party_service, purchase_service, returns_service, sales_service
from app.utils.exceptions import ValidationError


@pytest.fixture(autouse=True)
def _admin_session(admin_logged_in):
    yield


def test_sale_return_restocks_batch():
    med_id = medicine_service.add_medicine(name="Return Test Med")
    medicine_service.add_manual_batch(
        medicine_id=med_id, batch_number="RT-1", purchase_price=10, selling_price=20,
        quantity=50, expiry_date=date.today() + timedelta(days=200),
    )
    sale_result = sales_service.complete_sale(lines=[{"medicine_id": med_id, "quantity": 10}], amount_paid=200)
    detail = sales_service.get_sale_detail(sale_result.sale_id)

    from app.models import Sale, SaleItem

    with session_scope() as session:
        sale_item_id = session.query(SaleItem).join(Sale).filter(Sale.id == sale_result.sale_id).first().id

    returns_service.process_sale_return(
        sale_id=sale_result.sale_id, lines=[{"sale_item_id": sale_item_id, "quantity": 4}], reason="Customer changed mind"
    )

    from app.models import MedicineBatch

    with session_scope() as session:
        batch = session.query(MedicineBatch).filter_by(batch_number="RT-1").one()
        assert batch.quantity == 44  # 50 - 10 sold + 4 returned


def test_sale_return_cannot_exceed_sold_quantity():
    med_id = medicine_service.add_medicine(name="OverReturn Med")
    medicine_service.add_manual_batch(
        medicine_id=med_id, batch_number="OR-1", purchase_price=10, selling_price=20,
        quantity=50, expiry_date=date.today() + timedelta(days=200),
    )
    sale_result = sales_service.complete_sale(lines=[{"medicine_id": med_id, "quantity": 5}], amount_paid=100)

    from app.models import Sale, SaleItem

    with session_scope() as session:
        sale_item_id = session.query(SaleItem).join(Sale).filter(Sale.id == sale_result.sale_id).first().id

    with pytest.raises(ValidationError):
        returns_service.process_sale_return(
            sale_id=sale_result.sale_id, lines=[{"sale_item_id": sale_item_id, "quantity": 999}]
        )


def test_sale_return_without_restock_does_not_increase_quantity():
    med_id = medicine_service.add_medicine(name="DamagedReturn Med")
    medicine_service.add_manual_batch(
        medicine_id=med_id, batch_number="DR-1", purchase_price=10, selling_price=20,
        quantity=50, expiry_date=date.today() + timedelta(days=200),
    )
    sale_result = sales_service.complete_sale(lines=[{"medicine_id": med_id, "quantity": 5}], amount_paid=100)

    from app.models import Sale, SaleItem, MedicineBatch

    with session_scope() as session:
        sale_item_id = session.query(SaleItem).join(Sale).filter(Sale.id == sale_result.sale_id).first().id

    returns_service.process_sale_return(
        sale_id=sale_result.sale_id, lines=[{"sale_item_id": sale_item_id, "quantity": 2}],
        reason="Damaged", restock=False,
    )

    with session_scope() as session:
        batch = session.query(MedicineBatch).filter_by(batch_number="DR-1").one()
        assert batch.quantity == 45  # 50 - 5 sold, return not restocked


def test_purchase_return_decreases_stock():
    med_id = medicine_service.add_medicine(name="PurchReturn Med")
    supplier_id = party_service.add_supplier("PurchReturn Supplier")
    purchase_id = purchase_service.record_purchase(
        supplier_id=supplier_id,
        lines=[{
            "medicine_id": med_id, "batch_number": "PR-1", "quantity": 100,
            "purchase_price": 10, "selling_price": 15, "expiry_date": date.today() + timedelta(days=200),
        }],
    )
    from app.models import Purchase, PurchaseItem

    with session_scope() as session:
        purchase_item_id = (
            session.query(PurchaseItem).filter_by(purchase_id=purchase_id).first().id
        )

    returns_service.process_purchase_return(
        purchase_id=purchase_id, lines=[{"purchase_item_id": purchase_item_id, "quantity": 20}], reason="Wrong item"
    )

    from app.models import MedicineBatch

    with session_scope() as session:
        batch = session.query(MedicineBatch).filter_by(batch_number="PR-1").one()
        assert batch.quantity == 80


def test_manual_stock_adjustment_requires_reason():
    med_id = medicine_service.add_medicine(name="Adjust Med")
    medicine_service.add_manual_batch(
        medicine_id=med_id, batch_number="ADJ-1", purchase_price=5, selling_price=8,
        quantity=30, expiry_date=date.today() + timedelta(days=200),
    )
    from app.models import MedicineBatch

    with session_scope() as session:
        batch_id = session.query(MedicineBatch).filter_by(batch_number="ADJ-1").one().id

    with pytest.raises(ValidationError):
        returns_service.adjust_stock(batch_id=batch_id, delta=-5, reason="")

    returns_service.adjust_stock(batch_id=batch_id, delta=-5, reason="Damaged in storage")
    with session_scope() as session:
        batch = session.get(MedicineBatch, batch_id)
        assert batch.quantity == 25


def test_write_off_expired_batch():
    med_id = medicine_service.add_medicine(name="WriteOff Med")
    from app.models import MedicineBatch

    with session_scope() as session:
        batch = MedicineBatch(
            medicine_id=med_id, batch_number="WO-1", purchase_price=5, selling_price=8,
            quantity=15, expiry_date=date.today() - timedelta(days=10),
        )
        session.add(batch)
        session.flush()
        batch_id = batch.id

    returns_service.write_off_expired_batch(batch_id, reason="Routine expiry sweep")

    with session_scope() as session:
        batch = session.get(MedicineBatch, batch_id)
        assert batch.quantity == 0


def test_cannot_write_off_non_expired_batch():
    med_id = medicine_service.add_medicine(name="NotExpired Med")
    medicine_service.add_manual_batch(
        medicine_id=med_id, batch_number="NE-1", purchase_price=5, selling_price=8,
        quantity=10, expiry_date=date.today() + timedelta(days=100),
    )
    from app.models import MedicineBatch

    with session_scope() as session:
        batch_id = session.query(MedicineBatch).filter_by(batch_number="NE-1").one().id

    with pytest.raises(ValidationError):
        returns_service.write_off_expired_batch(batch_id)
