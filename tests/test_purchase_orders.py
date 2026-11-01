"""
Regression tests for purchase_order_service — TASK-04.

Covers:
  - create DRAFT PO → returns po_id
  - approve DRAFT → APPROVED status
  - cancel DRAFT / APPROVED → CANCELLED
  - cannot cancel COMPLETED
  - list_purchase_orders returns correct data without DetachedInstanceError
  - get_purchase_order_detail loads fully (no DetachedInstanceError)
  - permission checks
"""
from __future__ import annotations

from datetime import date, timedelta

import pytest

from app.database.session import session_scope
from app.models.purchase_order import POStatus, PurchaseOrder
from app.services import auth_service, medicine_service, party_service, purchase_order_service, user_service
from app.utils.exceptions import AuthorizationError, ValidationError


@pytest.fixture(autouse=True)
def _admin_session(admin_logged_in):
    yield


import itertools
_counter = itertools.count(1)


def _make_supplier():
    return party_service.add_supplier(f"PO Supplier {next(_counter)}")


def _make_medicine():
    return medicine_service.add_medicine(name=f"PO Med {next(_counter)}")


def test_create_draft_po_returns_id():
    supplier_id = _make_supplier()
    med_id = _make_medicine()
    po_id = purchase_order_service.create_purchase_order(
        supplier_id=supplier_id,
        lines=[{"medicine_id": med_id, "ordered_quantity": 50, "unit_price": 10.0}],
        expected_delivery_date=date.today() + timedelta(days=7),
    )
    assert isinstance(po_id, int)
    with session_scope() as session:
        po = session.get(PurchaseOrder, po_id)
        assert po.status == POStatus.DRAFT


def test_approve_draft_po():
    supplier_id = _make_supplier()
    med_id = _make_medicine()
    po_id = purchase_order_service.create_purchase_order(
        supplier_id=supplier_id,
        lines=[{"medicine_id": med_id, "ordered_quantity": 10, "unit_price": 5.0}],
    )
    purchase_order_service.approve_purchase_order(po_id)
    with session_scope() as session:
        po = session.get(PurchaseOrder, po_id)
        assert po.status == POStatus.APPROVED


def test_cannot_approve_already_approved_po():
    supplier_id = _make_supplier()
    med_id = _make_medicine()
    po_id = purchase_order_service.create_purchase_order(
        supplier_id=supplier_id,
        lines=[{"medicine_id": med_id, "ordered_quantity": 10, "unit_price": 5.0}],
    )
    purchase_order_service.approve_purchase_order(po_id)
    with pytest.raises(ValidationError, match="DRAFT"):
        purchase_order_service.approve_purchase_order(po_id)


def test_cancel_draft_po():
    supplier_id = _make_supplier()
    med_id = _make_medicine()
    po_id = purchase_order_service.create_purchase_order(
        supplier_id=supplier_id,
        lines=[{"medicine_id": med_id, "ordered_quantity": 5, "unit_price": 8.0}],
    )
    purchase_order_service.cancel_purchase_order(po_id, reason="Changed plan")
    with session_scope() as session:
        po = session.get(PurchaseOrder, po_id)
        assert po.status == POStatus.CANCELLED


def test_cannot_cancel_cancelled_po():
    supplier_id = _make_supplier()
    med_id = _make_medicine()
    po_id = purchase_order_service.create_purchase_order(
        supplier_id=supplier_id,
        lines=[{"medicine_id": med_id, "ordered_quantity": 5, "unit_price": 8.0}],
    )
    purchase_order_service.cancel_purchase_order(po_id, reason="First cancel")
    with pytest.raises(ValidationError):
        purchase_order_service.cancel_purchase_order(po_id, reason="Double cancel")


def test_list_purchase_orders_no_detached_error():
    """
    Regression: list_purchase_orders() accesses supplier.name and len(items)
    after session closes. Must use selectinload to avoid DetachedInstanceError.
    """
    supplier_id = _make_supplier()
    med_id = _make_medicine()
    purchase_order_service.create_purchase_order(
        supplier_id=supplier_id,
        lines=[{"medicine_id": med_id, "ordered_quantity": 10, "unit_price": 12.0}],
    )
    # Should not raise DetachedInstanceError
    orders = purchase_order_service.list_purchase_orders()
    assert len(orders) > 0
    first = orders[0]
    assert "supplier_name" in first
    assert "line_count" in first
    assert isinstance(first["line_count"], int)


