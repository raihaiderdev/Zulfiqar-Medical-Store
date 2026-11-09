"""
Reset the admin password directly in the database.
Run: python scripts/reset_admin_password.py
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.pop("PHARMACY_DB_URL", None)

from app.database.session import session_scope
from app.models import User
from app.security.passwords import hash_password, verify_password

NEW_PASSWORD = "Admin1234"

with session_scope() as session:
    admins = session.query(User).filter_by(is_admin=True).all()
    for admin in admins:
        admin.password_hash = hash_password(NEW_PASSWORD)
        admin.is_active = True
        session.add(admin)
        print(f"  Reset password for: {admin.username}  →  {NEW_PASSWORD}")

print("\nVerifying passwords work:")
with session_scope() as session:
    admins = session.query(User).filter_by(is_admin=True).all()
    for admin in admins:
        ok = verify_password(NEW_PASSWORD, admin.password_hash)
        print(f"  {admin.username}: verify={ok}")

print("\nLogin test:")
from app.services import auth_service
from app.security.session_context import current_session
for admin_name in [u.username for u in admins if True]:
    pass
# Get admin username fresh
with session_scope() as s2:
    admin_user = s2.query(User).filter_by(is_admin=True).first()
    uname = admin_user.username

try:
    auth_service.login(uname, NEW_PASSWORD)
    print(f"  LOGIN SUCCESS: {current_session.username}")
    print(f"  is_admin = {current_session.is_admin}")
    print(f"  has sales.create = {current_session.has_permission('sales.create')}")
    auth_service.logout()
except Exception as e:
    print(f"  LOGIN FAILED: {e}")

print(f"\nYour login credentials:")
print(f"  Username: {uname}")
print(f"  Password: {NEW_PASSWORD}")
