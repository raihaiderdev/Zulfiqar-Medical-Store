"""
Cashier Shift service — Phase 2.

Tracks cash reconciliation per shift.

Cash flow formula:
    expected_closing = opening_cash
                     + total_cash_sales
                     - total_cash_refunds
                     - total_cash_expenses
    variance = actual_closing_cash - expected_closing

Only one shift per cashier can be OPEN at a time.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import func

from app.database.session import session_scope
from app.models.cashier_shift import CashierShift, ShiftStatus
from app.models import Sale, SaleReturn, Expense
from app.models.enums import SaleStatus
from app.security.decorators import require_permission
from app.security.session_context import current_session
from app.services import audit_service
from app.utils.exceptions import NotFoundError, ValidationError


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


@require_permission("shifts.manage")
def open_shift(opening_cash: float = 0.0, notes: Optional[str] = None) -> int:
    """
    Open a new cashier shift for the current user.
    Raises if the cashier already has an open shift.
    Returns the new shift id.
    """
    if opening_cash < 0:
        raise ValidationError("Opening cash cannot be negative.")

    with session_scope() as session:
        # Check for existing open shift
        existing = (
            session.query(CashierShift)
            .filter(
                CashierShift.cashier_id == current_session.user_id,
                CashierShift.status == ShiftStatus.OPEN,
            )
            .one_or_none()
        )
        if existing is not None:
            raise ValidationError(
                f"You already have an open shift (ID {existing.id}). "
                "Close it before opening a new one."
            )

        shift = CashierShift(
            cashier_id=current_session.user_id,
            opened_at=_utcnow(),
            status=ShiftStatus.OPEN,
            opening_cash=opening_cash,
            notes=notes,
        )
        session.add(shift)
        session.flush()

        audit_service.record(
            session, user_id=current_session.user_id,
            action="SHIFT_OPENED", entity="cashier_shifts", entity_id=shift.id,
            new_value={"opening_cash": opening_cash},
        )
        return shift.id


@require_permission("shifts.manage")
def close_shift(
    shift_id: int,
    actual_closing_cash: float,
    notes: Optional[str] = None,
) -> dict:
    """
    Close an open shift.
    Returns the shift summary including cash variance.
    """
    if actual_closing_cash < 0:
        raise ValidationError("Actual closing cash cannot be negative.")

    with session_scope() as session:
        shift = session.get(CashierShift, shift_id)
        if shift is None:
            raise NotFoundError(f"Shift {shift_id} not found.")
        if shift.cashier_id != current_session.user_id and not current_session.is_admin:
            raise ValidationError("You can only close your own shift.")
        if shift.status != ShiftStatus.OPEN:
            raise ValidationError(f"Shift {shift_id} is not open.")

        summary = _compute_shift_summary(session, shift)
        expected = summary["expected_closing_cash"]
        variance = round(actual_closing_cash - expected, 2)

        shift.status              = ShiftStatus.CLOSED
        shift.closed_at           = _utcnow()
        shift.actual_closing_cash = actual_closing_cash
        if notes:
            shift.notes = notes
        session.add(shift)

        audit_service.record(
            session, user_id=current_session.user_id,
            action="SHIFT_CLOSED", entity="cashier_shifts", entity_id=shift_id,
            new_value={
                "actual_closing_cash": actual_closing_cash,
                "expected_closing_cash": expected,
                "variance": variance,
            },
        )

    return {**summary, "actual_closing_cash": actual_closing_cash, "variance": variance}


@require_permission("shifts.manage")
def get_shift_summary(shift_id: int) -> dict:
    """Return a full summary of a shift (open or closed)."""
    with session_scope() as session:
        shift = session.get(CashierShift, shift_id)
        if shift is None:
            raise NotFoundError(f"Shift {shift_id} not found.")
        summary = _compute_shift_summary(session, shift)
        if shift.actual_closing_cash is not None:
            summary["actual_closing_cash"] = float(shift.actual_closing_cash)
            summary["variance"] = round(
                float(shift.actual_closing_cash) - summary["expected_closing_cash"], 2
            )
        return summary


@require_permission("shifts.manage")
def get_current_open_shift() -> Optional[dict]:
    """Return the current user's open shift, or None."""
    with session_scope() as session:
        shift = (
            session.query(CashierShift)
            .filter(
                CashierShift.cashier_id == current_session.user_id,
                CashierShift.status == ShiftStatus.OPEN,
            )
            .one_or_none()
        )
        if shift is None:
            return None
        return _compute_shift_summary(session, shift)


@require_permission("shifts.manage")
def list_shifts(cashier_id: Optional[int] = None, limit: int = 50) -> list[dict]:
    with session_scope() as session:
        q = session.query(CashierShift)
        if cashier_id:
            q = q.filter(CashierShift.cashier_id == cashier_id)
        shifts = q.order_by(CashierShift.opened_at.desc()).limit(limit).all()
        result = []
        for s in shifts:
            summary = _compute_shift_summary(session, s)
            if s.actual_closing_cash is not None:
                summary["actual_closing_cash"] = float(s.actual_closing_cash)
                summary["variance"] = round(
                    float(s.actual_closing_cash) - summary["expected_closing_cash"], 2
                )
            result.append(summary)
        return result


# ── Internal ──────────────────────────────────────────────────────────────

def _compute_shift_summary(session, shift: CashierShift) -> dict:
    """
    Compute expected closing cash from transactional data within the shift window.

    Cash sales = completed sales by this cashier in the shift window.
    Cash refunds = sale returns linked to those sales.
    Cash expenses = expenses recorded by this cashier in the shift window.

    Note: in this system all sales are assumed to be cash unless payment
    method is extended in a future phase.
    """
    opened_at = shift.opened_at
    closed_at = shift.closed_at or _utcnow()

    # Total sales by cashier in shift window
    from sqlalchemy import cast, Date as SADate
    cash_sales_q = (
        session.query(func.coalesce(func.sum(Sale.total), 0))
        .filter(
            Sale.cashier_id == shift.cashier_id,
            Sale.status == SaleStatus.COMPLETED,
            Sale.created_at >= opened_at,
            Sale.created_at <= closed_at,
        )
        .scalar()
    )
    cash_sales = float(cash_sales_q or 0)

    # Total expenses in shift window by same cashier
    cash_expenses_q = (
        session.query(func.coalesce(func.sum(Expense.amount), 0))
        .filter(
            Expense.user_id == shift.cashier_id,
            Expense.created_at >= opened_at,
            Expense.created_at <= closed_at,
        )
        .scalar()
    )
    cash_expenses = float(cash_expenses_q or 0)

    opening = float(shift.opening_cash)
    expected = round(opening + cash_sales - cash_expenses, 2)

    from app.models.user import User
    user = session.get(User, shift.cashier_id)
    cashier_name = user.username if user else str(shift.cashier_id)

    return {
        "shift_id":             shift.id,
        "cashier_id":           shift.cashier_id,
        "cashier_name":         cashier_name,
        "status":               shift.status.value,
        "opened_at":            shift.opened_at.isoformat(),
        "closed_at":            shift.closed_at.isoformat() if shift.closed_at else None,
        "opening_cash":         opening,
        "cash_sales":           cash_sales,
        "cash_expenses":        cash_expenses,
        "expected_closing_cash": expected,
        "notes":                shift.notes or "",
    }
