"""Simulate a complete sale to find the exact failure point."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.pop("PHARMACY_DB_URL", None)

from app.services import auth_service, sales_service
from app.database.session import session_scope
from app.models import MedicineBatch, Medicine
from sqlalchemy.orm import selectinload

# Login as Naeem
print("Logging in as Naeem / Admin1234...")
try:
    auth_service.login("Naeem", "Admin1234")
    from app.security.session_context import current_session
    print(f"  Logged in: {current_session.username}  is_admin={current_session.is_admin}")
    print(f"  has_permission('sales.create'): {current_session.has_permission('sales.create')}")
except Exception as e:
    print(f"  LOGIN FAILED: {e}")
    sys.exit(1)

# Find a medicine with stock
print("\nFinding a medicine with stock...")
with session_scope() as session:
    batch = (
        session.query(MedicineBatch)
        .options(selectinload(MedicineBatch.medicine))
        .filter(MedicineBatch.quantity > 0, MedicineBatch.is_active == True)
        .first()
    )
    if batch is None:
        print("  No stock available!")
        sys.exit(1)
    med_id = batch.medicine_id
    med_name = batch.medicine.name
    print(f"  Using: {med_name} (medicine_id={med_id}, qty={batch.quantity})")

# Try the sale
print(f"\nAttempting complete_sale for {med_name}...")
try:
    result = sales_service.complete_sale(
        lines=[{"medicine_id": med_id, "quantity": 1}],
        amount_paid=100.0,
    )
    print(f"  SUCCESS: invoice={result.invoice_number} total={result.total}")
except Exception as e:
    print(f"  FAILED: {type(e).__name__}: {e}")

auth_service.logout()
