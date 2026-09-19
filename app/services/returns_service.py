"""
Returns & stock adjustments (Phase 1 §16, §17 clearance, §47.5-6). Every
path here writes its own stock_transaction and never edits the original
sale/purchase record in place — corrections are additive, reversal
entries, per Phase 1 §47.7.

Exception: after a sale return, the Sale.status is updated to
PARTIALLY_REFUNDED (or REFUNDED if all items are returned) so the
dashboard revenue figures stay accurate and the cashier can see the
return was processed.  The sale.total is also reduced by the returned
value so "Total Sales" on the dashboard reflects net revenue.
"""
from __future__ import annotations

from datetime import date
from typing import Optional, TypedDict

from app.database.session import session_scope
from app.models import PurchaseItem, PurchaseReturn, PurchaseReturnItem, Sale, SaleItem, SaleReturn, SaleReturnItem
from app.models.enums import SaleStatus, StockTxnType
from app.security.decorators import require_permission
from app.security.session_context import current_session
from app.services import audit_service, stock_service
from app.utils.exceptions import NotFoundError, ValidationError


class ReturnLineInput(TypedDict):
    sale_item_id: int
    quantity: int


@require_permission("returns.process")
def process_sale_return(
    *,
    sale_id: int,
    lines: list[ReturnLineInput],
    reason: Optional[str] = None,
    restock: bool = True,
) -> int:
    if not lines:
        raise ValidationError("A return must have at least one line item.")

    with session_scope() as session:
        sale_return = SaleReturn(
            sale_id=sale_id,
            return_date=date.today(),
            reason=reason,
            created_by_user_id=current_session.user_id,
            restock=restock,
        )
        session.add(sale_return)
        session.flush()

        for line in lines:
            sale_item = session.get(SaleItem, line["sale_item_id"])
            if sale_item is None or sale_item.sale_id != sale_id:
                raise NotFoundError(f"Sale item {line['sale_item_id']} not found on sale {sale_id}.")

            already_returned = (
                session.query(SaleReturnItem)
                .join(SaleReturn)
                .filter(SaleReturnItem.sale_item_id == sale_item.id)
                .with_entities(SaleReturnItem.quantity)
                .all()
            )
            total_already_returned = sum(q for (q,) in already_returned)
            if line["quantity"] <= 0:
                raise ValidationError("Return quantity must be positive.")
            if total_already_returned + line["quantity"] > sale_item.quantity:
                raise ValidationError(
                    f"Cannot return {line['quantity']} units — only "
                    f"{sale_item.quantity - total_already_returned} remain returnable on this line."
                )

            session.add(
                SaleReturnItem(sale_return_id=sale_return.id, sale_item_id=sale_item.id, quantity=line["quantity"])
            )

            if restock:
                stock_service.apply_stock_change(
                    session,
                    batch=sale_item.batch,
                    delta=line["quantity"],
                    txn_type=StockTxnType.SALE_RETURN,
                    user_id=current_session.user_id,
                    reference=f"return-of-sale#{sale_id}",
                    reason=reason or "Customer sale return",
                )
            else:
                # Returned but unsellable (e.g. damaged on return) — remove
                # from circulation so inventory stays accurate.  delta is
                # negative because the customer returns the goods but they
                # cannot go back on the shelf; we record them as DAMAGED so
                # the loss is traceable (Phase 1 §17).
                stock_service.apply_stock_change(
                    session,
                    batch=sale_item.batch,
                    delta=-line["quantity"],
                    txn_type=StockTxnType.DAMAGED,
                    user_id=current_session.user_id,
                    reference=f"return-of-sale#{sale_id}",
                    reason=reason or "Returned but not restocked (damaged)",
                )

        audit_service.record(
            session,
            user_id=current_session.user_id,
            action="SALE_RETURN_PROCESSED",
            entity="sale_returns",
            entity_id=sale_return.id,
            new_value={"sale_id": sale_id, "lines": len(lines), "restock": restock},
        )

        # ── Update the Sale's status and total to reflect the return ───────
        sale = session.get(Sale, sale_id)
        if sale:
            # Calculate total returned value for this return
            returned_value = 0.0
            for line in lines:
                sale_item = session.get(SaleItem, line["sale_item_id"])
                if sale_item:
                    returned_value += float(sale_item.unit_price) * line["quantity"]

            # Reduce sale total (net of return)
            new_total = round(max(0.0, float(sale.total) - returned_value), 2)
            sale.total = new_total

            # Check if ALL items are fully returned → REFUNDED, else PARTIALLY_REFUNDED
            all_returned = True
            for item in sale.items:
                already_returned = (
                    session.query(SaleReturnItem)
                    .join(SaleReturn)
                    .filter(SaleReturnItem.sale_item_id == item.id)
                    .with_entities(SaleReturnItem.quantity)
                    .all()
                )
                total_ret = sum(q for (q,) in already_returned)
                if total_ret < item.quantity:
                    all_returned = False
                    break

            sale.status = SaleStatus.REFUNDED if all_returned else SaleStatus.PARTIALLY_REFUNDED
            session.add(sale)

        return sale_return.id


class PurchaseReturnLineInput(TypedDict):
    purchase_item_id: int
    quantity: int


