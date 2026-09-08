from __future__ import annotations

from datetime import date
from typing import Optional

from sqlalchemy import Date, ForeignKey, Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, IDMixin, TimestampMixin

MONEY = Numeric(12, 2)


class ExpenseCategory(Base, IDMixin, TimestampMixin):
    __tablename__ = "expense_categories"
    __table_args__ = (UniqueConstraint("name", name="uq_expense_category_name"),)

    name: Mapped[str] = mapped_column(String(64), nullable=False)


class Expense(Base, IDMixin, TimestampMixin):
    __tablename__ = "expenses"

    category_id: Mapped[int] = mapped_column(ForeignKey("expense_categories.id", ondelete="RESTRICT"), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(String(255))
    amount: Mapped[float] = mapped_column(MONEY, nullable=False)
    expense_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    user_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    notes: Mapped[Optional[str]] = mapped_column(String(500))

    category: Mapped["ExpenseCategory"] = relationship()
    user: Mapped[Optional["User"]] = relationship()