def test_get_purchase_order_detail_no_detached_error():
    supplier_id = _make_supplier()
    med_id = _make_medicine()
    po_id = purchase_order_service.create_purchase_order(
        supplier_id=supplier_id,
        lines=[{"medicine_id": med_id, "ordered_quantity": 15, "unit_price": 7.0}],
    )
    detail = purchase_order_service.get_purchase_order_detail(po_id)
    assert detail["po_id"] == po_id
    assert len(detail["items"]) == 1
    assert detail["items"][0]["medicine_name"] != ""


def test_create_po_requires_permission():
    # Create supplier and medicine while still admin
    supplier_id = _make_supplier()
    med_id = _make_medicine()

    user_service.create_user(
        username="no_po_user",
        password="NoPOPass123!",
        permission_keys=["purchases.manage"],
    )
    auth_service.logout()
    auth_service.login("no_po_user", "NoPOPass123!")
    with pytest.raises(AuthorizationError):
        purchase_order_service.create_purchase_order(
            supplier_id=supplier_id,
            lines=[{"medicine_id": med_id, "ordered_quantity": 5, "unit_price": 5.0}],
        )
    auth_service.logout()


def test_create_po_with_empty_lines_rejected():
    supplier_id = _make_supplier()
    with pytest.raises(ValidationError, match="at least one line"):
        purchase_order_service.create_purchase_order(
            supplier_id=supplier_id,
            lines=[],
        )


def test_receive_goods_increases_stock_and_completes_po():
    """Full lifecycle: create → approve → receive → COMPLETED. Stock increases on receive."""
    supplier_id = _make_supplier()
    med_id = _make_medicine()

    # Create and approve PO
    po_id = purchase_order_service.create_purchase_order(
        supplier_id=supplier_id,
        lines=[{"medicine_id": med_id, "ordered_quantity": 20, "unit_price": 15.0}],
    )
    purchase_order_service.approve_purchase_order(po_id)

    # Get the PO item id
    detail_before = purchase_order_service.get_purchase_order_detail(po_id)
    po_item_id = detail_before["items"][0]["po_item_id"]

    # Stock before
    from app.models import MedicineBatch
    from app.database.session import session_scope as _ss
    with _ss() as session:
        batches_before = session.query(MedicineBatch).filter_by(medicine_id=med_id).count()

    # Receive all 20 units
    receipt_id = purchase_order_service.receive_goods(
        po_id=po_id,
        lines=[{
            "po_item_id":          po_item_id,
            "received_quantity":   20,
            "batch_number":        "RCV-001",
            "purchase_price":      15.0,
            "selling_price":       25.0,
            "expiry_date":         date.today() + timedelta(days=365),
        }],
    )
    assert isinstance(receipt_id, int)

    # PO should now be COMPLETED
    from app.models.purchase_order import POStatus
    with _ss() as session:
        from app.models.purchase_order import PurchaseOrder
        po = session.get(PurchaseOrder, po_id)
        assert po.status == POStatus.COMPLETED

    # Batch stock should have increased by 20
    with _ss() as session:
        batch = session.query(MedicineBatch).filter_by(
            medicine_id=med_id, batch_number="RCV-001"
        ).first()
        assert batch is not None
        assert batch.quantity == 20


def test_receive_goods_partially_updates_status():
    """Receiving fewer than ordered → PARTIALLY_RECEIVED."""
    supplier_id = _make_supplier()
    med_id = _make_medicine()

    po_id = purchase_order_service.create_purchase_order(
        supplier_id=supplier_id,
        lines=[{"medicine_id": med_id, "ordered_quantity": 30, "unit_price": 10.0}],
    )
    purchase_order_service.approve_purchase_order(po_id)

    detail = purchase_order_service.get_purchase_order_detail(po_id)
    po_item_id = detail["items"][0]["po_item_id"]

    purchase_order_service.receive_goods(
        po_id=po_id,
        lines=[{
            "po_item_id":        po_item_id,
            "received_quantity": 10,          # only 10 of 30
            "batch_number":      "PART-001",
            "purchase_price":    10.0,
            "selling_price":     18.0,
            "expiry_date":       date.today() + timedelta(days=365),
        }],
    )

    from app.models.purchase_order import POStatus, PurchaseOrder
    from app.database.session import session_scope as _ss
    with _ss() as session:
        po = session.get(PurchaseOrder, po_id)
        assert po.status == POStatus.PARTIALLY_RECEIVED
