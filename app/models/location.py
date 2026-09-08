from __future__ import annotations

from typing import List, Optional

from sqlalchemy import ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, IDMixin, TimestampMixin


class Wardrobe(Base, IDMixin, TimestampMixin):
    __tablename__ = "wardrobes"
    __table_args__ = (UniqueConstraint("code", name="uq_wardrobe_code"),)

    code: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    description: Mapped[Optional[str]] = mapped_column(String(255))

    racks: Mapped[List["Rack"]] = relationship(back_populates="wardrobe", cascade="all, delete-orphan")


class Rack(Base, IDMixin, TimestampMixin):
    __tablename__ = "racks"
    __table_args__ = (UniqueConstraint("wardrobe_id", "code", name="uq_rack_code_per_wardrobe"),)

    wardrobe_id: Mapped[int] = mapped_column(ForeignKey("wardrobes.id", ondelete="CASCADE"), nullable=False)
    code: Mapped[str] = mapped_column(String(32), nullable=False)

    wardrobe: Mapped["Wardrobe"] = relationship(back_populates="racks")
    shelves: Mapped[List["Shelf"]] = relationship(back_populates="rack", cascade="all, delete-orphan")


class Shelf(Base, IDMixin, TimestampMixin):
    __tablename__ = "shelves"
    __table_args__ = (UniqueConstraint("rack_id", "code", name="uq_shelf_code_per_rack"),)

    rack_id: Mapped[int] = mapped_column(ForeignKey("racks.id", ondelete="CASCADE"), nullable=False)
    code: Mapped[str] = mapped_column(String(32), nullable=False)

    rack: Mapped["Rack"] = relationship(back_populates="shelves")

    @property
    def full_location(self) -> str:
        return f"{self.rack.wardrobe.code} / {self.rack.code} / {self.code}"
