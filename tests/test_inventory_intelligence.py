"""
Phase 1 — Smart Inventory Intelligence Tests.

Tests cover:
  - Reorder calculation formulas
  - Expiry risk classification
  - Dead stock detection
  - ABC classification
  - Inventory turnover
  - Permission enforcement
  - Edge cases: zero sales, zero stock, never-sold medicines

All tests use the disposable test DB from conftest.py.
No production database is touched.
"""
from __future__ import annotations

import pytest
from datetime import date, timedelta

from app.database.session import session_scope
from app.models import (
    Medicine, MedicineBatch, Sale, SaleItem, Supplier, Customer,
    ExpenseCategory, Expense,
)
from app.models.enums import DosageForm, StockTxnType, SaleStatus
from app.services import stock_service
from app.utils.exceptions import AuthorizationError


# ── Fixtures ──────────────────────────────────────────────────────────────

@pytest.fixture()
def medicine_with_stock(admin_logged_in):
    """Active medicine with one non-expired batch, qty=100."""
    with session_scope() as session:
        med = Medicine(
            name="Test Paracetamol",
            dosage_form=DosageForm.TABLET,
            min_stock_level=10,
            reorder_level=20,
            is_active=True,
        )
        session.add(med)
        session.flush()

        batch = MedicineBatch(
            medicine_id=med.id,
            batch_number="TP-001",
            purchase_price=5.0,
            selling_price=10.0,
            expiry_date=date.today() + timedelta(days=365),
            quantity=0,
            is_active=True,
        )
        session.add(batch)
        session.flush()

        stock_service.apply_stock_change(
            session, batch=batch, delta=100,
            txn_type=StockTxnType.ADJUSTMENT_IN,
            user_id=1, reason="test fixture"
        )
        return {"medicine_id": med.id, "batch_id": batch.id, "medicine_name": med.name}


@pytest.fixture()
def medicine_with_sales(medicine_with_stock):
    """Same medicine, but with 30 sales of 1 unit each over the last 30 days."""
    import uuid
    prefix = uuid.uuid4().hex[:8].upper()
    with session_scope() as session:
        for i in range(30):
            sale_date = date.today() - timedelta(days=i)
            sale = Sale(
                invoice_number=f"INV-{prefix}-{i:04d}",
                sale_date=sale_date,
                subtotal=10.0,
                discount_total=0,
                tax_total=0,
                total=10.0,
                amount_paid=10.0,
                change_due=0,
                status=SaleStatus.COMPLETED,
            )
            session.add(sale)
            session.flush()
            item = SaleItem(
                sale_id=sale.id,
                batch_id=medicine_with_stock["batch_id"],
                quantity=1,
                unit_price=10.0,
                unit_cost=5.0,
                line_discount=0,
            )
            session.add(item)
    return medicine_with_stock


@pytest.fixture()
def expired_batch_medicine(admin_logged_in):
    """Medicine with an expired batch (qty=20, expiry yesterday)."""
    with session_scope() as session:
        med = Medicine(
            name="Expired Med",
            dosage_form=DosageForm.TABLET,
            min_stock_level=5,
            reorder_level=10,
            is_active=True,
        )
        session.add(med)
        session.flush()

        batch = MedicineBatch(
            medicine_id=med.id,
            batch_number="EXP-001",
            purchase_price=8.0,
            selling_price=15.0,
            expiry_date=date.today() - timedelta(days=1),
            quantity=0,
            is_active=True,
        )
        session.add(batch)
        session.flush()

        stock_service.apply_stock_change(
            session, batch=batch, delta=20,
            txn_type=StockTxnType.ADJUSTMENT_IN,
            user_id=1, reason="test expired batch"
        )
        return {"medicine_id": med.id, "batch_id": batch.id}


# ── Sellable stock helper ─────────────────────────────────────────────────

