from __future__ import annotations

from datetime import date
from typing import List, Optional

from sqlalchemy import CheckConstraint, Date, Enum, ForeignKey, Integer, Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, IDMixin, TimestampMixin
from app.models.enums import SaleStatus

MONEY = Numeric(12, 2)


class Sale(Base, IDMixin, TimestampMixin):
    __tablename__ = "sales"
    __table_args__ = (UniqueConstraint("invoice_number", name="uq_sale_invoice_number"),)

    invoice_number: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    sale_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    customer_id: Mapped[Optional[int]] = mapped_column(ForeignKey("customers.id", ondelete="SET NULL"))
    cashier_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))

    subtotal: Mapped[float] = mapped_column(MONEY, nullable=False, default=0)
    discount_total: Mapped[float] = mapped_column(MONEY, nullable=False, default=0)
    tax_total: Mapped[float] = mapped_column(MONEY, nullable=False, default=0)
    total: Mapped[float] = mapped_column(MONEY, nullable=False, default=0)
    amount_paid: Mapped[float] = mapped_column(MONEY, nullable=False, default=0)
    change_due: Mapped[float] = mapped_column(MONEY, nullable=False, default=0)

    status: Mapped[SaleStatus] = mapped_column(
        Enum(SaleStatus, native_enum=False, length=24), default=SaleStatus.COMPLETED, nullable=False
    )
    notes: Mapped[Optional[str]] = mapped_column(String(500))

    items: Mapped[List["SaleItem"]] = relationship(back_populates="sale", cascade="all, delete-orphan")
    customer: Mapped[Optional["Customer"]] = relationship()
    cashier: Mapped[Optional["User"]] = relationship()

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Sale id={self.id} invoice={self.invoice_number!r} total={self.total}>"


class SaleItem(Base, IDMixin, TimestampMixin):
    __tablename__ = "sale_items"
    __table_args__ = (CheckConstraint("quantity > 0", name="ck_sale_item_quantity_positive"),)

    sale_id: Mapped[int] = mapped_column(ForeignKey("sales.id", ondelete="CASCADE"), nullable=False)
    batch_id: Mapped[int] = mapped_column(ForeignKey("medicine_batches.id", ondelete="RESTRICT"), nullable=False)

    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    # unit_price / unit_cost are copied at time of sale — never recalculated
    # later from the batch's *current* prices, so historical profit stays accurate.
    unit_price: Mapped[float] = mapped_column(MONEY, nullable=False)
    unit_cost: Mapped[float] = mapped_column(MONEY, nullable=False)
    line_discount: Mapped[float] = mapped_column(MONEY, nullable=False, default=0)

    sale: Mapped["Sale"] = relationship(back_populates="items")
    batch: Mapped["MedicineBatch"] = relationship()

    @property
    def line_total(self) -> float:
        return round(self.unit_price * self.quantity - self.line_discount, 2)

    @property
    def line_profit(self) -> float:
        return round((self.unit_price - self.unit_cost) * self.quantity - self.line_discount, 2)


class SaleReturn(Base, IDMixin, TimestampMixin):
    __tablename__ = "sale_returns"

    sale_id: Mapped[int] = mapped_column(ForeignKey("sales.id", ondelete="RESTRICT"), nullable=False)
    return_date: Mapped[date] = mapped_column(Date, nullable=False)
    reason: Mapped[Optional[str]] = mapped_column(String(255))
    created_by_user_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    restock: Mapped[bool] = mapped_column(default=True, nullable=False)

    items: Mapped[List["SaleReturnItem"]] = relationship(back_populates="sale_return", cascade="all, delete-orphan")
    sale: Mapped["Sale"] = relationship()


class SaleReturnItem(Base, IDMixin, TimestampMixin):
    __tablename__ = "sale_return_items"
    __table_args__ = (CheckConstraint("quantity > 0", name="ck_sale_return_item_quantity_positive"),)

    sale_return_id: Mapped[int] = mapped_column(ForeignKey("sale_returns.id", ondelete="CASCADE"), nullable=False)
    sale_item_id: Mapped[int] = mapped_column(ForeignKey("sale_items.id", ondelete="RESTRICT"), nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)

    sale_return: Mapped["SaleReturn"] = relationship(back_populates="items")
    sale_item: Mapped["SaleItem"] = relationship()
