"""
Expense management — full CRUD for expenses and expense categories.
"""
from __future__ import annotations

from datetime import date
from typing import Optional

from app.database.session import session_scope
from app.models.expense import Expense, ExpenseCategory
from app.security.decorators import require_permission
from app.security.session_context import current_session
from app.services import audit_service
from app.utils.exceptions import ConflictError, NotFoundError, ValidationError


@require_permission("purchases.manage")
def list_categories() -> list[ExpenseCategory]:
    with session_scope() as session:
        cats = session.query(ExpenseCategory).order_by(ExpenseCategory.name).all()
        session.expunge_all()
        return cats


@require_permission("purchases.manage")
def add_category(name: str) -> int:
    name = name.strip()
    if not name:
        raise ValidationError("Category name is required.")
    with session_scope() as session:
        existing = session.query(ExpenseCategory).filter_by(name=name).one_or_none()
        if existing:
            raise ConflictError(f"Category '{name}' already exists.")
        cat = ExpenseCategory(name=name)
        session.add(cat)
        session.flush()
        return cat.id


@require_permission("purchases.manage")
def add_expense(
    *,
    category_id: int,
    amount: float,
    expense_date: date,
    description: Optional[str] = None,
    notes: Optional[str] = None,
) -> int:
    if amount <= 0:
        raise ValidationError("Expense amount must be greater than zero.")
    with session_scope() as session:
        cat = session.get(ExpenseCategory, category_id)
        if cat is None:
            raise NotFoundError(f"Expense category {category_id} not found.")
        expense = Expense(
            category_id=category_id,
            amount=amount,
            expense_date=expense_date,
            description=description,
            notes=notes,
            user_id=current_session.user_id,
        )
        session.add(expense)
        session.flush()
        audit_service.record(
            session,
            user_id=current_session.user_id,
            action="EXPENSE_ADDED",
            entity="expenses",
            entity_id=expense.id,
            new_value={"amount": amount, "category_id": category_id, "date": str(expense_date)},
        )
        return expense.id


@require_permission("purchases.manage")
def edit_expense(
    expense_id: int,
    *,
    category_id: Optional[int] = None,
    amount: Optional[float] = None,
    expense_date: Optional[date] = None,
    description: Optional[str] = None,
    notes: Optional[str] = None,
) -> None:
    with session_scope() as session:
        expense = session.get(Expense, expense_id)
        if expense is None:
            raise NotFoundError(f"Expense {expense_id} not found.")
        if category_id is not None:
            expense.category_id = category_id
        if amount is not None:
            if amount <= 0:
                raise ValidationError("Expense amount must be greater than zero.")
            expense.amount = amount
        if expense_date is not None:
            expense.expense_date = expense_date
        if description is not None:
            expense.description = description
        if notes is not None:
            expense.notes = notes
        session.add(expense)
        audit_service.record(
            session,
            user_id=current_session.user_id,
            action="EXPENSE_EDITED",
            entity="expenses",
            entity_id=expense_id,
        )


@require_permission("purchases.manage")
def delete_expense(expense_id: int) -> None:
    with session_scope() as session:
        expense = session.get(Expense, expense_id)
        if expense is None:
            raise NotFoundError(f"Expense {expense_id} not found.")
        session.delete(expense)
        audit_service.record(
            session,
            user_id=current_session.user_id,
            action="EXPENSE_DELETED",
            entity="expenses",
            entity_id=expense_id,
        )


@require_permission("purchases.manage")
def list_expenses(
    *,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    category_id: Optional[int] = None,
) -> list[dict]:
    with session_scope() as session:
        q = session.query(Expense)
        if date_from:
            q = q.filter(Expense.expense_date >= date_from)
        if date_to:
            q = q.filter(Expense.expense_date <= date_to)
        if category_id:
            q = q.filter(Expense.category_id == category_id)
        expenses = q.order_by(Expense.expense_date.desc(), Expense.id.desc()).all()
        # Eagerly load category name before session closes
        result = []
        for e in expenses:
            cat_name = e.category.name if e.category else ""
            result.append({
                "expense_id": e.id,
                "category": cat_name,
                "category_id": e.category_id,
                "description": e.description or "",
                "amount": float(e.amount),
                "date": e.expense_date.isoformat(),
                "notes": e.notes or "",
            })
        return result
