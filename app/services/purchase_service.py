"""
Purchase management (Phase 1 §15). Recording a purchase atomically:
creates/updates the batch, increases stock via stock_service (which
writes the matching ledger row), creates the Purchase/PurchaseItem
records, and updates the running total — all inside one DB transaction.
"""
from __future__ import annotations

from datetime import date
from typing import Optional, TypedDict

from app.database.session import session_scope
from app.models import MedicineBatch, Purchase, PurchaseItem
from app.models.enums import PaymentStatus, StockTxnType
from app.repositories.inventory_repository import LocationRepository, MedicineBatchRepository, SupplierRepository
from app.security.decorators import require_permission
from app.security.session_context import current_session
from app.services import audit_service, stock_service
from app.utils.exceptions import NotFoundError, ValidationError


class PurchaseLineInput(TypedDict, total=False):
    medicine_id: int
    batch_number: str
    quantity: int
    purchase_price: float
    selling_price: float
    expiry_date: date
    manufacturing_date: Optional[date]
    wardrobe_code: Optional[str]
    rack_code: Optional[str]
    shelf_code: Optional[str]


@require_permission("purchases.manage")
def record_purchase(
    *,
    supplier_id: int,
    lines: list[PurchaseLineInput],
    supplier_invoice_number: Optional[str] = None,
    purchase_date: Optional[date] = None,
    payment_status: PaymentStatus = PaymentStatus.UNPAID,
    notes: Optional[str] = None,
) -> int:
    if not lines:
        raise ValidationError("A purchase must have at least one line item.")

    purchase_date = purchase_date or date.today()

    with session_scope() as session:
        supplier = SupplierRepository(session).get(supplier_id)
        if supplier is None:
            raise NotFoundError(f"Supplier {supplier_id} not found.")

        purchase = Purchase(
            supplier_id=supplier_id,
            supplier_invoice_number=supplier_invoice_number,
            purchase_date=purchase_date,
            payment_status=payment_status,
            total_cost=0,
            notes=notes,
            created_by_user_id=current_session.user_id,
        )
        session.add(purchase)
        session.flush()

        batch_repo = MedicineBatchRepository(session)
        location_repo = LocationRepository(session)
        total_cost = 0.0

        for line in lines:
            quantity = line["quantity"]
            if quantity <= 0:
                raise ValidationError("Purchase line quantity must be positive.")
            if line["purchase_price"] < 0 or line["selling_price"] < 0:
                raise ValidationError("Prices cannot be negative.")

            batch = batch_repo.get_by_medicine_and_number(line["medicine_id"], line["batch_number"])
            if batch is None:
                shelf = None
                if line.get("wardrobe_code") and line.get("rack_code") and line.get("shelf_code"):
                    shelf = location_repo.get_or_create_full_location(
                        line["wardrobe_code"], line["rack_code"], line["shelf_code"]
                    )
                batch = MedicineBatch(
                    medicine_id=line["medicine_id"],
                    shelf_id=shelf.id if shelf else None,
                    supplier_id=supplier_id,
                    batch_number=line["batch_number"],
                    purchase_price=line["purchase_price"],
                    selling_price=line["selling_price"],
                    quantity=0,
                    manufacturing_date=line.get("manufacturing_date"),
                    expiry_date=line["expiry_date"],
                )
                session.add(batch)
                session.flush()
            else:
                # Existing batch topped up by a new purchase — refresh its
                # cost/selling price to reflect the latest purchase terms.
                batch.purchase_price = line["purchase_price"]
                batch.selling_price = line["selling_price"]
                session.add(batch)

            session.add(
                PurchaseItem(
                    purchase_id=purchase.id,
                    batch_id=batch.id,
                    quantity=quantity,
                    purchase_price=line["purchase_price"],
                )
            )

            stock_service.apply_stock_change(
                session,
                batch=batch,
                delta=quantity,
                txn_type=StockTxnType.PURCHASE,
                user_id=current_session.user_id,
                reference=supplier_invoice_number or f"purchase#{purchase.id}",
                reason="Purchase received",
            )

            total_cost += float(line["purchase_price"]) * quantity

        purchase.total_cost = total_cost
        session.add(purchase)

        audit_service.record(
            session,
            user_id=current_session.user_id,
            action="PURCHASE_RECORDED",
            entity="purchases",
            entity_id=purchase.id,
            new_value={"supplier_id": supplier_id, "total_cost": total_cost, "lines": len(lines)},
        )
        return purchase.id


@require_permission("purchases.manage")
def mark_purchase_paid(purchase_id: int) -> None:
    """Mark a purchase as fully paid."""
    from app.models.enums import PaymentStatus
    with session_scope() as session:
        purchase = session.get(Purchase, purchase_id)
        if purchase is None:
            raise NotFoundError(f"Purchase {purchase_id} not found.")
        purchase.payment_status = PaymentStatus.PAID
        session.add(purchase)
        audit_service.record(
            session, user_id=current_session.user_id, action="PURCHASE_MARKED_PAID",
            entity="purchases", entity_id=purchase_id,
        )


@require_permission("purchases.manage")
def supplier_purchase_history(supplier_id: int) -> list[dict]:
    with session_scope() as session:
        purchases = (
            session.query(Purchase)
            .filter(Purchase.supplier_id == supplier_id)
            .order_by(Purchase.purchase_date.desc())
            .all()
        )
        return [
            {
                "purchase_id": p.id,
                "date": p.purchase_date.isoformat(),
                "invoice_number": p.supplier_invoice_number,
                "total_cost": float(p.total_cost),
                "payment_status": p.payment_status.value,
            }
            for p in purchases
        ]