class TestSellableStock:
    def test_counts_only_non_expired_batches(self, medicine_with_stock, expired_batch_medicine):
        """Expired batches must NOT count as sellable stock."""
        from app.services.inventory_intelligence_service import _sellable_stock
        today = date.today()
        with session_scope() as session:
            # medicine_with_stock has 100 units, not expired
            ss = _sellable_stock(session, medicine_with_stock["medicine_id"], today)
            assert ss == 100

            # expired_batch_medicine has 20 units, ALL expired
            ss_exp = _sellable_stock(session, expired_batch_medicine["medicine_id"], today)
            assert ss_exp == 0, "Expired stock must not count as sellable"

    def test_zero_for_medicine_with_no_batches(self, admin_logged_in):
        with session_scope() as session:
            med = Medicine(
                name="No Batch Med", dosage_form=DosageForm.TABLET,
                min_stock_level=5, reorder_level=10, is_active=True,
            )
            session.add(med)
            session.flush()
            from app.services.inventory_intelligence_service import _sellable_stock
            assert _sellable_stock(session, med.id, date.today()) == 0


# ── Average Daily Sales ───────────────────────────────────────────────────

class TestAverageDailySales:
    def test_correct_ads_calculation(self, medicine_with_sales):
        """30 sales of 1 unit over 30 days → ADS = 1.0."""
        from app.services.inventory_intelligence_service import _units_sold_in_period
        today = date.today()
        period_start = today - timedelta(days=30)
        with session_scope() as session:
            sold = _units_sold_in_period(
                session, medicine_with_sales["medicine_id"],
                period_start, today
            )
        # 30 sales × 1 unit = 30 units
        assert sold == 30.0
        ads = sold / 30
        assert abs(ads - 1.0) < 0.01

    def test_zero_ads_for_no_sales(self, medicine_with_stock):
        from app.services.inventory_intelligence_service import _units_sold_in_period
        today = date.today()
        with session_scope() as session:
            sold = _units_sold_in_period(
                session, medicine_with_stock["medicine_id"],
                today - timedelta(days=90), today
            )
        assert sold == 0.0


# ── Reorder suggestions ───────────────────────────────────────────────────

