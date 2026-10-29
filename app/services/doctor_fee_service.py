"""
Doctor Fee service.

All doctor consultation fees are stored in the `doctor_fees` table,
completely separate from medicine sales, purchases, and inventory.

Workflow:
  1. Record a fee (standalone from Doctor Fees page, OR atomically via POS).
  2. List / summarise fees by date range and doctor.
  3. Get a daily collection summary for end-of-day reconciliation.
  4. Correct or void an entry (audit trail preserved).

Permission keys:
  doctor_fees.record  — create entries
  doctor_fees.view    — read / report
  doctor_fees.correct — correct or void entries
"""
from __future__ import annotations

import math
from datetime import date
from typing import Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.database.session import session_scope
from app.models.doctor_fee import DoctorFee
from app.security.decorators import require_permission
from app.security.session_context import current_session
from app.services import audit_service
from app.utils.exceptions import NotFoundError, ValidationError


# ── Shared validation ─────────────────────────────────────────────────────

def _validate_amount(amount: float) -> None:
    if not math.isfinite(amount):
        raise ValidationError("Doctor fee amount must be a finite number.")
    if amount < 0:
        raise ValidationError("Doctor fee amount cannot be negative.")
    if amount == 0:
        raise ValidationError("Doctor fee amount must be greater than zero.")


def _validate_doctor_name(name: str) -> None:
    if not name or not name.strip():
        raise ValidationError("Doctor name cannot be empty.")


def _fee_to_dict(f: DoctorFee) -> dict:
    return {
        "fee_id":           f.id,
        "fee_date":         f.fee_date.isoformat(),
        "doctor_name":      f.doctor_name,
        "amount":           float(f.amount),
        "payment_method":   f.payment_method or "",
        "patient_reference": f.patient_reference or "",
        "notes":            f.notes or "",
        "sale_reference":   f.sale_reference or "",
        "status":           f.status,
        "created_by_user_id": f.created_by_user_id,
    }


# ── Internal helper used by sales_service (no permission re-check) ────────

def _record_fee_in_session(
    session: Session,
    *,
    fee_date: date,
    doctor_name: str,
    amount: float,
    payment_method: Optional[str] = None,
    patient_reference: Optional[str] = None,
    notes: Optional[str] = None,
    sale_reference: Optional[str] = None,
    user_id: Optional[int] = None,
) -> int:
    """
    Insert a DoctorFee row inside an already-open session.
    Called by sales_service.complete_sale() so the fee and the Sale
    commit atomically. Validation is done by the caller before this point.
    """
    fee = DoctorFee(
        fee_date=fee_date,
        doctor_name=doctor_name.strip(),
        amount=amount,
        payment_method=payment_method,
        patient_reference=patient_reference,
        notes=notes,
        sale_reference=sale_reference,
        status="ACTIVE",
        created_by_user_id=user_id,
    )
    session.add(fee)
    session.flush()

    audit_service.record(
        session,
        user_id=user_id,
        action="DOCTOR_FEE_RECORDED",
        entity="doctor_fees",
        entity_id=fee.id,
        new_value={
            "fee_date":       fee_date.isoformat(),
            "doctor_name":    doctor_name,
            "amount":         amount,
            "payment_method": payment_method,
            "sale_reference": sale_reference,
        },
    )
    return fee.id


# ── Public API ────────────────────────────────────────────────────────────

@require_permission("doctor_fees.record")
def record_doctor_fee(
    *,
    fee_date: date,
    doctor_name: str,
    amount: float,
    payment_method: Optional[str] = None,
    patient_reference: Optional[str] = None,
    notes: Optional[str] = None,
    sale_reference: Optional[str] = None,
) -> int:
    """
    Record a standalone doctor fee (not attached to a POS sale).
    Returns the new fee id.
    """
    _validate_amount(amount)
    _validate_doctor_name(doctor_name)
    if fee_date > date.today():
        raise ValidationError("Fee date cannot be in the future.")

    with session_scope() as session:
        return _record_fee_in_session(
            session,
            fee_date=fee_date,
            doctor_name=doctor_name,
            amount=amount,
            payment_method=payment_method,
            patient_reference=patient_reference,
            notes=notes,
            sale_reference=sale_reference,
            user_id=current_session.user_id,
        )


@require_permission("doctor_fees.view")
def list_doctor_fees(
    *,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    doctor_name: Optional[str] = None,
    status: Optional[str] = None,
    limit: int = 200,
) -> list[dict]:
    """Return fee entries filtered by date range, doctor name, and/or status."""
    with session_scope() as session:
        q = session.query(DoctorFee)
        if date_from:
            q = q.filter(DoctorFee.fee_date >= date_from)
        if date_to:
            q = q.filter(DoctorFee.fee_date <= date_to)
        if doctor_name:
            q = q.filter(DoctorFee.doctor_name.ilike(f"%{doctor_name.strip()}%"))
        if status:
            q = q.filter(DoctorFee.status == status.upper())
        fees = q.order_by(DoctorFee.fee_date.desc(), DoctorFee.id.desc()).limit(limit).all()
        return [_fee_to_dict(f) for f in fees]


