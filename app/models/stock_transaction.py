from __future__ import annotations

from typing import Optional

from sqlalchemy import Enum, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, IDMixin, TimestampMixin
from app.models.enums import StockTxnType


class StockTransaction(Base, IDMixin, TimestampMixin):
    """
    Append-only ledger. Every quantity change on a MedicineBatch must be
    accompanied by exactly one row here. Application code should never
    write to MedicineBatch.quantity without also writing a matching
    StockTransaction in the same DB transaction.
    """
    __tablename__ = "stock_transactions"

    batch_id: Mapped[int] = mapped_column(ForeignKey("medicine_batches.id", ondelete="RESTRICT"), nullable=False, index=True)
    txn_type: Mapped[StockTxnType] = mapped_column(Enum(StockTxnType, native_enum=False, length=24), nullable=False, index=True)

    quantity: Mapped[int] = mapped_column(Integer, nullable=False)  # signed delta
    previous_quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    new_quantity: Mapped[int] = mapped_column(Integer, nullable=False)

    reference: Mapped[Optional[str]] = mapped_column(String(64))  # e.g. invoice number, purchase id
    reason: Mapped[Optional[str]] = mapped_column(String(255))
    user_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))

    batch: Mapped["MedicineBatch"] = relationship(back_populates="stock_transactions")
    user: Mapped[Optional["User"]] = relationship()

    def __repr__(self) -> str:  # pragma: no cover
        return f"<StockTransaction {self.txn_type} batch={self.batch_id} qty={self.quantity}>"
