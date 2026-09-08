from __future__ import annotations

from typing import Optional

from sqlalchemy import Boolean, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, IDMixin, TimestampMixin


class Supplier(Base, IDMixin, TimestampMixin):
    __tablename__ = "suppliers"
    __table_args__ = (UniqueConstraint("name", "phone", name="uq_supplier_name_phone"),)

    name: Mapped[str] = mapped_column(String(180), nullable=False, index=True)
    company: Mapped[Optional[str]] = mapped_column(String(180))
    phone: Mapped[Optional[str]] = mapped_column(String(32))
    email: Mapped[Optional[str]] = mapped_column(String(180))
    address: Mapped[Optional[str]] = mapped_column(String(255))
    tax_registration_number: Mapped[Optional[str]] = mapped_column(String(64))
    notes: Mapped[Optional[str]] = mapped_column(String(500))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class Customer(Base, IDMixin, TimestampMixin):
    __tablename__ = "customers"

    name: Mapped[str] = mapped_column(String(180), nullable=False, index=True)
    phone: Mapped[Optional[str]] = mapped_column(String(32), index=True)
    address: Mapped[Optional[str]] = mapped_column(String(255))
    email: Mapped[Optional[str]] = mapped_column(String(180))
    notes: Mapped[Optional[str]] = mapped_column(String(500))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