@require_permission("returns.process")
def process_purchase_return(
    *,
    purchase_id: int,
    lines: list[PurchaseReturnLineInput],
    reason: Optional[str] = None,
) -> int:
    if not lines:
        raise ValidationError("A return must have at least one line item.")

    with session_scope() as session:
        purchase_return = PurchaseReturn(
            purchase_id=purchase_id, return_date=date.today(), reason=reason, created_by_user_id=current_session.user_id
        )
        session.add(purchase_return)
        session.flush()

        for line in lines:
            purchase_item = session.get(PurchaseItem, line["purchase_item_id"])
            if purchase_item is None or purchase_item.purchase_id != purchase_id:
                raise NotFoundError(f"Purchase item {line['purchase_item_id']} not found on purchase {purchase_id}.")
            if line["quantity"] <= 0:
                raise ValidationError("Return quantity must be positive.")
            if line["quantity"] > purchase_item.batch.quantity:
                raise ValidationError(
                    f"Cannot return {line['quantity']} units — only {purchase_item.batch.quantity} "
                    f"currently in stock for batch '{purchase_item.batch.batch_number}'."
                )

            session.add(
                PurchaseReturnItem(
                    purchase_return_id=purchase_return.id,
                    purchase_item_id=purchase_item.id,
                    quantity=line["quantity"],
                )
            )
            stock_service.apply_stock_change(
                session,
                batch=purchase_item.batch,
                delta=-line["quantity"],
                txn_type=StockTxnType.PURCHASE_RETURN,
                user_id=current_session.user_id,
                reference=f"return-of-purchase#{purchase_id}",
                reason=reason or "Supplier purchase return",
            )

        audit_service.record(
            session,
            user_id=current_session.user_id,
            action="PURCHASE_RETURN_PROCESSED",
            entity="purchase_returns",
            entity_id=purchase_return.id,
            new_value={"purchase_id": purchase_id, "lines": len(lines)},
        )
        return purchase_return.id


@require_permission("stock.adjust")
def adjust_stock(
    *,
    batch_id: int,
    delta: int,
    reason: str,
) -> None:
    """Manual stock correction. `delta` positive = ADJUSTMENT_IN, negative
    = ADJUSTMENT_OUT. A reason is mandatory — untraceable adjustments are
    exactly what Phase 1 §8 forbids."""
    if delta == 0:
        raise ValidationError("Adjustment delta cannot be zero.")
    if not reason or not reason.strip():
        raise ValidationError("A reason is required for every stock adjustment.")

    from app.models import MedicineBatch

    with session_scope() as session:
        batch = session.get(MedicineBatch, batch_id)
        if batch is None:
            raise NotFoundError(f"Batch {batch_id} not found.")

        txn_type = StockTxnType.ADJUSTMENT_IN if delta > 0 else StockTxnType.ADJUSTMENT_OUT
        stock_service.apply_stock_change(
            session, batch=batch, delta=delta, txn_type=txn_type, user_id=current_session.user_id, reason=reason
        )
        audit_service.record(
            session,
            user_id=current_session.user_id,
            action="STOCK_ADJUSTED",
            entity="medicine_batches",
            entity_id=batch.id,
            new_value={"delta": delta, "reason": reason},
        )


@require_permission("stock.adjust")
def write_off_expired_batch(batch_id: int, reason: Optional[str] = None) -> None:
    """Removes an expired batch's remaining stock from circulation
    (Phase 1 §17). Does not delete the batch — it stays for historical
    reporting with quantity 0."""
    from app.models import MedicineBatch

    with session_scope() as session:
        batch = session.get(MedicineBatch, batch_id)
        if batch is None:
            raise NotFoundError(f"Batch {batch_id} not found.")
        if batch.expiry_date >= date.today():
            raise ValidationError("Batch is not expired — use adjust_stock for other corrections.")
        if batch.quantity <= 0:
            raise ValidationError("Batch already has zero stock.")

        stock_service.apply_stock_change(
            session,
            batch=batch,
            delta=-batch.quantity,
            txn_type=StockTxnType.EXPIRED,
            user_id=current_session.user_id,
            reason=reason or "Expired stock write-off",
        )
        audit_service.record(
            session,
            user_id=current_session.user_id,
            action="EXPIRED_STOCK_WRITTEN_OFF",
            entity="medicine_batches",
            entity_id=batch.id,
        )


@require_permission("returns.process")
def get_sale_returnable_items(sale_id: int) -> list[dict]:
    """
    Return the line items of a sale together with how many units are still
    returnable (original qty minus already-returned qty).
    Used to populate the Return dialog.
    """
    with session_scope() as session:
        sale = session.get(Sale, sale_id)
        if sale is None:
            raise NotFoundError(f"Sale {sale_id} not found.")

        result = []
        for item in sale.items:
            already_returned = (
                session.query(SaleReturnItem)
                .join(SaleReturn)
                .filter(SaleReturnItem.sale_item_id == item.id)
                .with_entities(SaleReturnItem.quantity)
                .all()
            )
            total_ret = sum(q for (q,) in already_returned)
            returnable = item.quantity - total_ret
            if returnable > 0:
                result.append({
                    "sale_item_id":   item.id,
                    "medicine_name":  item.batch.medicine.name,
                    "batch_number":   item.batch.batch_number,
                    "sold_quantity":  item.quantity,
                    "already_returned": total_ret,
                    "returnable":     returnable,
                    "unit_price":     float(item.unit_price),
                    "line_total":     item.line_total,
                })
        return result
