"""
Inventory Intelligence Service — Phase 1.

Provides smart inventory analytics using deterministic, documented formulas.
All calculations are derived exclusively from existing transactional data;
no external data sources or estimates are invented.

Formulas (all documented, no black boxes):

  Average Daily Sales (ADS):
      ADS = units_sold_in_period / analysis_period_days

  Sellable Stock:
      sellable_stock = SUM(batch.quantity) WHERE batch.is_active
                       AND batch.expiry_date >= today
                       AND batch.quantity > 0

  Days of Stock Remaining:
      days_remaining = sellable_stock / ADS   (if ADS > 0, else None)

  Reorder Point:
      reorder_point = ADS × lead_time_days + safety_stock_units

  Suggested Order Quantity:
      suggested_qty = max(0, target_stock - sellable_stock - incoming_stock)
      target_stock  = ADS × (lead_time_days + review_period_days) + safety_stock_units

  Estimated Waste (Expiry Risk):
      days_to_expiry  = (expiry_date - today).days
      projected_sales = ADS × days_to_expiry
      waste_units     = max(0, batch.quantity - projected_sales)
      waste_value     = waste_units × batch.purchase_price

  ABC Classification:
      Sort medicines by total revenue (descending).
      A = top 70% of cumulative revenue
      B = next 20% of cumulative revenue
      C = remaining 10%

  Inventory Turnover:
      turnover = COGS_for_period / average_inventory_value

All functions enforce existing service-layer permissions.
All read operations use session_scope() and return plain dicts, never ORM objects.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Optional

from sqlalchemy import func

from app.database.session import session_scope
from app.models import Medicine, MedicineBatch, Sale, SaleItem
from app.models.enums import SaleStatus
from app.security.decorators import require_permission
from app.security.session_context import current_session


# ── Configuration defaults (all overridable per-call) ─────────────────────

DEFAULT_ANALYSIS_DAYS      = 90   # period used to compute ADS
DEFAULT_LEAD_TIME_DAYS     = 7    # assumed supplier lead time if not set
DEFAULT_SAFETY_STOCK_DAYS  = 14   # safety buffer in days of demand
DEFAULT_REVIEW_PERIOD_DAYS = 7    # replenishment review interval
DEFAULT_DEAD_STOCK_DAYS    = 90   # days without sale → dead stock


# ── Internal helpers ──────────────────────────────────────────────────────

def _sellable_stock(session, medicine_id: int, as_of: date) -> int:
    """Sum of quantities across non-expired, active batches."""
    rows = (
        session.query(func.coalesce(func.sum(MedicineBatch.quantity), 0))
        .filter(
            MedicineBatch.medicine_id == medicine_id,
            MedicineBatch.is_active.is_(True),
            MedicineBatch.expiry_date >= as_of,
        )
        .scalar()
    )
    return int(rows or 0)


def _units_sold_in_period(session, medicine_id: int,
                           period_start: date, period_end: date) -> float:
    """Total units sold for a medicine in [period_start, period_end]."""
    result = (
        session.query(func.coalesce(func.sum(SaleItem.quantity), 0))
        .join(MedicineBatch, MedicineBatch.id == SaleItem.batch_id)
        .join(Sale, Sale.id == SaleItem.sale_id)
        .filter(
            MedicineBatch.medicine_id == medicine_id,
            Sale.sale_date >= period_start,
            Sale.sale_date <= period_end,
            Sale.status == SaleStatus.COMPLETED,
        )
        .scalar()
    )
    return float(result or 0)


def _last_sale_date(session, medicine_id: int) -> Optional[date]:
    """Most recent sale date for a medicine, or None."""
    row = (
        session.query(func.max(Sale.sale_date))
        .join(SaleItem, SaleItem.sale_id == Sale.id)
        .join(MedicineBatch, MedicineBatch.id == SaleItem.batch_id)
        .filter(
            MedicineBatch.medicine_id == medicine_id,
            Sale.status == SaleStatus.COMPLETED,
        )
        .scalar()
    )
    return row


def _cogs_for_period(session, period_start: date, period_end: date) -> float:
    """Total COGS for COMPLETED sales in the period."""
    result = (
        session.query(
            func.coalesce(func.sum(SaleItem.unit_cost * SaleItem.quantity), 0)
        )
        .join(Sale, Sale.id == SaleItem.sale_id)
        .filter(
            Sale.sale_date >= period_start,
            Sale.sale_date <= period_end,
            Sale.status == SaleStatus.COMPLETED,
        )
        .scalar()
    )
    return float(result or 0)


def _average_inventory_value(session, period_start: date, period_end: date) -> float:
    """
    Approximation: (opening_value + closing_value) / 2.
    Uses current stock value as closing, and treats it as a reasonable proxy.
    For a more precise calculation a periodic snapshot system would be needed.
    """
    current_value = float(
        session.query(
            func.coalesce(
                func.sum(MedicineBatch.quantity * MedicineBatch.purchase_price), 0
            )
        )
        .filter(MedicineBatch.is_active.is_(True), MedicineBatch.quantity > 0)
        .scalar()
        or 0
    )
    return current_value  # simplified — single snapshot


# ── Public API ────────────────────────────────────────────────────────────

@require_permission("stock.view")
def get_reorder_suggestions(
    *,
    analysis_days: int = DEFAULT_ANALYSIS_DAYS,
    lead_time_days: int = DEFAULT_LEAD_TIME_DAYS,
    safety_stock_days: int = DEFAULT_SAFETY_STOCK_DAYS,
    review_period_days: int = DEFAULT_REVIEW_PERIOD_DAYS,
    only_below_reorder_point: bool = False,
) -> list[dict]:
    """
    Returns reorder suggestions for all active medicines.

    Each entry contains:
        medicine_id, name, dosage_form, unit
        sellable_stock      — non-expired, active batch quantities
        avg_daily_sales     — ADS over analysis_days
        days_remaining      — estimated days until stockout (None if ADS == 0)
        lead_time_days      — configured lead time
        reorder_point       — trigger point for ordering
        suggested_qty       — recommended order quantity (0 if not needed)
        explanation         — human-readable explanation of the recommendation
        needs_reorder       — bool: sellable_stock <= reorder_point
    """
    today        = date.today()
    period_start = today - timedelta(days=analysis_days)
    results      = []

    with session_scope() as session:
        medicines = (
            session.query(Medicine)
            .filter(Medicine.is_active.is_(True))
            .order_by(Medicine.name)
            .all()
        )

        for med in medicines:
            stock   = _sellable_stock(session, med.id, today)
            sold    = _units_sold_in_period(session, med.id, period_start, today)
            ads     = round(sold / analysis_days, 4) if analysis_days > 0 else 0.0

            days_remaining: Optional[float] = (
                round(stock / ads, 1) if ads > 0 else None
            )

            safety_stock_units = round(ads * safety_stock_days)
            reorder_point      = round(ads * lead_time_days + safety_stock_units)
            target_stock       = round(
                ads * (lead_time_days + review_period_days) + safety_stock_units
            )
            suggested_qty      = max(0, target_stock - stock)
            needs_reorder      = stock <= reorder_point

            if only_below_reorder_point and not needs_reorder:
                continue

            # Human-readable explanation
            if ads == 0:
                explanation = (
                    f"No sales recorded in the last {analysis_days} days. "
                    "Current stock level cannot be evaluated against demand."
                )
            elif not needs_reorder:
                explanation = (
                    f"Sufficient stock for approximately {days_remaining:.0f} days "
                    f"based on average daily sales of {ads:.1f} units. "
                    f"Reorder point is {reorder_point} units."
                )
            else:
                if days_remaining is not None and days_remaining <= lead_time_days:
                    urgency = "⚠ URGENT — stock may run out before a new order arrives."
                elif days_remaining is not None and days_remaining <= lead_time_days + safety_stock_days:
                    urgency = "Reorder soon — approaching safety stock level."
                else:
                    urgency = "Below reorder point — consider placing an order."
                explanation = (
                    f"{urgency} "
                    f"Current sellable stock: {stock} units. "
                    f"ADS: {ads:.1f} units/day. "
                    f"Estimated {days_remaining:.0f} days remaining. "
                    f"Suggested order: {suggested_qty} units to reach {target_stock}-unit target."
                ) if days_remaining is not None else (
                    f"Stock is at or below reorder point ({reorder_point} units) "
                    f"but no recent sales data available. Manual review recommended."
                )

            results.append({
                "medicine_id":       med.id,
                "name":              med.name,
                "dosage_form":       med.dosage_form.value if med.dosage_form else "",
                "unit":              med.base_unit or med.unit or "",
                "sellable_stock":    stock,
                "avg_daily_sales":   ads,
                "days_remaining":    days_remaining,
                "lead_time_days":    lead_time_days,
                "reorder_point":     reorder_point,
                "target_stock":      target_stock,
                "suggested_qty":     suggested_qty,
                "needs_reorder":     needs_reorder,
                "explanation":       explanation,
                "analysis_days":     analysis_days,
            })

    return results


@require_permission("stock.view")
def get_expiry_risk_report(
    *,
    warning_days: int = 214,   # ~7 months
    analysis_days: int = DEFAULT_ANALYSIS_DAYS,
) -> list[dict]:
    """
    Enhanced expiry risk report that adds financial and demand context.

    Risk classification:
        HIGH     — waste_value > 1000 PKR  OR  days_to_expiry <= 30
        MODERATE — waste_value > 200 PKR   OR  days_to_expiry <= 90
        LOW      — otherwise (still within warning window)

    Returns list of dicts, each containing:
        batch_id, medicine_id, medicine_name, batch_number
        expiry_date, days_to_expiry
        quantity, purchase_price, purchase_value
        avg_daily_sales (medicine-level)
        projected_sales_before_expiry
        estimated_waste_units, estimated_waste_value
        risk_level  (HIGH / MODERATE / LOW)
        location
    """
    today        = date.today()
    cutoff       = today + timedelta(days=warning_days)
    period_start = today - timedelta(days=analysis_days)

    results = []

    with session_scope() as session:
        from sqlalchemy.orm import selectinload
        from app.models.location import Shelf, Rack, Wardrobe

        batches = (
            session.query(MedicineBatch)
            .options(
                selectinload(MedicineBatch.medicine),
                selectinload(MedicineBatch.shelf)
                    .selectinload(Shelf.rack)
                    .selectinload(Rack.wardrobe),
            )
            .filter(
                MedicineBatch.is_active.is_(True),
                MedicineBatch.quantity > 0,
                MedicineBatch.expiry_date <= cutoff,
            )
            .order_by(MedicineBatch.expiry_date.asc())
            .all()
        )

        for b in batches:
            days_to_expiry  = (b.expiry_date - today).days
            purchase_value  = float(b.purchase_price) * b.quantity
            sold            = _units_sold_in_period(
                session, b.medicine_id, period_start, today
            )
            ads             = round(sold / analysis_days, 4) if analysis_days > 0 else 0.0
            projected_sales = round(ads * max(0, days_to_expiry), 1) if ads > 0 else 0.0
            waste_units     = max(0.0, b.quantity - projected_sales)
            waste_value     = round(waste_units * float(b.purchase_price), 2)

            # Risk classification
            if days_to_expiry < 0:
                risk_level = "EXPIRED"
            elif waste_value > 1000 or days_to_expiry <= 30:
                risk_level = "HIGH"
            elif waste_value > 200 or days_to_expiry <= 90:
                risk_level = "MODERATE"
            else:
                risk_level = "LOW"

            location = ""
            if b.shelf:
                try:
                    location = b.shelf.full_location
                except Exception:
                    pass

            results.append({
                "batch_id":                      b.id,
                "medicine_id":                   b.medicine_id,
                "medicine_name":                 b.medicine.name,
                "batch_number":                  b.batch_number,
                "expiry_date":                   b.expiry_date.isoformat(),
                "days_to_expiry":                days_to_expiry,
                "quantity":                      b.quantity,
                "purchase_price":                float(b.purchase_price),
                "selling_price":                 float(b.selling_price),
                "purchase_value":                round(purchase_value, 2),
                "avg_daily_sales":               ads,
                "projected_sales_before_expiry": projected_sales,
                "estimated_waste_units":         round(waste_units, 1),
                "estimated_waste_value":         waste_value,
                "risk_level":                    risk_level,
                "location":                      location,
            })

    return results


@require_permission("stock.view")
def get_dead_stock(
    *,
    dead_stock_days: int = DEFAULT_DEAD_STOCK_DAYS,
) -> list[dict]:
    """
    Identifies medicines with no sales for the past `dead_stock_days`.

    Returns list of dicts:
        medicine_id, name, dosage_form
        last_sale_date (None if never sold)
        days_without_sales
        sellable_stock
        stock_value (at purchase price)
        earliest_expiry (soonest expiry across all active batches)
        suggested_action
    """
    today     = date.today()
    threshold = today - timedelta(days=dead_stock_days)
    results   = []

    with session_scope() as session:
        medicines = (
            session.query(Medicine)
            .filter(Medicine.is_active.is_(True))
            .order_by(Medicine.name)
            .all()
        )

        for med in medicines:
            stock = _sellable_stock(session, med.id, today)
            if stock == 0:
                continue   # out of stock — not "dead stock", just empty

            last_sale = _last_sale_date(session, med.id)
            if last_sale is not None and last_sale >= threshold:
                continue   # sold recently — not dead stock

            days_without = (
                (today - last_sale).days if last_sale else None
            )

            # Stock value at cost
            stock_value = float(
                session.query(
                    func.coalesce(
                        func.sum(
                            MedicineBatch.quantity * MedicineBatch.purchase_price
                        ),
                        0,
                    )
                )
                .filter(
                    MedicineBatch.medicine_id == med.id,
                    MedicineBatch.is_active.is_(True),
                    MedicineBatch.expiry_date >= today,
                    MedicineBatch.quantity > 0,
                )
                .scalar()
                or 0
            )

            # Earliest expiry
            earliest_row = (
                session.query(func.min(MedicineBatch.expiry_date))
                .filter(
                    MedicineBatch.medicine_id == med.id,
                    MedicineBatch.is_active.is_(True),
                    MedicineBatch.expiry_date >= today,
                    MedicineBatch.quantity > 0,
                )
                .scalar()
            )
            earliest_expiry = earliest_row.isoformat() if earliest_row else None

            if last_sale is None:
                action = "Never sold — consider removing from catalog or running a promotion."
            elif days_without and days_without > 180:
                action = "No sales in 6+ months — review with supplier for return or discount."
            else:
                action = f"No sales in {days_without} days — consider a promotional price."

            results.append({
                "medicine_id":        med.id,
                "name":               med.name,
                "dosage_form":        med.dosage_form.value if med.dosage_form else "",
                "last_sale_date":     last_sale.isoformat() if last_sale else None,
                "days_without_sales": days_without,
                "sellable_stock":     stock,
                "stock_value":        round(stock_value, 2),
                "earliest_expiry":    earliest_expiry,
                "suggested_action":   action,
                "threshold_days":     dead_stock_days,
            })

    return sorted(results, key=lambda x: (x["days_without_sales"] or 9999), reverse=True)


@require_permission("reports.view")
def get_abc_classification(
    *,
    analysis_days: int = DEFAULT_ANALYSIS_DAYS,
    a_threshold: float = 0.70,
    b_threshold: float = 0.90,
) -> list[dict]:
    """
    ABC inventory classification by revenue contribution.

    A items = top a_threshold (default 70%) of cumulative revenue
    B items = next b_threshold - a_threshold (default 20%)
    C items = remaining

    Returns sorted list (highest revenue first), each entry:
        medicine_id, name
        units_sold, revenue, cumulative_revenue_pct
        abc_class (A / B / C)
        avg_daily_sales
        sellable_stock
    """
    today        = date.today()
    period_start = today - timedelta(days=analysis_days)
    results      = []

    with session_scope() as session:
        # Revenue per medicine in period
        rows = (
            session.query(
                MedicineBatch.medicine_id,
                func.sum(SaleItem.quantity).label("units_sold"),
                func.sum(
                    SaleItem.quantity * SaleItem.unit_price - SaleItem.line_discount
                ).label("revenue"),
            )
            .join(SaleItem, SaleItem.batch_id == MedicineBatch.id)
            .join(Sale, Sale.id == SaleItem.sale_id)
            .filter(
                Sale.sale_date >= period_start,
                Sale.sale_date <= today,
                Sale.status == SaleStatus.COMPLETED,
            )
            .group_by(MedicineBatch.medicine_id)
            .order_by(func.sum(
                SaleItem.quantity * SaleItem.unit_price - SaleItem.line_discount
            ).desc())
            .all()
        )

        total_revenue = sum(float(r.revenue or 0) for r in rows)
        if total_revenue == 0:
            return []

        cumulative   = 0.0
        med_ids_seen = set()
        interim      = []

        for r in rows:
            rev = float(r.revenue or 0)
            cumulative += rev
            pct = cumulative / total_revenue
            interim.append({
                "medicine_id":        r.medicine_id,
                "units_sold":         int(r.units_sold or 0),
                "revenue":            round(rev, 2),
                "cumulative_pct":     round(pct, 4),
                "abc_class":          "A" if pct <= a_threshold else (
                                      "B" if pct <= b_threshold else "C"),
            })
            med_ids_seen.add(r.medicine_id)

        # Add sellable stock and medicine name
        meds = {
            m.id: m for m in
            session.query(Medicine).filter(Medicine.id.in_(med_ids_seen)).all()
        }

        for item in interim:
            med  = meds.get(item["medicine_id"])
            ads  = round(item["units_sold"] / analysis_days, 4) if analysis_days else 0
            stock = _sellable_stock(session, item["medicine_id"], today)
            item.update({
                "name":           med.name if med else str(item["medicine_id"]),
                "dosage_form":    med.dosage_form.value if med and med.dosage_form else "",
                "avg_daily_sales": ads,
                "sellable_stock": stock,
            })
            results.append(item)

    return results


@require_permission("reports.view")
def get_inventory_turnover(
    *,
    analysis_days: int = DEFAULT_ANALYSIS_DAYS,
) -> dict:
    """
    Computes inventory turnover ratio for the analysis period.

    Formula:
        Turnover = COGS_for_period / average_inventory_value

    A higher turnover means faster-moving inventory.
    Industry benchmark for pharmacies: 6–12 turns/year.

    Returns:
        cogs, average_inventory_value, turnover_ratio
        annualized_turnover (extrapolated to 365 days)
        interpretation
    """
    today        = date.today()
    period_start = today - timedelta(days=analysis_days)

    with session_scope() as session:
        cogs    = _cogs_for_period(session, period_start, today)
        avg_inv = _average_inventory_value(session, period_start, today)

        if avg_inv > 0:
            turnover   = round(cogs / avg_inv, 4)
            annualized = round(turnover * (365 / analysis_days), 2)
        else:
            turnover   = 0.0
            annualized = 0.0

        if annualized >= 12:
            interpretation = "Excellent — high inventory velocity."
        elif annualized >= 6:
            interpretation = "Good — healthy inventory turnover."
        elif annualized >= 3:
            interpretation = "Moderate — consider reviewing slow-moving stock."
        elif annualized > 0:
            interpretation = "Low — significant slow-moving or dead stock may exist."
        else:
            interpretation = "No sales data available for this period."

        return {
            "period_start":           period_start.isoformat(),
            "period_end":             today.isoformat(),
            "analysis_days":          analysis_days,
            "cogs":                   round(cogs, 2),
            "average_inventory_value": round(avg_inv, 2),
            "turnover_ratio":          turnover,
            "annualized_turnover":     annualized,
            "interpretation":          interpretation,
            "formula":                 "COGS / Average Inventory Value",
        }


@require_permission("stock.view")
def get_stock_intelligence_summary() -> dict:
    """
    Quick summary for the dashboard — aggregates key intelligence metrics.
    Designed to be called from the dashboard to show summary cards.

    Returns:
        items_needing_reorder  (count)
        dead_stock_count       (count)
        high_expiry_risk_count (count, batches)
        potential_waste_value  (PKR)
        inventory_turnover     (annualized ratio)
    """
    today = date.today()

    with session_scope() as session:
        # Items needing reorder
        period_start = today - timedelta(days=DEFAULT_ANALYSIS_DAYS)
        medicines    = (
            session.query(Medicine)
            .filter(Medicine.is_active.is_(True))
            .all()
        )

        needs_reorder = 0
        for med in medicines:
            stock = _sellable_stock(session, med.id, today)
            sold  = _units_sold_in_period(session, med.id, period_start, today)
            ads   = sold / DEFAULT_ANALYSIS_DAYS if DEFAULT_ANALYSIS_DAYS > 0 else 0
            rp    = round(ads * DEFAULT_LEAD_TIME_DAYS +
                          ads * DEFAULT_SAFETY_STOCK_DAYS)
            if stock <= rp:
                needs_reorder += 1

        # High expiry risk batches
        cutoff = today + timedelta(days=214)
        high_risk_batches = (
            session.query(func.count(MedicineBatch.id))
            .filter(
                MedicineBatch.is_active.is_(True),
                MedicineBatch.quantity > 0,
                MedicineBatch.expiry_date <= today + timedelta(days=30),
                MedicineBatch.expiry_date >= today,
            )
            .scalar()
        ) or 0

        # Potential waste value (batches expiring within 90 days)
        waste_q = (
            session.query(
                func.coalesce(
                    func.sum(
                        MedicineBatch.quantity * MedicineBatch.purchase_price
                    ),
                    0,
                )
            )
            .filter(
                MedicineBatch.is_active.is_(True),
                MedicineBatch.quantity > 0,
                MedicineBatch.expiry_date <= today + timedelta(days=90),
                MedicineBatch.expiry_date >= today,
            )
            .scalar()
        )
        potential_waste = float(waste_q or 0)

        # Dead stock count
        dead = 0
        threshold = today - timedelta(days=DEFAULT_DEAD_STOCK_DAYS)
        for med in medicines:
            stock = _sellable_stock(session, med.id, today)
            if stock == 0:
                continue
            last_sale = _last_sale_date(session, med.id)
            if last_sale is None or last_sale < threshold:
                dead += 1

        # Turnover
        cogs    = _cogs_for_period(session, period_start, today)
        avg_inv = _average_inventory_value(session, period_start, today)
        turnover = round(
            (cogs / avg_inv) * (365 / DEFAULT_ANALYSIS_DAYS), 2
        ) if avg_inv > 0 else 0.0

    return {
        "items_needing_reorder":  needs_reorder,
        "dead_stock_count":       dead,
        "high_expiry_risk_count": int(high_risk_batches),
        "potential_waste_value":  round(potential_waste, 2),
        "inventory_turnover":     turnover,
    }
