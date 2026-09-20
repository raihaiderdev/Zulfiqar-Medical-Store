"""
Reporting engine (Phase 1 §21, §22, §46). Every report is computed from
the transactional tables — `report_snapshots` is only an optional,
explicitly-created cache for a *closed* period (see `close_month()`),
never the source of truth.

Revenue/COGS/Profit definitions (Phase 1 §46):
    Revenue      = sum of completed sale line totals (after discount)
    COGS         = sum of (unit_cost * quantity) for those same lines
    Gross Profit = Revenue - COGS
    Net Profit   = Gross Profit - Expenses
Cancelled sales and returned quantities are excluded from "completed"
totals rather than netted silently into revenue.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date
from typing import Optional

from sqlalchemy import func

from app.database.session import session_scope
from app.models import Expense, ReportSnapshot, Sale, SaleItem, SaleReturnItem
from app.models.enums import SaleStatus
from app.security.decorators import require_permission, require_admin


@dataclass
class PeriodFinancials:
    period_start: date
    period_end: date
    revenue: float
    cogs: float
    gross_profit: float
    expenses: float
    net_profit: float
    returned_units: int
    total_discount: float = 0.0     # total discount given to customers


def _returned_quantity_by_sale_item(session, sale_item_ids: list[int]) -> dict[int, int]:
    if not sale_item_ids:
        return {}
    rows = (
        session.query(SaleReturnItem.sale_item_id, func.sum(SaleReturnItem.quantity))
        .filter(SaleReturnItem.sale_item_id.in_(sale_item_ids))
        .group_by(SaleReturnItem.sale_item_id)
        .all()
    )
    return {sale_item_id: qty for sale_item_id, qty in rows}


@require_permission("reports.view")
def sales_and_profit_report(period_start: date, period_end: date) -> PeriodFinancials:
    """
    Computes revenue/COGS/gross profit for [period_start, period_end]
    (inclusive), counting only COMPLETED sales and netting out returned
    units AND all discounts (both item-level line_discount AND sale-level
    discount_total) so revenue is never over-reported.
    """
    with session_scope() as session:
        # Fetch all completed sales in range (with items)
        from sqlalchemy.orm import selectinload as _sel
        sales = (
            session.query(Sale)
            .options(_sel(Sale.items))
            .filter(
                Sale.sale_date >= period_start,
                Sale.sale_date <= period_end,
                Sale.status == SaleStatus.COMPLETED,
            )
            .all()
        )

        sale_item_ids = [item.id for s in sales for item in s.items]
        returned_by_item = _returned_quantity_by_sale_item(session, sale_item_ids)

        revenue = 0.0
        cogs = 0.0
        returned_units_total = 0
        total_discount = 0.0

        for sale in sales:
            # Sum of item-level line_discounts on this sale
            item_disc_sum = sum(float(item.line_discount) for item in sale.items)
            # Sale-level discount not already distributed to items
            sale_level_extra_disc = max(0.0, float(sale.discount_total) - item_disc_sum)

            for item in sale.items:
                returned_qty = returned_by_item.get(item.id, 0)
                returned_units_total += returned_qty
                net_qty = max(0, item.quantity - returned_qty)
                proportion = (net_qty / item.quantity) if item.quantity else 0
                line_discount = float(item.line_discount) * proportion
                revenue += float(item.unit_price) * net_qty - line_discount
                cogs += float(item.unit_cost) * net_qty
                total_discount += line_discount

            # Deduct the undistributed sale-level discount from revenue
            # (proportionally scaled if some items were returned)
            if sale_level_extra_disc > 0 and sale.items:
                total_sold = sum(item.quantity for item in sale.items)
                total_returned = sum(returned_by_item.get(item.id, 0) for item in sale.items)
                if total_sold > 0:
                    net_proportion = max(0.0, (total_sold - total_returned) / total_sold)
                    applied_sale_disc = sale_level_extra_disc * net_proportion
                    revenue -= applied_sale_disc
                    total_discount += applied_sale_disc

        expenses_total = (
            session.query(func.coalesce(func.sum(Expense.amount), 0))
            .filter(Expense.expense_date >= period_start, Expense.expense_date <= period_end)
            .scalar()
        )
        expenses_total = float(expenses_total or 0)

        gross_profit = round(revenue - cogs, 2)
        net_profit = round(gross_profit - expenses_total, 2)

        return PeriodFinancials(
            period_start=period_start,
            period_end=period_end,
            revenue=round(revenue, 2),
            cogs=round(cogs, 2),
            gross_profit=gross_profit,
            expenses=round(expenses_total, 2),
            net_profit=net_profit,
            returned_units=returned_units_total,
            total_discount=round(total_discount, 2),
        )


@require_permission("reports.view")
def best_selling_medicines(period_start: date, period_end: date, limit: int = 10) -> list[dict]:
    with session_scope() as session:
        from app.models import Medicine, MedicineBatch

        rows = (
            session.query(
                Medicine.id,
                Medicine.name,
                func.sum(SaleItem.quantity).label("units_sold"),
                func.sum(SaleItem.unit_price * SaleItem.quantity - SaleItem.line_discount).label("revenue"),
                func.sum((SaleItem.unit_price - SaleItem.unit_cost) * SaleItem.quantity - SaleItem.line_discount).label(
                    "profit"
                ),
            )
            .join(MedicineBatch, MedicineBatch.id == SaleItem.batch_id)
            .join(Medicine, Medicine.id == MedicineBatch.medicine_id)
            .join(Sale, Sale.id == SaleItem.sale_id)
            .filter(Sale.sale_date >= period_start, Sale.sale_date <= period_end, Sale.status == SaleStatus.COMPLETED)
            .group_by(Medicine.id, Medicine.name)
            .order_by(func.sum(SaleItem.quantity).desc())
            .limit(limit)
            .all()
        )
        return [
            {"medicine_id": r[0], "name": r[1], "units_sold": int(r[2]), "revenue": float(r[3]), "profit": float(r[4])}
            for r in rows
        ]


@require_permission("reports.view")
def stock_valuation_report() -> dict:
    """Current inventory value at cost and at selling price, across all
    active, in-stock batches."""
    with session_scope() as session:
        from app.models import MedicineBatch

        batches = session.query(MedicineBatch).filter(MedicineBatch.is_active.is_(True), MedicineBatch.quantity > 0).all()
        cost_value = sum(float(b.purchase_price) * b.quantity for b in batches)
        retail_value = sum(float(b.selling_price) * b.quantity for b in batches)
        return {
            "batch_count": len(batches),
            "total_units": sum(b.quantity for b in batches),
            "cost_value": round(cost_value, 2),
            "retail_value": round(retail_value, 2),
            "potential_gross_profit": round(retail_value - cost_value, 2),
        }


@require_permission("reports.view")
@require_admin
def close_month(year: int, month: int, closed_by_user_id: Optional[int] = None) -> dict:
    """
    Explicit "close the month" action (Phase 1 §22, §M.4): computes the
    period's financials and caches them as an immutable snapshot for fast
    future lookups. Does NOT prevent recomputing the same figures from
    live data later — it's a read cache, not the source of truth. Closing
    twice overwrites the snapshot with a freshly recomputed value rather
    than silently reusing stale numbers.
    """
    from datetime import timedelta

    period_start = date(year, month, 1)
    period_end = date(year + 1, 1, 1) if month == 12 else date(year, month + 1, 1)
    period_end = period_end - timedelta(days=1)

    financials = sales_and_profit_report(period_start, period_end)
    period_key = f"{year:04d}-{month:02d}"
    payload = {
        "revenue": financials.revenue,
        "cogs": financials.cogs,
        "gross_profit": financials.gross_profit,
        "expenses": financials.expenses,
        "net_profit": financials.net_profit,
        "returned_units": financials.returned_units,
    }

    with session_scope() as session:
        existing = (
            session.query(ReportSnapshot)
            .filter_by(period_key=period_key, report_type="monthly_pnl")
            .one_or_none()
        )
        if existing:
            existing.payload_json = json.dumps(payload)
            existing.closed_by_user_id = closed_by_user_id
            session.add(existing)
        else:
            session.add(
                ReportSnapshot(
                    period_key=period_key,
                    report_type="monthly_pnl",
                    payload_json=json.dumps(payload),
                    is_closed=True,
                    closed_by_user_id=closed_by_user_id,
                )
            )
    return payload


@require_permission("reports.view")
def get_month_snapshot(year: int, month: int) -> Optional[dict]:
    period_key = f"{year:04d}-{month:02d}"
    with session_scope() as session:
        row = (
            session.query(ReportSnapshot)
            .filter_by(period_key=period_key, report_type="monthly_pnl")
            .one_or_none()
        )
        return json.loads(row.payload_json) if row else None
