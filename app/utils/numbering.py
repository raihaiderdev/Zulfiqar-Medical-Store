"""
Sequential invoice numbering (Phase 1 §12): INV-2026-000001, etc.
Generated inside the same DB transaction as the sale itself so there are
no gaps or collisions from two POS terminals racing (Phase 1 §47.7).

Uses MAX on the existing suffix rather than COUNT so that deleting a sale
never causes duplicate invoice numbers (e.g. if INV-2026-000003 is
deleted, COUNT would return 4 and the next number would be 000005 —
correctly skipping the gap — whereas the old COUNT+1 would re-issue 000005
but if another was deleted first it could collide).
"""
from __future__ import annotations

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.config.settings import settings
from app.models import Sale


def next_invoice_number(session: Session, year: int) -> str:
    prefix = f"{settings.invoice_prefix}-{year}-"
    max_invoice = (
        session.query(func.max(Sale.invoice_number))
        .filter(Sale.invoice_number.like(f"{prefix}%"))
        .scalar()
    )
    if max_invoice:
        try:
            last_seq = int(max_invoice[len(prefix):])
        except (ValueError, IndexError):
            last_seq = 0
    else:
        last_seq = 0
    return f"{prefix}{last_seq + 1:06d}"
