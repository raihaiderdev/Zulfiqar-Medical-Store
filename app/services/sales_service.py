"""
Sales / POS (Phase 1 §12, §19). `complete_sale()` is the single entry
point that atomically validates stock, allocates batches FEFO, deducts
inventory, records the ledger, and creates the invoice — all inside one
DB transaction, with stock re-validated at commit time (not just when the
cart was built) so two POS actions racing on the same batch can't oversell.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Optional, TypedDict

from sqlalchemy.orm import Session

from app.config.settings import settings
from app.database.session import session_scope
from app.models import MedicineBatch, Sale, SaleItem
from app.models.enums import StockTxnType
from app.repositories.inventory_repository import MedicineBatchRepository
from app.security.decorators import require_permission
from app.security.session_context import current_session
from app.services import audit_service, stock_service
from app.utils.exceptions import AuthorizationError, ValidationError
from app.utils.numbering import next_invoice_number

class SaleLineInput(TypedDict, total=False):
    medicine_id: int
    quantity: int
    batch_id: Optional[int]  # manual override; omit to let FEFO pick
    line_discount: float


@dataclass
class SaleResult:
    sale_id: int
    invoice_number: str
    total: float
    change_due: float


def allocate_fefo(session: Session, medicine_id: int, quantity: int) -> list[tuple[MedicineBatch, int]]:
    """Greedily consumes the earliest-expiring non-expired batches first
    until `quantity` is satisfied. Raises if total available stock is
    insufficient — expired batches are never included as candidates."""
    candidates = MedicineBatchRepository(session).fefo_candidates(medicine_id)
    remaining = quantity
    allocation: list[tuple[MedicineBatch, int]] = []

    for batch in candidates:
        if remaining <= 0:
            break
        take = min(batch.quantity, remaining)
        if take > 0:
            allocation.append((batch, take))
            remaining -= take

    if remaining > 0:
        available = sum(b.quantity for b in candidates)
        raise ValidationError(
            f"Insufficient stock for medicine {medicine_id}: requested {quantity}, "
            f"only {available} available across non-expired batches."
        )
    return allocation


@require_permission("sales.create")
def complete_sale(
    *,
    lines: list[SaleLineInput],
    amount_paid: float,
    customer_id: Optional[int] = None,
    discount_total: float = 0.0,
    notes: Optional[str] = None,
    allow_expired_override: bool = False,
    doctor_fee: Optional[dict] = None,
) -> SaleResult:
    if not lines:
        raise ValidationError("A sale must have at least one line item.")
    if discount_total < 0:
        raise ValidationError("Discount cannot be negative.")

    # Authorization check BEFORE any DB work so we never touch stock for
    # an unauthorized request (fail-fast, cleaner transaction boundary).
    if discount_total > 0 and not current_session.has_permission("sales.discount"):
        raise AuthorizationError("You are not authorized to apply discounts.")

    with session_scope() as session:
        sale = Sale(
            invoice_number=next_invoice_number(session, date.today().year),
            sale_date=date.today(),
            customer_id=customer_id,
            cashier_id=current_session.user_id,
            subtotal=0,
            discount_total=discount_total,
            tax_total=0,
            total=0,
            amount_paid=amount_paid,
            change_due=0,
            notes=notes,
        )
        session.add(sale)
        session.flush()

        subtotal = 0.0

        for line in lines:
            quantity = line["quantity"]
            if quantity <= 0:
                raise ValidationError("Sale line quantity must be positive.")
            line_discount = line.get("line_discount", 0.0)
            if line_discount < 0:
                raise ValidationError("Line discount cannot be negative.")

            if line.get("batch_id"):
                batch = session.get(MedicineBatch, line["batch_id"])
                if batch is None:
                    raise ValidationError(f"Batch {line['batch_id']} not found.")
                # Check expiry override: read from DB settings first (togglable from UI),
                # fall back to the env-var frozen settings object.
                from app.services.settings_service import get_setting as _get_setting
                override_from_db = (_get_setting("expiry.clearance_override", default="false") or "false").lower() == "true"
                override_enabled = override_from_db or settings.expiry_clearance_override_enabled
                if batch.expiry_date < date.today() and not (
                    allow_expired_override and override_enabled
                ):
                    raise ValidationError(
                        f"Batch '{batch.batch_number}' is expired and cannot be sold "
                        f"without an authorized clearance override."
                    )
                if batch.quantity < quantity:
                    raise ValidationError(
                        f"Insufficient stock in batch '{batch.batch_number}': "
                        f"requested {quantity}, available {batch.quantity}."
                    )
                allocation = [(batch, quantity)]
            else:
                allocation = allocate_fefo(session, line["medicine_id"], quantity)

            # Apply the line discount to the first sub-line only, to avoid
            # rounding drift from splitting it across batches.
            remaining_discount = line_discount

            for batch, qty in allocation:
                this_discount = remaining_discount
                remaining_discount = 0.0

                session.add(
                    SaleItem(
                        sale_id=sale.id,
                        batch_id=batch.id,
                        quantity=qty,
                        unit_price=batch.selling_price,
                        unit_cost=batch.purchase_price,
                        line_discount=this_discount,
                    )
                )
                stock_service.apply_stock_change(
                    session,
                    batch=batch,
                    delta=-qty,
                    txn_type=StockTxnType.SALE,
                    user_id=current_session.user_id,
                    reference=sale.invoice_number,
                    reason="POS sale",
                )
                subtotal += float(batch.selling_price) * qty - this_discount

        # No cap on discount amount — staff can give any discount they choose.
        # The only constraint is that the total cannot go below zero
        # (you cannot charge a negative price).
        total = round(subtotal - discount_total, 2)
        if total < 0:
            raise ValidationError("Discount cannot exceed the sale total.")

        sale.subtotal = round(subtotal, 2)
        sale.total = total
        sale.change_due = round(max(0.0, amount_paid - total), 2)
        session.add(sale)

        audit_service.record(
            session,
            user_id=current_session.user_id,
            action="SALE_COMPLETED",
            entity="sales",
            entity_id=sale.id,
            new_value={"invoice_number": sale.invoice_number, "total": total},
        )

        # Record doctor fee atomically in the same transaction
        if doctor_fee:
            import math as _math
            from app.services.doctor_fee_service import _record_fee_in_session, _validate_amount, _validate_doctor_name
            _validate_doctor_name(doctor_fee.get("doctor_name", ""))
            _validate_amount(float(doctor_fee.get("amount", 0)))
            _record_fee_in_session(
                session,
                fee_date=date.today(),
                doctor_name=doctor_fee["doctor_name"],
                amount=float(doctor_fee["amount"]),
                payment_method=doctor_fee.get("payment_method"),
                patient_reference=doctor_fee.get("patient_reference"),
                notes=doctor_fee.get("notes"),
                sale_reference=sale.invoice_number,
                user_id=current_session.user_id,
            )

        return SaleResult(
            sale_id=sale.id, invoice_number=sale.invoice_number, total=total, change_due=sale.change_due
        )


@require_permission("sales.view")
def list_sales(
    *,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    limit: int = 200,
) -> list[dict]:
    """Return a summary list of sales, newest first, optionally filtered by date range."""
    with session_scope() as session:
        q = session.query(Sale)
        if date_from:
            q = q.filter(Sale.sale_date >= date_from)
        if date_to:
            q = q.filter(Sale.sale_date <= date_to)
        sales = q.order_by(Sale.sale_date.desc(), Sale.id.desc()).limit(limit).all()
        return [
            {
                "sale_id": s.id,
                "invoice_number": s.invoice_number,
                "date": s.sale_date.isoformat(),
                "total": float(s.total),
                "amount_paid": float(s.amount_paid),
                "change_due": float(s.change_due),
                "status": s.status.value,
                "cashier_id": s.cashier_id,
            }
            for s in sales
        ]


@require_permission("sales.view")
def get_sale_detail(sale_id: int) -> dict:
    with session_scope() as session:
        sale = session.get(Sale, sale_id)
        if sale is None:
            raise ValidationError(f"Sale {sale_id} not found.")
        return {
            "invoice_number": sale.invoice_number,
            "date": sale.sale_date.isoformat(),
            "subtotal": float(sale.subtotal),
            "discount_total": float(sale.discount_total),
            "tax_total": float(sale.tax_total),
            "total": float(sale.total),
            "amount_paid": float(sale.amount_paid),
            "change_due": float(sale.change_due),
            "status": sale.status.value,
            "items": [
                {
                    "sale_item_id": item.id,          # required by edit_invoice_dialog
                    "medicine_name": item.batch.medicine.name,
                    "batch_number": item.batch.batch_number,
                    "quantity": item.quantity,
                    "unit_price": float(item.unit_price),
                    "unit_cost": float(item.unit_cost),
                    "line_discount": float(item.line_discount),
                    "line_total": item.line_total,
                    "line_profit": item.line_profit,
                }
                for item in sale.items
            ],
        }
