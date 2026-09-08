"""
Seed script — run after `alembic upgrade head`.

Creates:
  1. The permission catalog (always — required for the app to function).
  2. A default administrator account (always, if none exists yet — this is
     the first-run bootstrap; in the real app the setup wizard collects
     this interactively instead of using a hard-coded demo password).
  3. Optional demo pharmacy data (medicines, batches, a supplier, a
     purchase, a sale) — clearly fictional, deletable by the user, and
     only inserted when --with-demo-data is passed.

Usage:
    python scripts/seed_demo_data.py                  # permissions + admin only
    python scripts/seed_demo_data.py --with-demo-data  # + sample catalog data
"""
from __future__ import annotations

import argparse
import sys
from datetime import date, timedelta
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from app.database.session import session_scope  # noqa: E402
from app.models import (  # noqa: E402
    Category,
    Customer,
    Manufacturer,
    Medicine,
    MedicineBatch,
    Permission,
    Purchase,
    PurchaseItem,
    Rack,
    Sale,
    SaleItem,
    Shelf,
    StockTransaction,
    Supplier,
    User,
    UserPermission,
    Wardrobe,
)
from app.models.enums import DosageForm, PaymentStatus, StockTxnType
from app.permissions.keys import ADMIN_ONLY_PERMISSIONS, GRANTABLE_PERMISSIONS
from app.security.passwords import hash_password

DEFAULT_ADMIN_USERNAME = "admin"
DEFAULT_ADMIN_PASSWORD = "ChangeMe123!"  # noqa: S105 — first-run only, must be changed via setup wizard


def seed_permissions(session) -> None:
    existing = {p.key for p in session.query(Permission).all()}
    for key, description in {**GRANTABLE_PERMISSIONS, **ADMIN_ONLY_PERMISSIONS}.items():
        if key in existing:
            continue
        admin_only = key in ADMIN_ONLY_PERMISSIONS
        session.add(Permission(key=key, description=description, admin_only=admin_only))
    print(f"Permissions in catalog: {len(GRANTABLE_PERMISSIONS) + len(ADMIN_ONLY_PERMISSIONS)}")


def seed_default_admin(session) -> User:
    admin = session.query(User).filter_by(username=DEFAULT_ADMIN_USERNAME).one_or_none()
    if admin:
        print("Default admin already exists — skipping.")
        return admin
    admin = User(
        username=DEFAULT_ADMIN_USERNAME,
        password_hash=hash_password(DEFAULT_ADMIN_PASSWORD),
        full_name="Administrator",
        is_admin=True,
        is_active=True,
    )
    session.add(admin)
    session.flush()
    print(
        f"Created default admin user '{DEFAULT_ADMIN_USERNAME}' "
        f"with a temporary password. CHANGE THIS IMMEDIATELY after first login "
        f"— production builds should replace this with the interactive setup wizard."
    )
    return admin


def seed_demo_catalog_data(session, admin: User) -> None:
    if session.query(Medicine).count() > 0:
        print("Demo medicines already present — skipping demo data.")
        return

    category = Category(name="Analgesic", description="Pain relief")
    manufacturer = Manufacturer(name="GSK Pakistan")
    supplier = Supplier(name="City Pharma Distributors", company="City Pharma", phone="0300-0000000")
    wardrobe = Wardrobe(code="W-01", description="Main wardrobe")
    session.add_all([category, manufacturer, supplier, wardrobe])
    session.flush()

    rack = Rack(wardrobe_id=wardrobe.id, code="R-01")
    session.add(rack)
    session.flush()

    shelf = Shelf(rack_id=rack.id, code="S-01")
    session.add(shelf)
    session.flush()

    medicine = Medicine(
        name="Panadol 500mg",
        generic_formula="Paracetamol",
        brand_name="Panadol",
        category_id=category.id,
        manufacturer_id=manufacturer.id,
        default_supplier_id=supplier.id,
        dosage_form=DosageForm.TABLET,
        strength="500mg",
        pack_size="10x10",
        unit="tablet",
        barcode="8964000000011",
        min_stock_level=50,
        reorder_level=100,
        notes="Demo data — safe to delete.",
    )
    session.add(medicine)
    session.flush()

    batch = MedicineBatch(
        medicine_id=medicine.id,
        shelf_id=shelf.id,
        supplier_id=supplier.id,
        batch_number="DEMO-BATCH-A",
        purchase_price=100.00,
        selling_price=120.00,
        quantity=0,  # will be set to 200 via the purchase + stock transaction below
        manufacturing_date=date.today() - timedelta(days=90),
        expiry_date=date.today() + timedelta(days=540),
    )
    session.add(batch)
    session.flush()

    # Record the "purchase" that brought this batch into stock, with a
    # matching stock transaction — this mirrors exactly how Phase 5
    # (Purchases) will create batches in the real UI.
    purchase = Purchase(
        supplier_id=supplier.id,
        supplier_invoice_number="DEMO-PINV-0001",
        purchase_date=date.today() - timedelta(days=30),
        payment_status=PaymentStatus.PAID,
        total_cost=100.00 * 200,
        created_by_user_id=admin.id,
    )
    session.add(purchase)
    session.flush()

    session.add(PurchaseItem(purchase_id=purchase.id, batch_id=batch.id, quantity=200, purchase_price=100.00))

    previous_qty = batch.quantity
    batch.quantity = previous_qty + 200
    session.add(
        StockTransaction(
            batch_id=batch.id,
            txn_type=StockTxnType.PURCHASE,
            quantity=200,
            previous_quantity=previous_qty,
            new_quantity=batch.quantity,
            reference=purchase.supplier_invoice_number,
            user_id=admin.id,
            reason="Demo seed purchase",
        )
    )

    customer = Customer(name="Walk-in Customer", phone=None)
    session.add(customer)
    session.flush()

    # A demo sale of 5 units, reducing the batch and recording profit correctly.
    sale = Sale(
        invoice_number="INV-DEMO-000001",
        sale_date=date.today(),
        customer_id=customer.id,
        cashier_id=admin.id,
        subtotal=120.00 * 5,
        discount_total=0,
        tax_total=0,
        total=120.00 * 5,
        amount_paid=120.00 * 5,
        change_due=0,
    )
    session.add(sale)
    session.flush()

    session.add(
        SaleItem(
            sale_id=sale.id,
            batch_id=batch.id,
            quantity=5,
            unit_price=120.00,
            unit_cost=100.00,  # copied from batch.purchase_price at time of sale
            line_discount=0,
        )
    )

    previous_qty = batch.quantity
    batch.quantity = previous_qty - 5
    session.add(
        StockTransaction(
            batch_id=batch.id,
            txn_type=StockTxnType.SALE,
            quantity=-5,
            previous_quantity=previous_qty,
            new_quantity=batch.quantity,
            reference=sale.invoice_number,
            user_id=admin.id,
            reason="Demo seed sale",
        )
    )

    print("Inserted demo data: 1 medicine, 1 batch, 1 purchase, 1 sale (5 units), 1 customer.")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--with-demo-data", action="store_true", help="Also insert sample catalog/sale data")
    args = parser.parse_args()

    with session_scope() as session:
        seed_permissions(session)
        admin = seed_default_admin(session)
        session.flush()
        if args.with_demo_data:
            seed_demo_catalog_data(session, admin)

    print("Seed complete.")


if __name__ == "__main__":
    main()
