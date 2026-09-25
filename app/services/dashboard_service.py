"""
Dashboard KPI aggregation (Phase 1 §4 Admin Dashboard, §23). Pulls
together numbers from several services/reports into the single payload
the Admin dashboard screen needs — kept as one call so the UI doesn't
have to orchestrate a dozen separate queries itself.
"""
from __future__ import annotations

from datetime import date, timedelta

from sqlalchemy import func

from app.database.session import session_scope
from app.models import Medicine, MedicineBatch, Purchase, Sale, User
from app.models.enums import SaleStatus
from app.reports.report_engine import sales_and_profit_report, stock_valuation_report
from app.security.decorators import require_admin
from app.services.medicine_service import expiry_report, low_stock_report


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


@require_admin
def admin_dashboard_kpis() -> dict:
    today = date.today()
    periods = _period_bounds(today)

    with session_scope() as session:
        total_medicines = session.query(func.count(Medicine.id)).filter(Medicine.is_active.is_(True)).scalar()
        total_stock_qty = (
            session.query(func.coalesce(func.sum(MedicineBatch.quantity), 0))
            .filter(MedicineBatch.is_active.is_(True))
            .scalar()
        )
        total_purchases_value = session.query(func.coalesce(func.sum(Purchase.total_cost), 0)).scalar()
        active_user_count = session.query(func.count(User.id)).filter(User.is_active.is_(True)).scalar()

    expiry = expiry_report(warning_days=90)
    low_stock = low_stock_report()
    stock_valuation = stock_valuation_report()

    sales_kpis = {}
    for label, (start, end) in periods.items():
        financials = sales_and_profit_report(start, end)
        sales_kpis[label] = {
            "sales": financials.revenue,
            "profit": financials.gross_profit,
            "discount": financials.total_discount,
        }

    # ── Phase 1: intelligence summary (only if user has stock.intelligence) ──
    intelligence_summary = None
    from app.security.session_context import current_session as _cs
    if _cs.has_permission("stock.intelligence"):
        try:
            from app.services.inventory_intelligence_service import (
                get_stock_intelligence_summary,
            )
            intelligence_summary = get_stock_intelligence_summary()
        except Exception:
            intelligence_summary = None   # never crash the dashboard

    return {
        "total_medicines":       int(total_medicines or 0),
        "total_stock_quantity":  int(total_stock_qty or 0),
        "low_stock_count":       len(low_stock),
        "expired_count":         len(expiry["expired"]),
        "expiring_soon_count":   len(expiry["expiring_soon"]),
        "total_purchases_value": float(total_purchases_value or 0),
        "active_user_count":     int(active_user_count or 0),
        "stock_valuation":       stock_valuation,
        "sales":                 sales_kpis,
        "intelligence":          intelligence_summary,
    }