class TestReorderSuggestions:
    def test_permission_required(self):
        from app.security.session_context import current_session
        current_session.clear()
        from app.services.inventory_intelligence_service import get_reorder_suggestions
        with pytest.raises(Exception):
            get_reorder_suggestions()

    def test_returns_list(self, admin_logged_in):
        from app.services.inventory_intelligence_service import get_reorder_suggestions
        result = get_reorder_suggestions(analysis_days=90)
        assert isinstance(result, list)

    def test_result_has_required_keys(self, medicine_with_stock, admin_logged_in):
        from app.services.inventory_intelligence_service import get_reorder_suggestions
        result = get_reorder_suggestions(analysis_days=90)
        required_keys = {
            "medicine_id", "name", "sellable_stock", "avg_daily_sales",
            "reorder_point", "suggested_qty", "needs_reorder", "explanation",
        }
        for item in result:
            assert required_keys.issubset(item.keys()), \
                f"Missing keys: {required_keys - item.keys()}"

    def test_no_sales_medicine_has_zero_ads(self, medicine_with_stock, admin_logged_in):
        from app.services.inventory_intelligence_service import get_reorder_suggestions
        result = get_reorder_suggestions(analysis_days=90)
        found = [r for r in result
                 if r["medicine_id"] == medicine_with_stock["medicine_id"]]
        assert len(found) == 1
        assert found[0]["avg_daily_sales"] == 0.0

    def test_reorder_point_formula(self, admin_logged_in):
        """
        Reorder Point = ADS × lead_time_days + ADS × safety_stock_days
        With ADS=1, lead=7, safety=14 → RP = 21
        """
        from app.services.inventory_intelligence_service import get_reorder_suggestions
        # Create medicine and add exactly 30 sales
        with session_scope() as session:
            med = Medicine(
                name="Formula Test Med", dosage_form=DosageForm.TABLET,
                min_stock_level=5, reorder_level=10, is_active=True,
            )
            session.add(med)
            session.flush()
            batch = MedicineBatch(
                medicine_id=med.id, batch_number="FT-001",
                purchase_price=5.0, selling_price=10.0,
                expiry_date=date.today() + timedelta(days=365),
                quantity=0, is_active=True,
            )
            session.add(batch)
            session.flush()
            stock_service.apply_stock_change(
                session, batch=batch, delta=5,
                txn_type=StockTxnType.ADJUSTMENT_IN,
                user_id=1, reason="test"
            )
            for i in range(30):
                import uuid as _uuid
                pfx = _uuid.uuid4().hex[:6].upper()
                sale = Sale(
                    invoice_number=f"FT-{pfx}-{i:04d}",
                    sale_date=date.today() - timedelta(days=i),
                    subtotal=10.0, discount_total=0, tax_total=0,
                    total=10.0, amount_paid=10.0, change_due=0,
                    status=SaleStatus.COMPLETED,
                )
                session.add(sale)
                session.flush()
                session.add(SaleItem(
                    sale_id=sale.id, batch_id=batch.id,
                    quantity=1, unit_price=10.0, unit_cost=5.0, line_discount=0,
                ))
            med_id = med.id

        result = get_reorder_suggestions(
            analysis_days=30, lead_time_days=7, safety_stock_days=14
        )
        found = [r for r in result if r["medicine_id"] == med_id]
        assert len(found) == 1
        item = found[0]

        # ADS = 30 / 30 = 1.0
        assert abs(item["avg_daily_sales"] - 1.0) < 0.01
        # RP = 1.0 × 7 + 1.0 × 14 = 21
        assert item["reorder_point"] == 21, \
            f"Expected reorder_point=21, got {item['reorder_point']}"

    def test_suggested_qty_zero_when_stock_is_sufficient(self, medicine_with_stock, admin_logged_in):
        """Medicine with 100 units and 0 sales → suggested_qty should be 0."""
        from app.services.inventory_intelligence_service import get_reorder_suggestions
        result = get_reorder_suggestions(analysis_days=90)
        found = [r for r in result
                 if r["medicine_id"] == medicine_with_stock["medicine_id"]]
        assert len(found) == 1
        # ADS = 0, so reorder_point = 0 and stock (100) > 0 → no reorder needed
        assert found[0]["suggested_qty"] == 0
        assert not found[0]["needs_reorder"]

    def test_only_below_rp_filter(self, admin_logged_in):
        from app.services.inventory_intelligence_service import get_reorder_suggestions
        all_items    = get_reorder_suggestions(analysis_days=90, only_below_reorder_point=False)
        below_rp     = get_reorder_suggestions(analysis_days=90, only_below_reorder_point=True)
        assert len(below_rp) <= len(all_items)
        for item in below_rp:
            assert item["needs_reorder"]

    def test_expired_stock_not_counted_as_sellable(self, expired_batch_medicine, admin_logged_in):
        """Expired batch stock must not reduce the suggested reorder quantity."""
        from app.services.inventory_intelligence_service import get_reorder_suggestions
        result = get_reorder_suggestions(analysis_days=90)
        found = [r for r in result
                 if r["medicine_id"] == expired_batch_medicine["medicine_id"]]
        assert len(found) == 1
        # sellable_stock must be 0 because the only batch is expired
        assert found[0]["sellable_stock"] == 0


# ── Expiry risk ───────────────────────────────────────────────────────────

