"""
DoctorFee model — records doctor consultation fees as a standalone
business transaction, completely separate from medicine sales and inventory.
"""
from __future__ import annotations

from datetime import date
from typing import Optional

from sqlalchemy import Date, ForeignKey, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, IDMixin, TimestampMixin

MONEY = Numeric(12, 2)


class DoctorFee(Base, IDMixin, TimestampMixin):
    """
    A single doctor consultation fee entry.

    status values:
      ACTIVE    — valid, counted in totals
      CORRECTED — edited in place; audit log holds old/new values
      VOIDED    — cancelled; excluded from totals but kept for audit
    """
    __tablename__ = "doctor_fees"

    fee_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    doctor_name: Mapped[str] = mapped_column(String(180), nullable=False, index=True)
    amount: Mapped[float] = mapped_column(MONEY, nullable=False)

    # Optional — any user-entered method string (CASH, CARD, ONLINE, …)
    payment_method: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)

    # Optional, non-identifying reference (token number, initials, etc.)
    patient_reference: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)

    notes: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)

    # Invoice number of the linked sale (when fee was added via POS)
    sale_reference: Mapped[Optional[str]] = mapped_column(String(32), nullable=True, index=True)

    status: Mapped[str] = mapped_column(String(16), nullable=False, default="ACTIVE")

    created_by_user_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    # Relationship (lazy load is fine — used only in service layer dicts)
    created_by: Mapped[Optional["User"]] = relationship(foreign_keys=[created_by_user_id])  # type: ignore[name-defined]
