"""
Purchase Order service — Phase 2.

Lifecycle rules:
  DRAFT      → can be edited, cancelled.
  APPROVED   → cannot be edited; can be received (partially or fully).
  PARTIALLY_RECEIVED → more receipts possible.
  COMPLETED  → all ordered quantity received; no more receipts allowed.
  CANCELLED  → terminal state.

Stock ONLY increases when `receive_goods()` is called, which delegates
to the existing `purchase_service.record_purchase()` so the stock ledger
invariant is preserved.

PO numbers are auto-generated: PO-{YEAR}-{SEQ:06d}
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Optional, TypedDict

from sqlalchemy import func

from app.database.session import session_scope
from app.models import Supplier
from app.models.purchase_order import (
    POStatus,
    PurchaseOrder,
    PurchaseOrderItem,
    PurchaseOrderReceipt,
    PurchaseOrderReceiptItem,
)
from app.security.decorators import require_permission
from app.security.session_context import current_session
from app.services import audit_service, purchase_service
from app.utils.exceptions import NotFoundError, ValidationError


# ── Helpers ───────────────────────────────────────────────────────────────

def _next_po_number(session, year: int) -> str:
    prefix = f"PO-{year}-"
    max_val = (
        session.query(func.max(PurchaseOrder.po_number))
        .filter(PurchaseOrder.po_number.like(f"{prefix}%"))
        .scalar()
    )
    if max_val:
        try:
            last_seq = int(max_val[len(prefix):])
        except (ValueError, IndexError):
            last_seq = 0
    else:
        last_seq = 0
    return f"{prefix}{last_seq + 1:06d}"


# ── Input types ───────────────────────────────────────────────────────────

class POLineInput(TypedDict, total=False):
    medicine_id:      int
    ordered_quantity: int
    unit_price:       float
    notes:            Optional[str]


class ReceiptLineInput(TypedDict):
    po_item_id:        int
    received_quantity: int
    batch_number:      str
    purchase_price:    float
    selling_price:     float
    expiry_date:       date


# ── Service functions ─────────────────────────────────────────────────────

@require_permission("purchase_orders.create")
def create_purchase_order(
    *,
    supplier_id: int,
    lines: list[POLineInput],
    expected_delivery_date: Optional[date] = None,
    notes: Optional[str] = None,
) -> int:
    """
    Create a DRAFT purchase order.
    Returns the new PO's id.
    Stock is NOT affected at this stage.
    """
    if not lines:
        raise ValidationError("A purchase order must have at least one line.")

    with session_scope() as session:
        supplier = session.get(Supplier, supplier_id)
        if supplier is None:
            raise NotFoundError(f"Supplier {supplier_id} not found.")

        po = PurchaseOrder(
            supplier_id=supplier_id,
            po_number=_next_po_number(session, date.today().year),
            order_date=date.today(),
            expected_delivery_date=expected_delivery_date,
            status=POStatus.DRAFT,
            notes=notes,
            created_by_user_id=current_session.user_id,
        )
        session.add(po)
        session.flush()

        for line in lines:
            qty = line.get("ordered_quantity", 0)
            price = line.get("unit_price", 0.0)
            if qty <= 0:
                raise ValidationError("Ordered quantity must be positive.")
            if price < 0:
                raise ValidationError("Unit price cannot be negative.")
            session.add(PurchaseOrderItem(
                purchase_order_id=po.id,
                medicine_id=line["medicine_id"],
                ordered_quantity=qty,
                unit_price=price,
                notes=line.get("notes"),
            ))

        audit_service.record(
            session,
            user_id=current_session.user_id,
            action="PO_CREATED",
            entity="purchase_orders",
            entity_id=po.id,
            new_value={"po_number": po.po_number, "supplier_id": supplier_id,
                       "lines": len(lines)},
        )
        return po.id


@require_permission("purchase_orders.approve")
def approve_purchase_order(po_id: int) -> None:
    """Approve a DRAFT PO. Only DRAFT → APPROVED is valid."""
    with session_scope() as session:
        po = session.get(PurchaseOrder, po_id)
        if po is None:
            raise NotFoundError(f"Purchase order {po_id} not found.")
        if po.status != POStatus.DRAFT:
            raise ValidationError(
                f"Only DRAFT orders can be approved. Current status: {po.status.value}"
            )
        po.status = POStatus.APPROVED
        po.approved_by_user_id = current_session.user_id
        session.add(po)
        audit_service.record(
            session, user_id=current_session.user_id,
            action="PO_APPROVED", entity="purchase_orders", entity_id=po_id,
        )


@require_permission("purchase_orders.approve")
def cancel_purchase_order(po_id: int, reason: Optional[str] = None) -> None:
    """Cancel a DRAFT or APPROVED PO. PARTIALLY_RECEIVED cannot be cancelled."""
    with session_scope() as session:
        po = session.get(PurchaseOrder, po_id)
        if po is None:
            raise NotFoundError(f"Purchase order {po_id} not found.")
        if po.status in (POStatus.COMPLETED, POStatus.CANCELLED):
            raise ValidationError(
                f"Cannot cancel a {po.status.value} purchase order."
            )
        if po.status == POStatus.PARTIALLY_RECEIVED:
            raise ValidationError(
                "Cannot cancel a partially-received order. "
                "Contact supplier and process a purchase return instead."
            )
        po.status = POStatus.CANCELLED
        session.add(po)
        audit_service.record(
            session, user_id=current_session.user_id,
            action="PO_CANCELLED", entity="purchase_orders", entity_id=po_id,
            new_value={"reason": reason},
        )


@require_permission("purchase_orders.receive")
def receive_goods(
    *,
    po_id: int,
    lines: list[ReceiptLineInput],
    notes: Optional[str] = None,
) -> int:
    """
    Record receipt of goods against a purchase order.

    For each line:
      - Validates received_quantity <= remaining (ordered - already received).
      - Delegates to `purchase_service.record_purchase()` for stock ledger entry.
      - Updates PO status to PARTIALLY_RECEIVED or COMPLETED.

    Returns the PurchaseOrderReceipt id.
    Stock is only updated inside this call via the existing purchase service.
    """
    if not lines:
        raise ValidationError("At least one receipt line is required.")

    with session_scope() as session:
        po = session.get(PurchaseOrder, po_id)
        if po is None:
            raise NotFoundError(f"Purchase order {po_id} not found.")
        if po.status not in (POStatus.APPROVED, POStatus.PARTIALLY_RECEIVED):
            raise ValidationError(
                f"Cannot receive goods against a {po.status.value} order. "
                "Order must be APPROVED or PARTIALLY_RECEIVED."
            )

        # Validate quantities
        for line in lines:
            po_item = session.get(PurchaseOrderItem, line["po_item_id"])
            if po_item is None or po_item.purchase_order_id != po_id:
                raise NotFoundError(
                    f"PO item {line['po_item_id']} not found on PO {po_id}."
                )
            already_received = _already_received(session, line["po_item_id"])
            remaining = po_item.ordered_quantity - already_received
            if line["received_quantity"] > remaining:
                raise ValidationError(
                    f"Cannot receive {line['received_quantity']} units for item "
                    f"{line['po_item_id']} — only {remaining} remaining to receive."
                )

        # Create the receipt header (flush to get id before delegating)
        receipt = PurchaseOrderReceipt(
            purchase_order_id=po_id,
            received_date=date.today(),
            received_by_user_id=current_session.user_id,
            notes=notes,
        )
        session.add(receipt)
        session.flush()

        # Add receipt line items
        for line in lines:
            session.add(PurchaseOrderReceiptItem(
                receipt_id=receipt.id,
                po_item_id=line["po_item_id"],
                received_quantity=line["received_quantity"],
                batch_number=line["batch_number"],
                purchase_price=line["purchase_price"],
                selling_price=line["selling_price"],
                expiry_date=line["expiry_date"],
            ))

        # Update PO status
        all_received = _check_all_received(session, po)
        po.status = POStatus.COMPLETED if all_received else POStatus.PARTIALLY_RECEIVED
        session.add(po)

        audit_service.record(
            session, user_id=current_session.user_id,
            action="PO_GOODS_RECEIVED", entity="purchase_orders", entity_id=po_id,
            new_value={
                "receipt_id": receipt.id,
                "lines": len(lines),
                "new_status": po.status.value,
            },
        )

    # Delegate stock creation to existing purchase_service (outside the session above
    # so purchase_service opens its own session_scope — same pattern used elsewhere).
    purchase_lines = [
        {
            "medicine_id":   _get_medicine_id_for_po_item(line["po_item_id"]),
            "batch_number":  line["batch_number"],
            "quantity":      line["received_quantity"],
            "purchase_price": line["purchase_price"],
            "selling_price": line["selling_price"],
            "expiry_date":   line["expiry_date"],
        }
        for line in lines
    ]
    purchase_id = purchase_service.record_purchase(
        supplier_id=_get_supplier_id(po_id),
        lines=purchase_lines,
        notes=f"Received against PO {_get_po_number(po_id)}",
    )

    # Link the purchase record to the receipt
    with session_scope() as session:
        r = session.get(PurchaseOrderReceipt, receipt.id)
        if r:
            r.purchase_id = purchase_id
            session.add(r)

    return receipt.id


def _already_received(session, po_item_id: int) -> int:
    result = (
        session.query(func.coalesce(func.sum(PurchaseOrderReceiptItem.received_quantity), 0))
        .join(PurchaseOrderReceipt,
              PurchaseOrderReceipt.id == PurchaseOrderReceiptItem.receipt_id)
        .filter(PurchaseOrderReceiptItem.po_item_id == po_item_id)
        .scalar()
    )
    return int(result or 0)


def _check_all_received(session, po: PurchaseOrder) -> bool:
    for item in po.items:
        if _already_received(session, item.id) < item.ordered_quantity:
            return False
    return True


def _get_supplier_id(po_id: int) -> int:
    with session_scope() as session:
        po = session.get(PurchaseOrder, po_id)
        return po.supplier_id if po else 0


def _get_po_number(po_id: int) -> str:
    with session_scope() as session:
        po = session.get(PurchaseOrder, po_id)
        return po.po_number if po else str(po_id)


def _get_medicine_id_for_po_item(po_item_id: int) -> int:
    with session_scope() as session:
        item = session.get(PurchaseOrderItem, po_item_id)
        return item.medicine_id if item else 0


# ── Read functions ────────────────────────────────────────────────────────

@require_permission("purchase_orders.create")
def list_purchase_orders(
    *,
    status: Optional[POStatus] = None,
    supplier_id: Optional[int] = None,
    limit: int = 200,
) -> list[dict]:
    with session_scope() as session:
        q = session.query(PurchaseOrder)
        if status:
            q = q.filter(PurchaseOrder.status == status)
        if supplier_id:
            q = q.filter(PurchaseOrder.supplier_id == supplier_id)
        orders = q.order_by(PurchaseOrder.order_date.desc()).limit(limit).all()
        return [
            {
                "po_id":                    o.id,
                "po_number":                o.po_number,
                "supplier_name":            o.supplier.name if o.supplier else "",
                "order_date":               o.order_date.isoformat(),
                "expected_delivery_date":   (
                    o.expected_delivery_date.isoformat()
                    if o.expected_delivery_date else None
                ),
                "status":                   o.status.value,
                "line_count":               len(o.items),
                "notes":                    o.notes or "",
            }
            for o in orders
        ]


@require_permission("purchase_orders.create")
def get_purchase_order_detail(po_id: int) -> dict:
    with session_scope() as session:
        from sqlalchemy.orm import selectinload
        po = (
            session.query(PurchaseOrder)
            .options(
                selectinload(PurchaseOrder.items)
                    .selectinload(PurchaseOrderItem.medicine),
                selectinload(PurchaseOrder.supplier),
                selectinload(PurchaseOrder.receipts)
                    .selectinload(PurchaseOrderReceipt.items),
            )
            .filter(PurchaseOrder.id == po_id)
            .one_or_none()
        )
        if po is None:
            raise NotFoundError(f"Purchase order {po_id} not found.")

        items = []
        for item in po.items:
            already = _already_received(session, item.id)
            items.append({
                "po_item_id":       item.id,
                "medicine_id":      item.medicine_id,
                "medicine_name":    item.medicine.name if item.medicine else "",
                "ordered_quantity": item.ordered_quantity,
                "received_quantity": already,
                "remaining":        item.ordered_quantity - already,
                "unit_price":       float(item.unit_price),
                "notes":            item.notes or "",
            })

        return {
            "po_id":                  po.id,
            "po_number":              po.po_number,
            "supplier_id":            po.supplier_id,
            "supplier_name":          po.supplier.name if po.supplier else "",
            "order_date":             po.order_date.isoformat(),
            "expected_delivery_date": (
                po.expected_delivery_date.isoformat()
                if po.expected_delivery_date else None
            ),
            "status":                 po.status.value,
            "notes":                  po.notes or "",
            "items":                  items,
            "receipt_count":          len(po.receipts),
        }
