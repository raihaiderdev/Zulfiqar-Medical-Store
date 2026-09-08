from __future__ import annotations

from datetime import date, timedelta

import pytest

from app.database.session import session_scope
from app.services import auth_service, medicine_service, sales_service, user_service
from app.utils.exceptions import AuthorizationError, ValidationError


@pytest.fixture(autouse=True)
def _admin_session(admin_logged_in):
    yield


def _make_medicine_with_batch(batch_number="S-1", quantity=100, expiry_days=300, selling_price=50, purchase_price=30):
    med_id = medicine_service.add_medicine(name=f"Sale Test Med {batch_number}")
    medicine_service.add_manual_batch(
        medicine_id=med_id,
        batch_number=batch_number,
        purchase_price=purchase_price,
        selling_price=selling_price,
        quantity=quantity,
        expiry_date=date.today() + timedelta(days=expiry_days),
    )
    return med_id


def test_complete_sale_deducts_stock_and_records_profit():
    med_id = _make_medicine_with_batch(quantity=100, selling_price=50, purchase_price=30)
    result = sales_service.complete_sale(
        lines=[{"medicine_id": med_id, "quantity": 5}],
        amount_paid=250,
    )
    assert result.total == 250
    assert result.change_due == 0
    assert result.invoice_number.startswith("INV-")

    detail = sales_service.get_sale_detail(result.sale_id)
    assert detail["items"][0]["line_profit"] == (50 - 30) * 5

    from app.models import MedicineBatch

    with session_scope() as session:
        batch = session.query(MedicineBatch).filter_by(medicine_id=med_id).one()
        assert batch.quantity == 95


def test_sale_uses_fefo_across_two_batches():
    med_id = medicine_service.add_medicine(name="FEFO Sale Med")
    medicine_service.add_manual_batch(
        medicine_id=med_id, batch_number="FAR", purchase_price=10, selling_price=20,
        quantity=10, expiry_date=date.today() + timedelta(days=500),
    )
    medicine_service.add_manual_batch(
        medicine_id=med_id, batch_number="NEAR", purchase_price=10, selling_price=20,
        quantity=5, expiry_date=date.today() + timedelta(days=30),
    )
    # Requesting 8 units should consume all 5 from NEAR, then 3 from FAR.
    result = sales_service.complete_sale(lines=[{"medicine_id": med_id, "quantity": 8}], amount_paid=160)
    detail = sales_service.get_sale_detail(result.sale_id)
    batch_numbers = {item["batch_number"] for item in detail["items"]}
    assert batch_numbers == {"NEAR", "FAR"}

    from app.models import MedicineBatch

    with session_scope() as session:
        near = session.query(MedicineBatch).filter_by(batch_number="NEAR").one()
        far = session.query(MedicineBatch).filter_by(batch_number="FAR").one()
        assert near.quantity == 0
        assert far.quantity == 7


def test_sale_rejects_insufficient_stock():
    med_id = _make_medicine_with_batch(quantity=3)
    with pytest.raises(ValidationError):
        sales_service.complete_sale(lines=[{"medicine_id": med_id, "quantity": 10}], amount_paid=1000)


def test_sale_blocks_expired_batch_by_default():
    med_id = medicine_service.add_medicine(name="Expired Sale Med")
    # Can't use add_manual_batch (it rejects already-expired batches), so
    # insert directly to simulate a batch that expired after being added.
    from app.models import MedicineBatch

    with session_scope() as session:
        batch = MedicineBatch(
            medicine_id=med_id, batch_number="EXP-SELL", purchase_price=5, selling_price=10,
            quantity=20, expiry_date=date.today() - timedelta(days=5),
        )
        session.add(batch)
        session.flush()
        batch_id = batch.id

    with pytest.raises(ValidationError):
        sales_service.complete_sale(
            lines=[{"medicine_id": med_id, "quantity": 1, "batch_id": batch_id}], amount_paid=10
        )


def test_discount_requires_permission():
    user_service.create_user(
        username="no_discount_cashier", password="CashierPass123!",
        permission_keys=["sales.create", "medicine.view"],
    )
    med_id = _make_medicine_with_batch(quantity=50, selling_price=100)
    auth_service.logout()
    auth_service.login("no_discount_cashier", "CashierPass123!")
    with pytest.raises(AuthorizationError):
        sales_service.complete_sale(
            lines=[{"medicine_id": med_id, "quantity": 1}], amount_paid=90, discount_total=10
        )
    auth_service.logout()


def test_discount_exceeding_cap_rejected():
    med_id = _make_medicine_with_batch(quantity=50, selling_price=100)
    with pytest.raises(ValidationError):
        # settings.max_discount_percent default is 20% -> max 20 on a 100 subtotal
        sales_service.complete_sale(
            lines=[{"medicine_id": med_id, "quantity": 1}], amount_paid=50, discount_total=50
        )


def test_change_due_calculated_correctly():
    med_id = _make_medicine_with_batch(quantity=50, selling_price=100)
    result = sales_service.complete_sale(lines=[{"medicine_id": med_id, "quantity": 1}], amount_paid=150)
    assert result.total == 100
    assert result.change_due == 50


def test_invoice_numbers_are_sequential_and_unique():
    med_id = _make_medicine_with_batch(quantity=50, selling_price=10)
    r1 = sales_service.complete_sale(lines=[{"medicine_id": med_id, "quantity": 1}], amount_paid=10)
    r2 = sales_service.complete_sale(lines=[{"medicine_id": med_id, "quantity": 1}], amount_paid=10)
    assert r1.invoice_number != r2.invoice_number