@require_permission("doctor_fees.view")
def get_doctor_fee_summary(
    *,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    doctor_name: Optional[str] = None,
) -> dict:
    """
    Aggregate summary of ACTIVE fees (voided/corrected excluded from totals).
    Returns total_fees, fee_count, by_doctor list, by_payment_method list.
    """
    with session_scope() as session:
        q = session.query(DoctorFee).filter(DoctorFee.status == "ACTIVE")
        if date_from:
            q = q.filter(DoctorFee.fee_date >= date_from)
        if date_to:
            q = q.filter(DoctorFee.fee_date <= date_to)
        if doctor_name:
            q = q.filter(DoctorFee.doctor_name.ilike(f"%{doctor_name.strip()}%"))

        fees = q.all()
        total = round(sum(float(f.amount) for f in fees), 2)

        # Per-doctor breakdown
        by_doctor: dict[str, dict] = {}
        for f in fees:
            d = by_doctor.setdefault(f.doctor_name, {"doctor_name": f.doctor_name, "total": 0.0, "count": 0})
            d["total"] = round(d["total"] + float(f.amount), 2)
            d["count"] += 1

        # Per-payment-method breakdown
        by_method: dict[str, dict] = {}
        for f in fees:
            m = f.payment_method or "Unspecified"
            d = by_method.setdefault(m, {"method": m, "total": 0.0, "count": 0})
            d["total"] = round(d["total"] + float(f.amount), 2)
            d["count"] += 1

        return {
            "total_fees":        total,
            "fee_count":         len(fees),
            "by_doctor":         sorted(by_doctor.values(), key=lambda x: x["total"], reverse=True),
            "by_payment_method": sorted(by_method.values(), key=lambda x: x["total"], reverse=True),
        }


@require_permission("doctor_fees.view")
def get_daily_fee_collection(*, fee_date: date) -> dict:
    """
    Daily collection summary for a specific date.
    Returns all fee entries for that day (all statuses) plus
    ACTIVE-only totals for reconciliation.
    """
    with session_scope() as session:
        all_fees = (
            session.query(DoctorFee)
            .filter(DoctorFee.fee_date == fee_date)
            .order_by(DoctorFee.id.asc())
            .all()
        )

        active = [f for f in all_fees if f.status == "ACTIVE"]
        total_collected = round(sum(float(f.amount) for f in active), 2)

        by_doctor: dict[str, dict] = {}
        for f in active:
            d = by_doctor.setdefault(f.doctor_name, {"doctor_name": f.doctor_name, "total": 0.0, "count": 0})
            d["total"] = round(d["total"] + float(f.amount), 2)
            d["count"] += 1

        return {
            "fee_date":        fee_date.isoformat(),
            "total_collected": total_collected,
            "fee_count":       len(active),
            "entries":         [_fee_to_dict(f) for f in all_fees],
            "by_doctor":       sorted(by_doctor.values(), key=lambda x: x["total"], reverse=True),
        }


@require_permission("doctor_fees.correct")
def correct_doctor_fee(
    *,
    fee_id: int,
    new_amount: Optional[float] = None,
    new_doctor_name: Optional[str] = None,
    new_payment_method: Optional[str] = None,
    new_notes: Optional[str] = None,
    reason: str,
) -> int:
    """
    Correct an ACTIVE doctor fee entry in place.
    Audit record captures old and new values plus the mandatory reason.
    Returns the fee_id.
    """
    if not reason or not reason.strip():
        raise ValidationError("A reason is required to correct a fee entry.")

    with session_scope() as session:
        fee = session.get(DoctorFee, fee_id)
        if fee is None:
            raise NotFoundError(f"Doctor fee {fee_id} not found.")
        if fee.status == "VOIDED":
            raise ValidationError("Cannot correct a voided fee entry.")

        old_value = {
            "amount":         float(fee.amount),
            "doctor_name":    fee.doctor_name,
            "payment_method": fee.payment_method,
            "notes":          fee.notes,
            "status":         fee.status,
        }

        if new_amount is not None:
            _validate_amount(new_amount)
            fee.amount = new_amount
        if new_doctor_name is not None:
            _validate_doctor_name(new_doctor_name)
            fee.doctor_name = new_doctor_name.strip()
        if new_payment_method is not None:
            fee.payment_method = new_payment_method
        if new_notes is not None:
            fee.notes = new_notes

        fee.status = "CORRECTED"
        session.add(fee)

        audit_service.record(
            session,
            user_id=current_session.user_id,
            action="DOCTOR_FEE_CORRECTED",
            entity="doctor_fees",
            entity_id=fee_id,
            old_value=old_value,
            new_value={
                "amount":         float(fee.amount),
                "doctor_name":    fee.doctor_name,
                "payment_method": fee.payment_method,
                "notes":          fee.notes,
                "reason":         reason.strip(),
            },
        )
        return fee_id


@require_permission("doctor_fees.correct")
def void_doctor_fee(*, fee_id: int, reason: str) -> None:
    """
    Void a doctor fee entry. Voided entries are excluded from totals
    but kept in the DB for the audit trail.
    """
    if not reason or not reason.strip():
        raise ValidationError("A reason is required to void a fee entry.")

    with session_scope() as session:
        fee = session.get(DoctorFee, fee_id)
        if fee is None:
            raise NotFoundError(f"Doctor fee {fee_id} not found.")
        if fee.status == "VOIDED":
            raise ValidationError("Fee is already voided.")

        old_value = {
            "fee_date":       fee.fee_date.isoformat(),
            "doctor_name":    fee.doctor_name,
            "amount":         float(fee.amount),
            "payment_method": fee.payment_method,
            "status":         fee.status,
        }
        fee.status = "VOIDED"
        session.add(fee)

        audit_service.record(
            session,
            user_id=current_session.user_id,
            action="DOCTOR_FEE_VOIDED",
            entity="doctor_fees",
            entity_id=fee_id,
            old_value=old_value,
            new_value={"reason": reason.strip()},
        )
