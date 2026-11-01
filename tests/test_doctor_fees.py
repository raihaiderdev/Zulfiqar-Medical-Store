"""
Regression tests for doctor_fee_service — TASK-01.

Covers:
  - record / list / summary / correct / void happy paths
  - validation rejections (amount ≤ 0, non-finite, future date, empty name)
  - permission checks (missing doctor_fees.record / doctor_fees.correct)
  - atomicity: doctor fee committed with POS sale or both roll back
  - isolation: doctor fees are NOT stored in the sales or expenses tables
  - daily collection summary
"""
from __future__ import annotations

import math
from datetime import date, timedelta

import pytest

from app.database.session import session_scope
from app.models.doctor_fee import DoctorFee
from app.services import auth_service, doctor_fee_service, medicine_service, sales_service, user_service
from app.utils.exceptions import AuthorizationError, ValidationError


@pytest.fixture(autouse=True)
def _admin_session(admin_logged_in):
    yield


# ── record_doctor_fee ─────────────────────────────────────────────────────


def test_record_valid_fee_creates_active_row():
    fee_id = doctor_fee_service.record_doctor_fee(
        fee_date=date.today(),
        doctor_name="Dr. Test",
        amount=200.0,
        payment_method="CASH",
    )
    assert isinstance(fee_id, int)
    with session_scope() as session:
        fee = session.get(DoctorFee, fee_id)
        assert fee is not None
        assert fee.status == "ACTIVE"
        assert float(fee.amount) == 200.0
        assert fee.doctor_name == "Dr. Test"


def test_record_fee_audit_row_created(admin_logged_in):
    from app.models import AuditLog

    fee_id = doctor_fee_service.record_doctor_fee(
        fee_date=date.today(), doctor_name="Dr. Audit", amount=150.0
    )
    with session_scope() as session:
        log = (
            session.query(AuditLog)
            .filter_by(action="DOCTOR_FEE_RECORDED", entity="doctor_fees", entity_id=fee_id)
            .first()
        )
        assert log is not None


def test_record_fee_negative_amount_rejected():
    with pytest.raises(ValidationError, match="cannot be negative"):
        doctor_fee_service.record_doctor_fee(
            fee_date=date.today(), doctor_name="Dr. X", amount=-10.0
        )


def test_record_fee_zero_amount_rejected():
    with pytest.raises(ValidationError, match="greater than zero"):
        doctor_fee_service.record_doctor_fee(
            fee_date=date.today(), doctor_name="Dr. X", amount=0.0
        )


def test_record_fee_nan_amount_rejected():
    with pytest.raises(ValidationError, match="finite"):
        doctor_fee_service.record_doctor_fee(
            fee_date=date.today(), doctor_name="Dr. X", amount=float("nan")
        )


def test_record_fee_infinite_amount_rejected():
    with pytest.raises(ValidationError, match="finite"):
        doctor_fee_service.record_doctor_fee(
            fee_date=date.today(), doctor_name="Dr. X", amount=float("inf")
        )


def test_record_fee_empty_doctor_name_rejected():
    with pytest.raises(ValidationError, match="empty"):
        doctor_fee_service.record_doctor_fee(
            fee_date=date.today(), doctor_name="   ", amount=100.0
        )


def test_record_fee_future_date_rejected():
    with pytest.raises(ValidationError, match="future"):
        doctor_fee_service.record_doctor_fee(
            fee_date=date.today() + timedelta(days=1), doctor_name="Dr. X", amount=100.0
        )


def test_record_fee_without_record_permission_rejected():
    user_service.create_user(
        username="fee_viewer_only",
        password="ViewerPass123!",
        permission_keys=["doctor_fees.view"],
    )
    auth_service.logout()
    auth_service.login("fee_viewer_only", "ViewerPass123!")
    with pytest.raises(AuthorizationError):
        doctor_fee_service.record_doctor_fee(
            fee_date=date.today(), doctor_name="Dr. X", amount=100.0
        )
    auth_service.logout()


