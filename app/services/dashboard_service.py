"""
Dashboard KPI aggregation — lightweight version.

Performance improvements:
  - Sales/profit KPIs use direct SQL aggregates instead of loading every
    SaleItem into Python for 4 separate periods.
  - Expiry/low-stock counts use COUNT queries, not full row loads.
  - Intelligence summary is computed only when the user has the permission.
  - Stock valuation remains a single aggregate query (already fast).
"""
from __future__ import annotations

from datetime import date, timedelta

from sqlalchemy import func

from app.database.session import session_scope
from app.models import (
    Expense, Medicine, MedicineBatch, Purchase, Sale, SaleItem, User
)
from app.models.enums import SaleStatus
from app.security.decorators import require_admin


def _period_bounds(today: date) -> dict[str, tuple[date, date]]:
    week_start = today - timedelta(days=today.weekday())
    month_start = today.replace(day=1)
    year_start = today.replace(month=1, day=1)
    return {
        "today": (today, today),
        "this_week": (week_start, today),
        "this_month": (month_start, today),
        "this_year": (year_start, today),
    }


def _fast_sales_kpi(session, start: date, end: date) -> dict:
    """
    Compute revenue / profit / discount for a date range with a single
    aggregate SQL query — avoids loading every SaleItem into Python.
    """
    row = (
        session.query(
            func.coalesce(func.sum(
                SaleItem.unit_price * SaleItem.quantity - SaleItem.line_discount
            ), 0).label("revenue_items"),
            func.coalesce(func.sum(
                SaleItem.unit_cost * SaleItem.quantity
            ), 0).label("cogs"),
            func.coalesce(func.sum(SaleItem.line_discount), 0).label("item_disc"),
        )
        .join(Sale, Sale.id == SaleItem.sale_id)
        .filter(
            Sale.sale_date >= start,
            Sale.sale_date <= end,
            Sale.status == SaleStatus.COMPLETED,
        )
        .one()
    )
    revenue = float(row.revenue_items or 0)
    cogs    = float(row.cogs or 0)

    # Sale-level discount (subtract from revenue, add to total_discount)
    sale_disc_row = (
        session.query(func.coalesce(func.sum(Sale.discount_total), 0))
        .filter(
            Sale.sale_date >= start,
            Sale.sale_date <= end,
            Sale.status == SaleStatus.COMPLETED,
        )
        .scalar()
    )
    sale_level_disc = float(sale_disc_row or 0)
    item_disc       = float(row.item_disc or 0)
    extra_disc      = max(0.0, sale_level_disc - item_disc)
    revenue        -= extra_disc
    total_discount  = item_disc + extra_disc
    gross_profit    = round(revenue - cogs, 2)

    # Doctor fees for this period
    from app.models.doctor_fee import DoctorFee
    fee_row = (
        session.query(func.coalesce(func.sum(DoctorFee.amount), 0))
        .filter(
            DoctorFee.fee_date >= start,
            DoctorFee.fee_date <= end,
            DoctorFee.status == "ACTIVE",
        )
        .scalar()
    )
    doctor_fees = float(fee_row or 0)

    return {
        "sales":       round(revenue, 2),
        "profit":      gross_profit,
        "discount":    round(total_discount, 2),
        "doctor_fees": round(doctor_fees, 2),
    }