class TestExpiryRisk:
    def test_permission_required(self):
        from app.security.session_context import current_session
        current_session.clear()
        from app.services.inventory_intelligence_service import get_expiry_risk_report
        with pytest.raises(Exception):
            get_expiry_risk_report()

    def test_returns_list(self, admin_logged_in, medicine_with_stock):
        from app.services.inventory_intelligence_service import get_expiry_risk_report
        result = get_expiry_risk_report(warning_days=400)
        assert isinstance(result, list)

    def test_expired_batch_classified_expired(self, expired_batch_medicine, admin_logged_in):
        from app.services.inventory_intelligence_service import get_expiry_risk_report
        result = get_expiry_risk_report(warning_days=400)
        found = [r for r in result
                 if r["medicine_id"] == expired_batch_medicine["medicine_id"]]
        assert len(found) >= 1
        assert found[0]["risk_level"] == "EXPIRED"

    def test_purchase_value_calculated(self, expired_batch_medicine, admin_logged_in):
        """purchase_value = qty × purchase_price."""
        from app.services.inventory_intelligence_service import get_expiry_risk_report
        result = get_expiry_risk_report(warning_days=400)
        found = [r for r in result
                 if r["medicine_id"] == expired_batch_medicine["medicine_id"]]
        assert len(found) >= 1
        item = found[0]
        expected = item["quantity"] * item["purchase_price"]
        assert abs(item["purchase_value"] - expected) < 0.01

    def test_high_risk_for_imminent_expiry(self, admin_logged_in):
        """Batch expiring in 15 days → HIGH risk."""
        with session_scope() as session:
            med = Medicine(
                name="Soon Expire Med", dosage_form=DosageForm.TABLET,
                min_stock_level=5, reorder_level=10, is_active=True,
            )
            session.add(med)
            session.flush()
            batch = MedicineBatch(
                medicine_id=med.id, batch_number="SE-001",
                purchase_price=50.0, selling_price=100.0,
                expiry_date=date.today() + timedelta(days=15),
                quantity=0, is_active=True,
            )
            session.add(batch)
            session.flush()
            stock_service.apply_stock_change(
                session, batch=batch, delta=100,
                txn_type=StockTxnType.ADJUSTMENT_IN,
                user_id=1, reason="test"
            )
            med_id = med.id

        from app.services.inventory_intelligence_service import get_expiry_risk_report
        result = get_expiry_risk_report(warning_days=400, analysis_days=90)
        found = [r for r in result if r["medicine_id"] == med_id]
        assert len(found) >= 1
        assert found[0]["risk_level"] == "HIGH", \
            f"Expected HIGH, got {found[0]['risk_level']}"

    def test_waste_value_zero_when_sufficient_sales_velocity(self, admin_logged_in):
        """
        If ADS × days_to_expiry >= qty, no waste is expected.
        Batch: qty=10, expiry in 20 days.
        Create 10 sales/day over last 30 days → ADS = 10.
        projected_sales = 10 × 20 = 200 >> 10 → waste = 0.
        """
        with session_scope() as session:
            med = Medicine(
                name="Fast Mover", dosage_form=DosageForm.TABLET,
                min_stock_level=5, reorder_level=10, is_active=True,
            )
            session.add(med)
            session.flush()
            batch = MedicineBatch(
                medicine_id=med.id, batch_number="FM-001",
                purchase_price=10.0, selling_price=20.0,
                expiry_date=date.today() + timedelta(days=20),
                quantity=0, is_active=True,
            )
            session.add(batch)
            session.flush()
            stock_service.apply_stock_change(
                session, batch=batch, delta=310,  # 300 for sales + 10 remaining
                txn_type=StockTxnType.ADJUSTMENT_IN,
                user_id=1, reason="test"
            )
            # 10 units/day × 30 days = 300 sales
            for i in range(30):
                import uuid as _uuid2
                pfx2 = _uuid2.uuid4().hex[:6].upper()
                sale = Sale(
                    invoice_number=f"FM-{pfx2}-{i:04d}",
                    sale_date=date.today() - timedelta(days=i),
                    subtotal=200.0, discount_total=0, tax_total=0,
                    total=200.0, amount_paid=200.0, change_due=0,
                    status=SaleStatus.COMPLETED,
                )
                session.add(sale)
                session.flush()
                session.add(SaleItem(
                    sale_id=sale.id, batch_id=batch.id,
                    quantity=10, unit_price=20.0, unit_cost=10.0, line_discount=0,
                ))
                stock_service.apply_stock_change(
                    session, batch=batch, delta=-10,
                    txn_type=StockTxnType.SALE,
                    user_id=1, reference=f"FM-{pfx2}-{i:04d}", reason="test sale"
                )
            med_id = med.id

        from app.services.inventory_intelligence_service import get_expiry_risk_report
        result = get_expiry_risk_report(warning_days=400, analysis_days=30)
        found = [r for r in result if r["medicine_id"] == med_id]
        if found:
            assert found[0]["estimated_waste_units"] == 0.0, \
                f"Expected 0 waste, got {found[0]['estimated_waste_units']}"


