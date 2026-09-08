from __future__ import annotations

from typing import List, Optional

from sqlalchemy import Boolean, Enum, ForeignKey, Index, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, IDMixin, TimestampMixin
from app.models.enums import DosageForm


class Category(Base, IDMixin, TimestampMixin):
    __tablename__ = "categories"
    __table_args__ = (UniqueConstraint("name", name="uq_category_name"),)

    name: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    description: Mapped[Optional[str]] = mapped_column(String(255))


class Manufacturer(Base, IDMixin, TimestampMixin):
    __tablename__ = "manufacturers"
    __table_args__ = (UniqueConstraint("name", name="uq_manufacturer_name"),)

    name: Mapped[str] = mapped_column(String(128), nullable=False, index=True)


class Medicine(Base, IDMixin, TimestampMixin):
    __tablename__ = "medicines"
    __table_args__ = (
        UniqueConstraint("barcode", name="uq_medicine_barcode"),
        Index("ix_medicine_name_formula", "name", "generic_formula"),
    )

    name: Mapped[str] = mapped_column(String(180), nullable=False, index=True)
    generic_formula: Mapped[Optional[str]] = mapped_column(String(180), index=True)
    brand_name: Mapped[Optional[str]] = mapped_column(String(180))
    category_id: Mapped[Optional[int]] = mapped_column(ForeignKey("categories.id", ondelete="SET NULL"))
    manufacturer_id: Mapped[Optional[int]] = mapped_column(ForeignKey("manufacturers.id", ondelete="SET NULL"))
    default_supplier_id: Mapped[Optional[int]] = mapped_column(ForeignKey("suppliers.id", ondelete="SET NULL"))

    dosage_form: Mapped[DosageForm] = mapped_column(
        Enum(DosageForm, native_enum=False, length=20), default=DosageForm.TABLET, nullable=False
    )
    strength: Mapped[Optional[str]] = mapped_column(String(64))
    pack_size: Mapped[Optional[str]] = mapped_column(String(64))
    unit: Mapped[Optional[str]] = mapped_column(String(32))   # legacy / display alias
    # F10 — unit-based pricing
    base_unit: Mapped[Optional[str]] = mapped_column(String(32))   # e.g. "Tablet", "mL"
    pack_unit: Mapped[Optional[str]] = mapped_column(String(32))   # e.g. "Strip", "Box"
    units_per_pack: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    tax_percent: Mapped[Optional[float]] = mapped_column(default=0.0)

    barcode: Mapped[Optional[str]] = mapped_column(String(64), index=True)
    min_stock_level: Mapped[int] = mapped_column(Integer, default=10, nullable=False)
    reorder_level: Mapped[int] = mapped_column(Integer, default=20, nullable=False)

    notes: Mapped[Optional[str]] = mapped_column(String(500))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    category: Mapped[Optional["Category"]] = relationship()
    manufacturer: Mapped[Optional["Manufacturer"]] = relationship()
    default_supplier: Mapped[Optional["Supplier"]] = relationship(foreign_keys=[default_supplier_id])
    # passive_deletes=True: let the DB-level ON DELETE CASCADE (declared on
    # MedicineBatch.medicine_id) handle removal of batches instead of the
    # ORM trying to NULL out the (NOT NULL) FK column first.
    batches: Mapped[List["MedicineBatch"]] = relationship(back_populates="medicine", passive_deletes=True)

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Medicine id={self.id} name={self.name!r}>"