@require_admin
def admin_dashboard_kpis() -> dict:
    today  = date.today()
    cutoff = today - timedelta(days=90)   # expiry warning window

    with session_scope() as session:
        # ── Inventory counts (fast aggregates) ──────────────────────────
        total_medicines = int(
            session.query(func.count(Medicine.id))
            .filter(Medicine.is_active.is_(True))
            .scalar() or 0
        )
        total_stock_qty = int(
            session.query(func.coalesce(func.sum(MedicineBatch.quantity), 0))
            .filter(MedicineBatch.is_active.is_(True))
            .scalar() or 0
        )
        total_purchases_value = float(
            session.query(func.coalesce(func.sum(Purchase.total_cost), 0)).scalar() or 0
        )
        active_user_count = int(
            session.query(func.count(User.id))
            .filter(User.is_active.is_(True))
            .scalar() or 0
        )

        # Expired batches count
        expired_count = int(
            session.query(func.count(MedicineBatch.id))
            .filter(
                MedicineBatch.is_active.is_(True),
                MedicineBatch.quantity > 0,
                MedicineBatch.expiry_date < today,
            )
            .scalar() or 0
        )

        # Expiring soon count (within 90 days, not yet expired)
        expiring_soon_count = int(
            session.query(func.count(MedicineBatch.id))
            .filter(
                MedicineBatch.is_active.is_(True),
                MedicineBatch.quantity > 0,
                MedicineBatch.expiry_date >= today,
                MedicineBatch.expiry_date <= today + timedelta(days=90),
            )
            .scalar() or 0
        )

        # Low stock count (total qty per medicine ≤ min_stock_level)
        from sqlalchemy import case
        low_stock_count = int(
            session.query(func.count())
            .select_from(
                session.query(
                    Medicine.id,
                    func.coalesce(func.sum(
                        case((MedicineBatch.is_active == True, MedicineBatch.quantity), else_=0)  # noqa: E712
                    ), 0).label("total_qty"),
                    Medicine.min_stock_level,
                )
                .outerjoin(MedicineBatch, MedicineBatch.medicine_id == Medicine.id)
                .filter(Medicine.is_active.is_(True))
                .group_by(Medicine.id, Medicine.min_stock_level)
                .having(
                    func.coalesce(func.sum(
                        case((MedicineBatch.is_active == True, MedicineBatch.quantity), else_=0)  # noqa: E712
                    ), 0) <= Medicine.min_stock_level
                )
                .subquery()
            )
            .scalar() or 0
        )

        # Stock valuation (single aggregate — already fast)
        sv_row = session.query(
            func.coalesce(func.sum(MedicineBatch.quantity * MedicineBatch.purchase_price), 0).label("cost"),
            func.coalesce(func.sum(MedicineBatch.quantity * MedicineBatch.selling_price), 0).label("retail"),
            func.count(MedicineBatch.id).label("batch_count"),
            func.coalesce(func.sum(MedicineBatch.quantity), 0).label("total_units"),
        ).filter(
            MedicineBatch.is_active.is_(True),
            MedicineBatch.quantity > 0,
        ).one()
        cost_val   = float(sv_row.cost or 0)
        retail_val = float(sv_row.retail or 0)
        stock_valuation = {
            "batch_count":            int(sv_row.batch_count or 0),
            "total_units":            int(sv_row.total_units or 0),
            "cost_value":             round(cost_val, 2),
            "retail_value":           round(retail_val, 2),
            "potential_gross_profit": round(retail_val - cost_val, 2),
        }

        # ── Sales KPIs — one aggregate query per period ──────────────────
        periods   = _period_bounds(today)
        sales_kpis = {
            label: _fast_sales_kpi(session, start, end)
            for label, (start, end) in periods.items()
        }

    # ── Intelligence summary (permission-gated, runs outside main session) ──
    intelligence_summary = None
    from app.security.session_context import current_session as _cs
    if _cs.has_permission("stock.intelligence"):
        try:
            from app.services.inventory_intelligence_service import get_stock_intelligence_summary
            intelligence_summary = get_stock_intelligence_summary()
        except Exception:
            intelligence_summary = None  # never crash the dashboard

    return {
        "total_medicines":       total_medicines,
        "total_stock_quantity":  total_stock_qty,
        "low_stock_count":       low_stock_count,
        "expired_count":         expired_count,
        "expiring_soon_count":   expiring_soon_count,
        "total_purchases_value": total_purchases_value,
        "active_user_count":     active_user_count,
        "stock_valuation":       stock_valuation,
        "sales":                 sales_kpis,
        "intelligence":          intelligence_summary,
    }
