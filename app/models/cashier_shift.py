"""
Cashier Shift models — Phase 2.

Tracks opening cash, sales during shift, and closing reconciliation.
Cash variance = actual_closing_cash - expected_closing_cash.
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, Enum, ForeignKey, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, IDMixin, TimestampMixin

import enum

MONEY = Numeric(12, 2)


class ShiftStatus(str, enum.Enum):
    OPEN   = "OPEN"
    CLOSED = "CLOSED"


class CashierShift(Base, IDMixin, TimestampMixin):
    """
    One cashier shift. Stock and sales are linked via Sale.cashier_id
    and the shift's opened_at / closed_at timestamps.

    Cash flow:
        expected_closing = opening_cash
                         + sum(cash sales during shift)
                         - sum(cash refunds during shift)
                         - sum(cash expenses during shift)

        variance = actual_closing_cash - expected_closing
    """
    __tablename__ = "cashier_shifts"

    cashier_id:    Mapped[int]      = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    opened_at:     Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    closed_at:     Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    status:        Mapped[ShiftStatus] = mapped_column(
        Enum(ShiftStatus, native_enum=False, length=8),
        default=ShiftStatus.OPEN, nullable=False, index=True
    )

    opening_cash:         Mapped[float] = mapped_column(MONEY, nullable=False, default=0)
    actual_closing_cash:  Mapped[Optional[float]] = mapped_column(MONEY)
    notes:                Mapped[Optional[str]]   = mapped_column(Text)

    cashier: Mapped["User"] = relationship(foreign_keys=[cashier_id])

    @property
    def is_open(self) -> bool:
        return self.status == ShiftStatus.OPEN

    def __repr__(self) -> str:
        return (
            f"<CashierShift id={self.id} cashier_id={self.cashier_id} "
            f"status={self.status.value}>"
        )
