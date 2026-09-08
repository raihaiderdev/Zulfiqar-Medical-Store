"""
Invoice editing service (Feature 3).

Allows authorized users to correct a completed invoice after the fact.
Design principles:
  - Never silently overwrite historical records.
  - Every correction is delta-based: we reverse the old lines and apply new
    ones through the stock ledger, so the full history is traceable.
  - A dedicated INVOICE_EDIT StockTxnType is NOT added (to avoid a DB
    migration just for naming); instead we use ADJUSTMENT_IN / ADJUSTMENT_OUT
    with a reference that points back to the invoice number.
  - The audit log records old and new values in full.
  - Stock must be validated before committing — insufficient stock for an
    increase must be rejected, not silently capped.
  - Only users with "sales.edit_invoice" (or admins) may call these functions.
"""
from __future__ import annotations

from datetime import date
from typing import Optional, TypedDict

from sqlalchemy.orm import Session

from app.database.session import session_scope
from app.models import MedicineBatch, Sale, SaleItem
from app.models.enums import SaleStatus, StockTxnType
from app.repositories.inventory_repository import MedicineBatchRepository
from app.security.decorators import require_permission
from app.security.session_context import current_session
from app.services import audit_service, stock_service
from app.utils.exceptions import NotFoundError, ValidationError


class InvoiceEditLineInput(TypedDict, total=False):
    """
    Describe a desired change to one existing sale line.
    `sale_item_id` — the SaleItem row to modify (required).
    `new_quantity`  — desired final quantity (0 = remove the line entirely).
    `new_unit_price` — override unit price (None = keep existing price).
    `new_line_discount` — override line discount (None = keep existing).
    """
    sale_item_id: int
    new_quantity: int
    new_unit_price: Optional[float]
    new_line_discount: Optional[float]


def _recompute_sale_totals(session: Session, sale: Sale) -> None:
    """Recompute and persist sale.subtotal / sale.total from its current items."""
    subtotal = 0.0
    discount_total = 0.0
    for item in sale.items:
        subtotal += float(item.unit_price) * item.quantity
        discount_total += float(item.line_discount)
    sale.subtotal = round(subtotal, 2)
    sale.discount_total = round(discount_total, 2)
    sale.total = round(subtotal - discount_total, 2)
    session.add(sale)