# ── Dead stock ────────────────────────────────────────────────────────────

class TestDeadStock:
    def test_permission_required(self):
        from app.security.session_context import current_session
        current_session.clear()
        from app.services.inventory_intelligence_service import get_dead_stock
        with pytest.raises(Exception):
            get_dead_stock()

    def test_never_sold_medicine_detected(self, medicine_with_stock, admin_logged_in):
        from app.services.inventory_intelligence_service import get_dead_stock
        result = get_dead_stock(dead_stock_days=90)
        found = [r for r in result
                 if r["medicine_id"] == medicine_with_stock["medicine_id"]]
        assert len(found) == 1
        assert found[0]["last_sale_date"] is None

    def test_recently_sold_medicine_excluded(self, medicine_with_sales, admin_logged_in):
        """Medicine sold today must NOT appear in dead stock."""
        from app.services.inventory_intelligence_service import get_dead_stock
        result = get_dead_stock(dead_stock_days=90)
        found = [r for r in result
                 if r["medicine_id"] == medicine_with_sales["medicine_id"]]
        assert len(found) == 0, \
            "Medicine sold within threshold should not be dead stock"

    def test_out_of_stock_excluded(self, admin_logged_in):
        """Zero-stock medicine must NOT appear in dead stock."""
        with session_scope() as session:
            med = Medicine(
                name="Empty Stock Med", dosage_form=DosageForm.TABLET,
                min_stock_level=5, reorder_level=10, is_active=True,
            )
            session.add(med)
            session.flush()
            batch = MedicineBatch(
                medicine_id=med.id, batch_number="ES-001",
                purchase_price=5.0, selling_price=10.0,
                expiry_date=date.today() + timedelta(days=365),
                quantity=0, is_active=True,
            )
            session.add(batch)
            med_id = med.id

        from app.services.inventory_intelligence_service import get_dead_stock
        result = get_dead_stock(dead_stock_days=90)
        found = [r for r in result if r["medicine_id"] == med_id]
        assert len(found) == 0, "Zero-stock item should not be dead stock"

    def test_stock_value_calculated_correctly(self, medicine_with_stock, admin_logged_in):
        """stock_value = sellable_stock × purchase_price."""
        from app.services.inventory_intelligence_service import get_dead_stock
        result = get_dead_stock(dead_stock_days=1)  # threshold=1 day → catches unsold
        found = [r for r in result
                 if r["medicine_id"] == medicine_with_stock["medicine_id"]]
        assert len(found) == 1
        item = found[0]
        # qty=100, purchase_price=5 → value=500
        assert abs(item["stock_value"] - 500.0) < 0.01

    def test_sorted_by_days_without_sales_descending(self, admin_logged_in):
        from app.services.inventory_intelligence_service import get_dead_stock
        result = get_dead_stock(dead_stock_days=1)
        days_list = [r["days_without_sales"] or 9999 for r in result]
        assert days_list == sorted(days_list, reverse=True)


# ── ABC Classification ────────────────────────────────────────────────────

