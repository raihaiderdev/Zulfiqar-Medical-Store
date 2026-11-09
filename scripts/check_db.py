"""Quick DB diagnostics — run from project root."""
import sqlite3, sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

con = sqlite3.connect("database/pharmacy.db")
cur = con.cursor()

print("=== USERS ===")
cur.execute("SELECT id, username, is_admin, is_active FROM users")
for u in cur.fetchall():
    print(f"  {u}")

print("\n=== ALEMBIC VERSION ===")
cur.execute("SELECT version_num FROM alembic_version")
print(f"  {cur.fetchone()}")

print("\n=== PERMISSIONS IN DB ===")
cur.execute("SELECT key FROM permissions ORDER BY key")
perms = [r[0] for r in cur.fetchall()]
print(f"  Total: {len(perms)}")
for p in perms:
    print(f"  {p}")

print("\n=== TABLES ===")
cur.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
for r in cur.fetchall():
    print(f"  {r[0]}")

con.close()

# Now test the actual login + permission check
print("\n=== LOGIN TEST ===")
os.environ.pop("PHARMACY_DB_URL", None)
from app.services import auth_service
from app.security.session_context import current_session
try:
    auth_service.login("testing", "Admin1234")
    print(f"  Logged in: {current_session.username}  is_admin={current_session.is_admin}")
    print(f"  Has sales.create: {current_session.has_permission('sales.create')}")
    print(f"  Has doctor_fees.record: {current_session.has_permission('doctor_fees.record')}")
    auth_service.logout()
except Exception as e:
    print(f"  FAILED: {e}")
