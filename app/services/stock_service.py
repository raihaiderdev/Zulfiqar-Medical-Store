"""
Stock ledger service — the ONLY place in the codebase that should mutate
`MedicineBatch.quantity`. Every call writes a matching `StockTransaction`
row in the same DB transaction, per Phase 1 §8 ("never silently change
stock quantities... every important stock modification must be traceable").

Callers (purchase/sales/returns/adjustment services) pass an already-open
SQLAlchemy `session` so this participates in their transaction rather than
opening its own — a failed sale, for example, must roll back its stock
change along with everything else.
"""
from __future__ import annotations

from typing import Optional

from sqlalchemy.orm import Session

from app.models import MedicineBatch
from app.models.enums import StockTxnType
from app.models.stock_transaction import StockTransaction
from app.utils.exceptions import ValidationError


def apply_stock_change(
    session: Session,
    *,
    batch: MedicineBatch,
    delta: int,
    txn_type: StockTxnType,
    user_id: Optional[int],
    reference: Optional[str] = None,
    reason: Optional[str] = None,
) -> StockTransaction:
    """
    `delta` is signed: positive increases stock (PURCHASE, ADJUSTMENT_IN,
    SALE_RETURN-with-restock), negative decreases it (SALE, ADJUSTMENT_OUT,
    PURCHASE_RETURN, EXPIRED, DAMAGED).

    Refuses to let quantity go negative (Phase 1 §47.2) — the CHECK
    constraint on medicine_batches would also catch this at flush time,
    but failing fast here gives a much clearer error message to the UI.
    """
    previous_quantity = batch.quantity
    new_quantity = previous_quantity + delta
    if new_quantity < 0:
        raise ValidationError(
            f"Stock change would make batch '{batch.batch_number}' negative "
            f"({previous_quantity} {delta:+d} = {new_quantity})."
        )

    batch.quantity = new_quantity
    session.add(batch)

    txn = StockTransaction(
        batch_id=batch.id,
        txn_type=txn_type,
        quantity=delta,
        previous_quantity=previous_quantity,
        new_quantity=new_quantity,
        reference=reference,
        reason=reason,
        user_id=user_id,
    )
    session.add(txn)
    session.flush()
    return txn


def reconcile_batch_quantity(session: Session, batch: MedicineBatch) -> int:
    """Recomputes a batch's quantity purely from its stock_transactions
    ledger — a diagnostic/repair tool, not part of the normal write path."""
    total = (
        session.query(StockTransaction)
        .filter(StockTransaction.batch_id == batch.id)
        .with_entities(StockTransaction.quantity)
        .all()
    )
    return sum(q for (q,) in total)