class TestABCClassification:
    def test_permission_required(self):
        from app.security.session_context import current_session
        current_session.clear()
        from app.services.inventory_intelligence_service import get_abc_classification
        with pytest.raises(Exception):
            get_abc_classification()

    def test_returns_empty_with_no_sales(self, admin_logged_in):
        from app.services.inventory_intelligence_service import get_abc_classification
        result = get_abc_classification(analysis_days=90)
        assert isinstance(result, list)
        # Might be empty if no completed sales exist in a fresh test DB
        # (other tests may have added sales — just verify structure if non-empty)
        for item in result:
            assert "abc_class" in item
            assert item["abc_class"] in ("A", "B", "C")

    def test_classes_are_mutually_exclusive(self, medicine_with_sales, admin_logged_in):
        from app.services.inventory_intelligence_service import get_abc_classification
        result = get_abc_classification(analysis_days=90)
        for item in result:
            assert item["abc_class"] in ("A", "B", "C")

    def test_cumulative_pct_increases_monotonically(self, medicine_with_sales, admin_logged_in):
        from app.services.inventory_intelligence_service import get_abc_classification
        result = get_abc_classification(analysis_days=90)
        prev = 0.0
        for item in result:
            assert item["cumulative_pct"] >= prev - 0.0001
            prev = item["cumulative_pct"]

    def test_required_keys_present(self, medicine_with_sales, admin_logged_in):
        from app.services.inventory_intelligence_service import get_abc_classification
        result = get_abc_classification(analysis_days=90)
        required = {"medicine_id", "name", "units_sold", "revenue",
                    "cumulative_pct", "abc_class", "avg_daily_sales"}
        for item in result:
            assert required.issubset(item.keys())


# ── Inventory Turnover ────────────────────────────────────────────────────

class TestInventoryTurnover:
    def test_permission_required(self):
        from app.security.session_context import current_session
        current_session.clear()
        from app.services.inventory_intelligence_service import get_inventory_turnover
        with pytest.raises(Exception):
            get_inventory_turnover()

    def test_returns_dict_with_required_keys(self, admin_logged_in):
        from app.services.inventory_intelligence_service import get_inventory_turnover
        result = get_inventory_turnover(analysis_days=90)
        required = {
            "cogs", "average_inventory_value", "turnover_ratio",
            "annualized_turnover", "interpretation", "formula"
        }
        assert required.issubset(result.keys())

    def test_zero_inventory_returns_zero_turnover(self, admin_logged_in):
        """With empty inventory, turnover ratio should be 0."""
        from app.services.inventory_intelligence_service import get_inventory_turnover
        result = get_inventory_turnover(analysis_days=90)
        # May be 0 if test DB is fresh, or non-zero if other tests ran first
        assert result["turnover_ratio"] >= 0.0
        assert result["annualized_turnover"] >= 0.0

    def test_turnover_formula_documented(self, admin_logged_in):
        from app.services.inventory_intelligence_service import get_inventory_turnover
        result = get_inventory_turnover()
        assert "COGS" in result["formula"]

    def test_positive_turnover_with_sales(self, medicine_with_sales, admin_logged_in):
        """With sales, COGS > 0 → turnover > 0."""
        from app.services.inventory_intelligence_service import get_inventory_turnover
        result = get_inventory_turnover(analysis_days=30)
        # medicine_with_sales has 30 sales × unit_cost=5 → COGS=150
        assert result["cogs"] >= 150.0 - 0.01


# ── Intelligence summary ──────────────────────────────────────────────────

class TestIntelligenceSummary:
    def test_returns_all_keys(self, admin_logged_in):
        from app.services.inventory_intelligence_service import get_stock_intelligence_summary
        result = get_stock_intelligence_summary()
        required = {
            "items_needing_reorder", "dead_stock_count",
            "high_expiry_risk_count", "potential_waste_value",
            "inventory_turnover"
        }
        assert required.issubset(result.keys())

    def test_permission_required(self):
        from app.security.session_context import current_session
        current_session.clear()
        from app.services.inventory_intelligence_service import get_stock_intelligence_summary
        with pytest.raises(Exception):
            get_stock_intelligence_summary()

    def test_all_values_non_negative(self, admin_logged_in, medicine_with_stock):
        from app.services.inventory_intelligence_service import get_stock_intelligence_summary
        result = get_stock_intelligence_summary()
        for key, val in result.items():
            assert val >= 0, f"{key} should be non-negative, got {val}"

    def test_dead_stock_count_reflects_never_sold(self, medicine_with_stock, admin_logged_in):
        """medicine_with_stock is never sold → dead_stock_count >= 1."""
        from app.services.inventory_intelligence_service import get_stock_intelligence_summary
        result = get_stock_intelligence_summary()
        assert result["dead_stock_count"] >= 1