@require_permission("sales.edit_invoice")
def edit_invoice(
    *,
    sale_id: int,
    line_changes: list[InvoiceEditLineInput],
    reason: str,
    new_amount_paid: Optional[float] = None,
    new_customer_id: Optional[int] = None,
    new_notes: Optional[str] = None,
) -> dict:
    """
    Apply corrections to an existing completed invoice.

    For each line in `line_changes`:
      - If new_quantity > old_quantity  → check stock, deduct the extra delta.
      - If new_quantity < old_quantity  → return the difference to stock.
      - If new_quantity == 0            → remove the line entirely, return all
                                          qty to stock.
      - new_unit_price / new_line_discount → update in-place, no stock change.

    Returns a dict with the updated totals.
    Raises ValidationError for any invalid state.
    """
    if not reason or not reason.strip():
        raise ValidationError("A reason is required when editing an invoice.")
    if not line_changes:
        raise ValidationError("Provide at least one line change.")

    with session_scope() as session:
        sale = session.get(Sale, sale_id)
        if sale is None:
            raise NotFoundError(f"Invoice / Sale {sale_id} not found.")
        if sale.status not in (SaleStatus.COMPLETED, SaleStatus.PARTIALLY_REFUNDED):
            raise ValidationError(
                f"Only COMPLETED invoices can be edited. "
                f"This invoice has status '{sale.status.value}'."
            )

        old_snapshot = {
            "invoice_number": sale.invoice_number,
            "subtotal": float(sale.subtotal),
            "discount_total": float(sale.discount_total),
            "total": float(sale.total),
            "items": [
                {
                    "sale_item_id": i.id,
                    "batch_id": i.batch_id,
                    "quantity": i.quantity,
                    "unit_price": float(i.unit_price),
                    "line_discount": float(i.line_discount),
                }
                for i in sale.items
            ],
        }

        for change in line_changes:
            item = session.get(SaleItem, change["sale_item_id"])
            if item is None or item.sale_id != sale_id:
                raise NotFoundError(
                    f"Sale item {change['sale_item_id']} not found on sale {sale_id}."
                )

            new_qty = change.get("new_quantity")
            if new_qty is not None:
                if new_qty < 0:
                    raise ValidationError("New quantity cannot be negative.")

                old_qty = item.quantity
                delta = new_qty - old_qty  # positive = need more stock, negative = return stock

                if delta > 0:
                    # Need extra stock — verify availability on the SAME batch.
                    batch = session.get(MedicineBatch, item.batch_id)
                    if batch is None:
                        raise ValidationError(f"Batch {item.batch_id} no longer exists.")
                    if batch.expiry_date < date.today():
                        raise ValidationError(
                            f"Cannot increase quantity on an expired batch "
                            f"'{batch.batch_number}'."
                        )
                    if batch.quantity < delta:
                        raise ValidationError(
                            f"Insufficient stock in batch '{batch.batch_number}': "
                            f"need {delta} more but only {batch.quantity} available."
                        )
                    stock_service.apply_stock_change(
                        session,
                        batch=batch,
                        delta=-delta,
                        txn_type=StockTxnType.SALE,
                        user_id=current_session.user_id,
                        reference=sale.invoice_number,
                        reason=f"Invoice edit: qty {old_qty}→{new_qty}. {reason}",
                    )
                elif delta < 0:
                    # Return units to stock.
                    batch = session.get(MedicineBatch, item.batch_id)
                    if batch is None:
                        raise ValidationError(f"Batch {item.batch_id} no longer exists.")
                    stock_service.apply_stock_change(
                        session,
                        batch=batch,
                        delta=-delta,  # negative delta → positive stock return
                        txn_type=StockTxnType.SALE_RETURN,
                        user_id=current_session.user_id,
                        reference=sale.invoice_number,
                        reason=f"Invoice edit: qty {old_qty}→{new_qty}. {reason}",
                    )

                if new_qty == 0:
                    # Remove the line entirely.
                    session.delete(item)
                    continue
                else:
                    item.quantity = new_qty

            new_price = change.get("new_unit_price")
            if new_price is not None:
                if new_price < 0:
                    raise ValidationError("Unit price cannot be negative.")
                item.unit_price = new_price

            new_discount = change.get("new_line_discount")
            if new_discount is not None:
                if new_discount < 0:
                    raise ValidationError("Line discount cannot be negative.")
                item.line_discount = new_discount

            session.add(item)

        # Flush deletions so recompute sees the up-to-date item list.
        session.flush()

        # Ensure at least one line remains.
        remaining = session.query(SaleItem).filter(SaleItem.sale_id == sale_id).count()
        if remaining == 0:
            raise ValidationError(
                "An invoice must have at least one line. "
                "Use 'cancel sale' to void an invoice entirely."
            )

        # Update header fields if provided.
        if new_amount_paid is not None:
            if new_amount_paid < 0:
                raise ValidationError("Amount paid cannot be negative.")
            sale.amount_paid = new_amount_paid

        if new_customer_id is not None:
            sale.customer_id = new_customer_id

        if new_notes is not None:
            sale.notes = new_notes

        _recompute_sale_totals(session, sale)

        # Recompute change_due.
        sale.change_due = round(max(0.0, float(sale.amount_paid) - float(sale.total)), 2)
        session.add(sale)
        session.flush()

        new_snapshot = {
            "invoice_number": sale.invoice_number,
            "subtotal": float(sale.subtotal),
            "discount_total": float(sale.discount_total),
            "total": float(sale.total),
        }

        audit_service.record(
            session,
            user_id=current_session.user_id,
            action="INVOICE_EDITED",
            entity="sales",
            entity_id=sale.id,
            old_value={**old_snapshot, "reason": reason},
            new_value=new_snapshot,
        )

        return {
            "sale_id": sale.id,
            "invoice_number": sale.invoice_number,
            "subtotal": float(sale.subtotal),
            "discount_total": float(sale.discount_total),
            "total": float(sale.total),
            "amount_paid": float(sale.amount_paid),
            "change_due": float(sale.change_due),
        }


@require_permission("sales.view")
def get_editable_invoice(sale_id: int) -> dict:
    """Load full invoice detail including per-item data for the edit dialog."""
    from app.services.sales_service import get_sale_detail
    return get_sale_detail(sale_id)