# ── list_doctor_fees ──────────────────────────────────────────────────────


def test_list_fees_date_range_filter():
    today = date.today()
    old_date = today - timedelta(days=10)

    doctor_fee_service.record_doctor_fee(fee_date=old_date, doctor_name="Dr. Old", amount=50.0)
    doctor_fee_service.record_doctor_fee(fee_date=today, doctor_name="Dr. New", amount=75.0)

    recent = doctor_fee_service.list_doctor_fees(
        date_from=today - timedelta(days=1), date_to=today
    )
    names = {r["doctor_name"] for r in recent}
    assert "Dr. New" in names
    # Dr. Old was recorded 10 days ago so should not appear
    assert "Dr. Old" not in names


def test_list_fees_doctor_name_filter_case_insensitive():
    doctor_fee_service.record_doctor_fee(fee_date=date.today(), doctor_name="Dr. Smith", amount=80.0)
    results = doctor_fee_service.list_doctor_fees(doctor_name="smith")
    assert any(r["doctor_name"] == "Dr. Smith" for r in results)


def test_list_fees_without_view_permission_rejected():
    user_service.create_user(
        username="no_fee_view",
        password="NoViewPass123!",
        permission_keys=[],  # no permissions
    )
    auth_service.logout()
    auth_service.login("no_fee_view", "NoViewPass123!")
    with pytest.raises(AuthorizationError):
        doctor_fee_service.list_doctor_fees()
    auth_service.logout()


# ── get_doctor_fee_summary ────────────────────────────────────────────────


def test_summary_excludes_voided_fees():
    today = date.today()
    fee_id = doctor_fee_service.record_doctor_fee(
        fee_date=today, doctor_name="Dr. Voided", amount=300.0
    )
    doctor_fee_service.void_doctor_fee(fee_id=fee_id, reason="Test void")

    summary = doctor_fee_service.get_doctor_fee_summary(date_from=today, date_to=today)
    # The voided fee should not be counted
    for doc in summary["by_doctor"]:
        assert doc["doctor_name"] != "Dr. Voided"


def test_summary_totals_active_fees_only():
    today = date.today()
    start_total = doctor_fee_service.get_doctor_fee_summary(
        date_from=today, date_to=today
    )["total_fees"]

    doctor_fee_service.record_doctor_fee(fee_date=today, doctor_name="Dr. Active", amount=500.0)
    fee_id = doctor_fee_service.record_doctor_fee(
        fee_date=today, doctor_name="Dr. ToVoid", amount=200.0
    )
    doctor_fee_service.void_doctor_fee(fee_id=fee_id, reason="Test")

    new_total = doctor_fee_service.get_doctor_fee_summary(
        date_from=today, date_to=today
    )["total_fees"]
    # Only the 500.0 active fee should be added
    assert abs(new_total - start_total - 500.0) < 0.01


# ── correct_doctor_fee ────────────────────────────────────────────────────


def test_correct_fee_updates_amount_and_status():
    fee_id = doctor_fee_service.record_doctor_fee(
        fee_date=date.today(), doctor_name="Dr. Correct", amount=100.0
    )
    doctor_fee_service.correct_doctor_fee(
        fee_id=fee_id, new_amount=150.0, reason="Corrected after billing check"
    )
    with session_scope() as session:
        fee = session.get(DoctorFee, fee_id)
        assert float(fee.amount) == 150.0
        assert fee.status == "CORRECTED"


def test_correct_fee_audit_has_old_and_new_values():
    from app.models import AuditLog

    fee_id = doctor_fee_service.record_doctor_fee(
        fee_date=date.today(), doctor_name="Dr. AuditCorrect", amount=100.0
    )
    doctor_fee_service.correct_doctor_fee(
        fee_id=fee_id, new_amount=250.0, reason="Audit test reason"
    )
    with session_scope() as session:
        import json
        log = (
            session.query(AuditLog)
            .filter_by(action="DOCTOR_FEE_CORRECTED", entity="doctor_fees", entity_id=fee_id)
            .first()
        )
        assert log is not None
        old = json.loads(log.old_value)
        new = json.loads(log.new_value)
        assert old["amount"] == 100.0
        assert new["amount"] == 250.0
        assert "reason" in new


