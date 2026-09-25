"""
Purchase Order models — Phase 2.

PurchaseOrder lifecycle:
    DRAFT → APPROVED → PARTIALLY_RECEIVED → COMPLETED
    Any state → CANCELLED

Stock increases ONLY when a PurchaseOrderReceipt is committed.
Creating or approving a PO never touches inventory.
"""
from __future__ import annotations

from datetime import date
from typing import List, Optional

from sqlalchemy import (
    CheckConstraint, Date, Enum, ForeignKey, Integer,
    Numeric, String, Text, UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, IDMixin, TimestampMixin

import enum

MONEY = Numeric(12, 2)


class POStatus(str, enum.Enum):
    DRAFT             = "DRAFT"
    APPROVED          = "APPROVED"
    PARTIALLY_RECEIVED = "PARTIALLY_RECEIVED"
    COMPLETED         = "COMPLETED"
    CANCELLED         = "CANCELLED"


class PurchaseOrder(Base, IDMixin, TimestampMixin):
    """
    A pre-purchase order sent to a supplier before goods arrive.
    Goods receipt happens via PurchaseOrderReceipt rows.
    """
    __tablename__ = "purchase_orders"

    supplier_id: Mapped[int] = mapped_column(
        ForeignKey("suppliers.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    po_number: Mapped[str] = mapped_column(String(32), nullable=False, unique=True, index=True)
    order_date: Mapped[date]  = mapped_column(Date, nullable=False)
    expected_delivery_date: Mapped[Optional[date]] = mapped_column(Date)
    status: Mapped[POStatus] = mapped_column(
        Enum(POStatus, native_enum=False, length=24),
        default=POStatus.DRAFT, nullable=False, index=True
    )
    notes: Mapped[Optional[str]] = mapped_column(Text)
    created_by_user_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    approved_by_user_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )

    supplier:    Mapped["Supplier"]          = relationship(foreign_keys=[supplier_id])
    created_by:  Mapped[Optional["User"]]    = relationship(foreign_keys=[created_by_user_id])
    approved_by: Mapped[Optional["User"]]    = relationship(foreign_keys=[approved_by_user_id])
    items:       Mapped[List["PurchaseOrderItem"]] = relationship(
        back_populates="purchase_order", cascade="all, delete-orphan"
    )
    receipts:    Mapped[List["PurchaseOrderReceipt"]] = relationship(
        back_populates="purchase_order", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<PurchaseOrder po={self.po_number!r} status={self.status.value}>"


class PurchaseOrderItem(Base, IDMixin, TimestampMixin):
    """One line on a purchase order."""
    __tablename__ = "purchase_order_items"
    __table_args__ = (
        CheckConstraint("ordered_quantity > 0", name="ck_poi_qty_positive"),
    )

    purchase_order_id: Mapped[int] = mapped_column(
        ForeignKey("purchase_orders.id", ondelete="CASCADE"), nullable=False, index=True
    )
    medicine_id: Mapped[int] = mapped_column(
        ForeignKey("medicines.id", ondelete="RESTRICT"), nullable=False
    )
    ordered_quantity: Mapped[int]  = mapped_column(Integer, nullable=False)
    unit_price:       Mapped[float] = mapped_column(MONEY, nullable=False)
    notes:            Mapped[Optional[str]] = mapped_column(String(255))

    purchase_order: Mapped["PurchaseOrder"] = relationship(back_populates="items")
    medicine:       Mapped["Medicine"]      = relationship()


class PurchaseOrderReceipt(Base, IDMixin, TimestampMixin):
    """
    A goods-received note (GRN) against a purchase order.
    Committing a receipt calls purchase_service.record_purchase() which
    creates the stock ledger entries atomically.
    Partial fulfillment is supported — multiple receipts per PO are allowed.
    """
    __tablename__ = "purchase_order_receipts"

    purchase_order_id: Mapped[int] = mapped_column(
        ForeignKey("purchase_orders.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    # Link to the Purchase record created when goods were received
    purchase_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("purchases.id", ondelete="SET NULL")
    )
    received_date: Mapped[date]  = mapped_column(Date, nullable=False)
    received_by_user_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    notes: Mapped[Optional[str]] = mapped_column(String(500))

    purchase_order: Mapped["PurchaseOrder"] = relationship(back_populates="receipts")
    purchase:       Mapped[Optional["Purchase"]] = relationship()
    received_by:    Mapped[Optional["User"]]     = relationship(foreign_keys=[received_by_user_id])
    items:          Mapped[List["PurchaseOrderReceiptItem"]] = relationship(
        back_populates="receipt", cascade="all, delete-orphan"
    )


class PurchaseOrderReceiptItem(Base, IDMixin, TimestampMixin):
    """One medicine line actually received in a GRN."""
    __tablename__ = "purchase_order_receipt_items"
    __table_args__ = (
        CheckConstraint("received_quantity > 0", name="ck_pori_qty_positive"),
    )

    receipt_id: Mapped[int] = mapped_column(
        ForeignKey("purchase_order_receipts.id", ondelete="CASCADE"), nullable=False
    )
    po_item_id: Mapped[int] = mapped_column(
        ForeignKey("purchase_order_items.id", ondelete="RESTRICT"), nullable=False
    )
    received_quantity: Mapped[int]   = mapped_column(Integer, nullable=False)
    batch_number:      Mapped[str]   = mapped_column(String(64), nullable=False)
    purchase_price:    Mapped[float] = mapped_column(MONEY, nullable=False)
    selling_price:     Mapped[float] = mapped_column(MONEY, nullable=False)
    expiry_date:       Mapped[date]  = mapped_column(Date, nullable=False)

    receipt: Mapped["PurchaseOrderReceipt"]  = relationship(back_populates="items")
    po_item: Mapped["PurchaseOrderItem"]     = relationship()
