from __future__ import annotations

from datetime import date
from typing import List, Optional

from sqlalchemy import CheckConstraint, Date, ForeignKey, Index, Integer, Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, IDMixin, TimestampMixin

MONEY = Numeric(12, 2)  # store money as fixed-point decimal, never float


class MedicineBatch(Base, IDMixin, TimestampMixin):
    """
    The actual inventory unit. A Medicine can have many batches; stock
    quantity, cost and expiry all live here, never on Medicine itself.
    """
    __tablename__ = "medicine_batches"
    __table_args__ = (
        UniqueConstraint("medicine_id", "batch_number", name="uq_batch_per_medicine"),
        CheckConstraint("quantity >= 0", name="ck_batch_quantity_non_negative"),
        CheckConstraint("purchase_price >= 0", name="ck_batch_purchase_price_non_negative"),
        CheckConstraint("selling_price >= 0", name="ck_batch_selling_price_non_negative"),
        Index("ix_batch_expiry", "expiry_date"),
        Index("ix_batch_medicine_expiry", "medicine_id", "expiry_date"),
    )

    medicine_id: Mapped[int] = mapped_column(ForeignKey("medicines.id", ondelete="CASCADE"), nullable=False)
    shelf_id: Mapped[Optional[int]] = mapped_column(ForeignKey("shelves.id", ondelete="SET NULL"))
    supplier_id: Mapped[Optional[int]] = mapped_column(ForeignKey("suppliers.id", ondelete="SET NULL"))

    batch_number: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    purchase_price: Mapped[float] = mapped_column(MONEY, nullable=False)
    selling_price: Mapped[float] = mapped_column(MONEY, nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    manufacturing_date: Mapped[Optional[date]] = mapped_column(Date)
    expiry_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)

    is_active: Mapped[bool] = mapped_column(default=True, nullable=False)

    medicine: Mapped["Medicine"] = relationship(back_populates="batches")
    shelf: Mapped[Optional["Shelf"]] = relationship()
    supplier: Mapped[Optional["Supplier"]] = relationship()
    stock_transactions: Mapped[List["StockTransaction"]] = relationship(back_populates="batch")

    def __repr__(self) -> str:  # pragma: no cover
        return f"<MedicineBatch id={self.id} medicine_id={self.medicine_id} batch={self.batch_number!r} qty={self.quantity}>"
