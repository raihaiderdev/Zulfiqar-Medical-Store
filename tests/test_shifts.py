"""
Regression tests for shift_service — TASK-03.

Each test that opens a shift closes it before returning so state does not
bleed into subsequent tests (the service allows only ONE open shift per
cashier at a time).
"""
from __future__ import annotations

import pytest

from app.database.session import session_scope
from app.models.cashier_shift import CashierShift, ShiftStatus
from app.services import auth_service, shift_service, user_service
from app.utils.exceptions import AuthorizationError, ValidationError


@pytest.fixture(autouse=True)
def _admin_session(admin_logged_in):
    yield


def test_open_shift_creates_open_row():
    shift_id = shift_service.open_shift(opening_cash=500.0)
    assert isinstance(shift_id, int)
    with session_scope() as session:
        shift = session.get(CashierShift, shift_id)
        assert shift is not None
        assert shift.status == ShiftStatus.OPEN
        assert float(shift.opening_cash) == 500.0
    shift_service.close_shift(shift_id=shift_id, actual_closing_cash=500.0)


def test_duplicate_open_shift_rejected():
    shift_id = shift_service.open_shift(opening_cash=100.0)
    with pytest.raises(ValidationError, match="already have an open shift"):
        shift_service.open_shift(opening_cash=200.0)
    shift_service.close_shift(shift_id=shift_id, actual_closing_cash=100.0)


def test_close_shift_transitions_to_closed():
    shift_id = shift_service.open_shift(opening_cash=1000.0)
    summary = shift_service.close_shift(shift_id=shift_id, actual_closing_cash=1000.0)
    with session_scope() as session:
        shift = session.get(CashierShift, shift_id)
        assert shift.status == ShiftStatus.CLOSED
    assert "variance" in summary
    assert summary["status"] == "CLOSED"


def test_close_shift_variance_computed_correctly():
    shift_id = shift_service.open_shift(opening_cash=500.0)
    summary = shift_service.close_shift(shift_id=shift_id, actual_closing_cash=480.0)
    assert summary["expected_closing_cash"] == 500.0
    assert abs(summary["variance"] - (-20.0)) < 0.01


def test_get_shift_summary_returns_correct_fields():
    shift_id = shift_service.open_shift(opening_cash=200.0)
    summary = shift_service.get_shift_summary(shift_id)
    for field in ["shift_id", "cashier_id", "status", "opening_cash", "expected_closing_cash"]:
        assert field in summary, f"Missing field: {field}"
    shift_service.close_shift(shift_id=shift_id, actual_closing_cash=200.0)


def test_open_shift_negative_cash_rejected():
    with pytest.raises(ValidationError, match="negative"):
        shift_service.open_shift(opening_cash=-100.0)


def test_open_shift_without_permission_rejected():
    user_service.create_user(
        username="no_shift_user",
        password="NoShiftPass123!",
        permission_keys=["sales.create"],
    )
    auth_service.logout()
    auth_service.login("no_shift_user", "NoShiftPass123!")
    with pytest.raises(AuthorizationError):
        shift_service.open_shift(opening_cash=0.0)
    auth_service.logout()