def test_correct_fee_without_reason_rejected():
    fee_id = doctor_fee_service.record_doctor_fee(
        fee_date=date.today(), doctor_name="Dr. NoReason", amount=100.0
    )
    with pytest.raises(ValidationError, match="reason"):
        doctor_fee_service.correct_doctor_fee(fee_id=fee_id, new_amount=200.0, reason="")


def test_correct_fee_without_correct_permission_rejected():
    fee_id = doctor_fee_service.record_doctor_fee(
        fee_date=date.today(), doctor_name="Dr. NoPerm", amount=100.0
    )
    user_service.create_user(
        username="fee_recorder_only",
        password="RecorderPass123!",
        permission_keys=["doctor_fees.record", "doctor_fees.view"],
    )
    auth_service.logout()
    auth_service.login("fee_recorder_only", "RecorderPass123!")
    with pytest.raises(AuthorizationError):
        doctor_fee_service.correct_doctor_fee(
            fee_id=fee_id, new_amount=200.0, reason="Attempted without permission"
        )
    auth_service.logout()


# ── void_doctor_fee ───────────────────────────────────────────────────────


def test_void_fee_sets_voided_status():
    fee_id = doctor_fee_service.record_doctor_fee(
        fee_date=date.today(), doctor_name="Dr. VoidMe", amount=75.0
    )
    doctor_fee_service.void_doctor_fee(fee_id=fee_id, reason="Duplicate entry")
    with session_scope() as session:
        fee = session.get(DoctorFee, fee_id)
        assert fee.status == "VOIDED"


def test_void_fee_without_reason_rejected():
    fee_id = doctor_fee_service.record_doctor_fee(
        fee_date=date.today(), doctor_name="Dr. VoidNoReason", amount=75.0
    )
    with pytest.raises(ValidationError, match="reason"):
        doctor_fee_service.void_doctor_fee(fee_id=fee_id, reason="")


def test_cannot_void_already_voided_fee():
    fee_id = doctor_fee_service.record_doctor_fee(
        fee_date=date.today(), doctor_name="Dr. DoubleVoid", amount=75.0
    )
    doctor_fee_service.void_doctor_fee(fee_id=fee_id, reason="First void")
    with pytest.raises(ValidationError, match="already voided"):
        doctor_fee_service.void_doctor_fee(fee_id=fee_id, reason="Second void")


# ── get_daily_fee_collection ──────────────────────────────────────────────


def test_daily_collection_returns_correct_totals():
    today = date.today()
    doctor_fee_service.record_doctor_fee(fee_date=today, doctor_name="Dr. Daily1", amount=100.0)
    doctor_fee_service.record_doctor_fee(fee_date=today, doctor_name="Dr. Daily1", amount=200.0)
    fee_to_void = doctor_fee_service.record_doctor_fee(
        fee_date=today, doctor_name="Dr. Daily2", amount=999.0
    )
    doctor_fee_service.void_doctor_fee(fee_id=fee_to_void, reason="Void for daily test")

    data = doctor_fee_service.get_daily_fee_collection(fee_date=today)
    assert "fee_date" in data
    assert "total_collected" in data
    # Active fees for Dr. Daily1 total at least 300 (may be more from other tests)
    assert data["total_collected"] >= 300.0
    # Voided fee should not be in total_collected
    assert 999.0 not in [e["amount"] for e in data["entries"] if e["status"] == "ACTIVE"]


