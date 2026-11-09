"""Test Naeem login and simulate a sale to find the exact failure point."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.pop("PHARMACY_DB_URL", None)

from app.services import auth_service, medicine_service, sales_service
from app.security.session_context import current_session

print("=== Testing Naeem_Adil / Naeem login ===")

# Try the username as stored in the DB
for username in ["Naeem", "Naeem_Adil"]:
    for password in ["Admin1234", "admin1234", "Naeem1234", "12345678"]:
        try:
            auth_service.login(username, password)
            print(f"  SUCCESS: {username} / {password}")
            print(f"  is_admin={current_session.is_admin}")
            print(f"  has sales.create: {current_session.has_permission('sales.create')}")
            auth_service.logout()
            break
        except Exception:
            pass
    else:
        print(f"  All passwords failed for {username}")

print("\n=== Checking if sale service can be called with Naeem ===")
# Check if any medicine+batch exists for a test sale
try:
    from app.database.session import session_scope
    from app.models import MedicineBatch, Medicine
    from sqlalchemy import func
    with session_scope() as session:
        batch_count = session.query(func.count(MedicineBatch.id)).filter(
            MedicineBatch.quantity > 0,
            MedicineBatch.is_active == True
        ).scalar()
        print(f"  Active batches with stock: {batch_count}")
except Exception as e:
    print(f"  DB query failed: {e}")
