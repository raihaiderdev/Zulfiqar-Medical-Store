from __future__ import annotations

from datetime import date
from typing import List, Optional

from sqlalchemy import CheckConstraint, Date, Enum, ForeignKey, Integer, Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, IDMixin, TimestampMixin
from app.models.enums import PaymentStatus

MONEY = Numeric(12, 2)


class Purchase(Base, IDMixin, TimestampMixin):
    __tablename__ = "purchases"
    __table_args__ = (UniqueConstraint("supplier_invoice_number", "supplier_id", name="uq_purchase_supplier_invoice"),)

    supplier_id: Mapped[int] = mapped_column(ForeignKey("suppliers.id", ondelete="RESTRICT"), nullable=False)
    supplier_invoice_number: Mapped[Optional[str]] = mapped_column(String(64))
    purchase_date: Mapped[date] = mapped_column(Date, nullable=False)
    payment_status: Mapped[PaymentStatus] = mapped_column(
        Enum(PaymentStatus, native_enum=False, length=16), default=PaymentStatus.UNPAID, nullable=False
    )
    total_cost: Mapped[float] = mapped_column(MONEY, nullable=False, default=0)
    notes: Mapped[Optional[str]] = mapped_column(String(500))
    created_by_user_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))

    items: Mapped[List["PurchaseItem"]] = relationship(back_populates="purchase", cascade="all, delete-orphan")
    supplier: Mapped["Supplier"] = relationship()


class PurchaseItem(Base, IDMixin, TimestampMixin):
    __tablename__ = "purchase_items"
    __table_args__ = (CheckConstraint("quantity > 0", name="ck_purchase_item_quantity_positive"),)

    purchase_id: Mapped[int] = mapped_column(ForeignKey("purchases.id", ondelete="CASCADE"), nullable=False)
    batch_id: Mapped[int] = mapped_column(ForeignKey("medicine_batches.id", ondelete="RESTRICT"), nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    purchase_price: Mapped[float] = mapped_column(MONEY, nullable=False)

    purchase: Mapped["Purchase"] = relationship(back_populates="items")
    batch: Mapped["MedicineBatch"] = relationship()


class PurchaseReturn(Base, IDMixin, TimestampMixin):
    __tablename__ = "purchase_returns"

    purchase_id: Mapped[int] = mapped_column(ForeignKey("purchases.id", ondelete="RESTRICT"), nullable=False)
    return_date: Mapped[date] = mapped_column(Date, nullable=False)
    reason: Mapped[Optional[str]] = mapped_column(String(255))
    created_by_user_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))

    items: Mapped[List["PurchaseReturnItem"]] = relationship(
        back_populates="purchase_return", cascade="all, delete-orphan"
    )
    purchase: Mapped["Purchase"] = relationship()


class PurchaseReturnItem(Base, IDMixin, TimestampMixin):
    __tablename__ = "purchase_return_items"
    __table_args__ = (CheckConstraint("quantity > 0", name="ck_purchase_return_item_quantity_positive"),)

    purchase_return_id: Mapped[int] = mapped_column(
        ForeignKey("purchase_returns.id", ondelete="CASCADE"), nullable=False
    )
    purchase_item_id: Mapped[int] = mapped_column(ForeignKey("purchase_items.id", ondelete="RESTRICT"), nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)

    purchase_return: Mapped["PurchaseReturn"] = relationship(back_populates="items")
    purchase_item: Mapped["PurchaseItem"] = relationship()