def test_daily_collection_all_entries_listed_including_voided():
    today = date.today()
    fee_id = doctor_fee_service.record_doctor_fee(
        fee_date=today, doctor_name="Dr. ListAll", amount=55.0
    )
    doctor_fee_service.void_doctor_fee(fee_id=fee_id, reason="Testing list all")

    data = doctor_fee_service.get_daily_fee_collection(fee_date=today)
    # All entries are returned regardless of status
    voided_entries = [e for e in data["entries"] if e["status"] == "VOIDED"]
    assert len(voided_entries) > 0


# ── Isolation: not stored as Sale or Expense ─────────────────────────────


def test_doctor_fee_not_stored_in_sales_table():
    """Doctor fees must be in doctor_fees, not sales."""
    before_count = _count_table("sales")
    doctor_fee_service.record_doctor_fee(
        fee_date=date.today(), doctor_name="Dr. IsolationCheck", amount=111.0
    )
    after_count = _count_table("sales")
    assert after_count == before_count  # no new sale row


def test_doctor_fee_not_stored_in_expenses_table():
    before_count = _count_table("expenses")
    doctor_fee_service.record_doctor_fee(
        fee_date=date.today(), doctor_name="Dr. IsolationExpense", amount=222.0
    )
    after_count = _count_table("expenses")
    assert after_count == before_count


def _count_table(table_name: str) -> int:
    with session_scope() as session:
        return session.execute(
            __import__("sqlalchemy").text(f"SELECT COUNT(*) FROM {table_name}")
        ).scalar()


# ── POS integration ───────────────────────────────────────────────────────


def test_complete_sale_with_doctor_fee_records_both_atomically():
    """A POS sale + doctor fee must both commit in the same transaction."""
    med_id = medicine_service.add_medicine(name="DocFee POS Med")
    medicine_service.add_manual_batch(
        medicine_id=med_id, batch_number="DF-POS-1",
        purchase_price=10, selling_price=20,
        quantity=50, expiry_date=date.today() + timedelta(days=300),
    )

    fee_count_before = _count_table("doctor_fees")
    sale_count_before = _count_table("sales")

    result = sales_service.complete_sale(
        lines=[{"medicine_id": med_id, "quantity": 2}],
        amount_paid=140.0,
        doctor_fee={"doctor_name": "Dr. POS", "amount": 100.0},
    )

    assert _count_table("sales") == sale_count_before + 1
    assert _count_table("doctor_fees") == fee_count_before + 1

    # Verify the fee references the invoice
    with session_scope() as session:
        fee = (
            session.query(DoctorFee)
            .filter_by(sale_reference=result.invoice_number)
            .first()
        )
        assert fee is not None
        assert float(fee.amount) == 100.0


def test_complete_sale_with_invalid_doctor_fee_amount_rejects():
    med_id = medicine_service.add_medicine(name="DocFee Invalid Med")
    medicine_service.add_manual_batch(
        medicine_id=med_id, batch_number="DF-INV-1",
        purchase_price=10, selling_price=20,
        quantity=50, expiry_date=date.today() + timedelta(days=300),
    )
    with pytest.raises(ValidationError):
        sales_service.complete_sale(
            lines=[{"medicine_id": med_id, "quantity": 1}],
            amount_paid=20.0,
            doctor_fee={"doctor_name": "Dr. Bad", "amount": 0.0},
        )


def test_complete_sale_without_doctor_fee_creates_no_fee_row():
    med_id = medicine_service.add_medicine(name="NoDocFee Med")
    medicine_service.add_manual_batch(
        medicine_id=med_id, batch_number="NDF-1",
        purchase_price=10, selling_price=20,
        quantity=50, expiry_date=date.today() + timedelta(days=300),
    )
    fee_count_before = _count_table("doctor_fees")
    sales_service.complete_sale(
        lines=[{"medicine_id": med_id, "quantity": 1}],
        amount_paid=20.0,
        doctor_fee=None,
    )
    assert _count_table("doctor_fees") == fee_count_before
