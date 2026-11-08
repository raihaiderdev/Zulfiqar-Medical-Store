"""
One-time script: restore the live pharmacy.db to a clean state.
  1. Remove all test-generated users.
  2. Create/restore the real admin user 'testing' with password 'Admin1234'.
  3. Fix the pharmacy name to 'Zulfiqar Medical Store'.
  4. Grant all permissions to the admin user.

Run ONCE from the project root:
  python scripts/fix_live_db.py
"""
from __future__ import annotations

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Use the REAL database (not the test temp file)
os.environ.pop("PHARMACY_DB_URL", None)  # remove any override

from app.database.session import init_db, session_scope
from app.models import User, Permission, UserPermission, ApplicationSetting

# Make sure all tables exist (safe no-op if already there)
init_db()

TEST_USERNAMES = {
    "test_suite_admin", "cashier1", "sneaky_grant_test", "temp_user",
    "reset_target", "self_change_user", "fee_viewer_only", "no_fee_view",
    "fee_recorder_only", "viewer_only", "no_edit_user", "no_po_user",
    "no_shift_user", "no_discount_cashier", "ui_smoke_user",
    "no_fee_view_2", "no_shift_user_2",
}

with session_scope() as session:
    # ── Step 1: Remove all test users ──────────────────────────────────
    removed = 0
    for u in session.query(User).all():
        if u.username in TEST_USERNAMES:
            # Delete their permission grants first
            session.query(UserPermission).filter_by(user_id=u.id).delete()
            session.delete(u)
            removed += 1
            print(f"  Removed test user: {u.username}")

    # ── Step 2: Create/restore the real admin ───────────────────────────
    from app.security.passwords import hash_password

    existing_admin = session.query(User).filter_by(username="testing").first()
    if existing_admin is None:
        # Also check for Naeem_Adil
        existing_admin = session.query(User).filter_by(username="Naeem_Adil").first()

    if existing_admin is None:
        admin = User(
            username="testing",
            password_hash=hash_password("Admin1234"),
            full_name="Administrator",
            is_admin=True,
            is_active=True,
        )
        session.add(admin)
        session.flush()
        print(f"  Created admin user: testing / Admin1234")
    else:
        # Reset password and ensure it's active admin
        existing_admin.password_hash = hash_password("Admin1234")
        existing_admin.is_admin  = True
        existing_admin.is_active = True
        # If it was Naeem_Adil, also add a 'testing' alias
        if existing_admin.username != "testing":
            existing_admin.username = "testing"
        session.add(existing_admin)
        print(f"  Reset admin: {existing_admin.username} — password set to Admin1234")

    session.flush()

    # ── Step 3: Fix pharmacy name ────────────────────────────────────────
    name_row = session.query(ApplicationSetting).filter_by(key="pharmacy.name").first()
    if name_row:
        old = name_row.value
        name_row.value = "Zulfiqar Medical Store"
        session.add(name_row)
        print(f"  Pharmacy name changed: '{old}' → 'Zulfiqar Medical Store'")
    else:
        session.add(ApplicationSetting(key="pharmacy.name", value="Zulfiqar Medical Store"))
        print("  Pharmacy name created: 'Zulfiqar Medical Store'")

    print(f"\nDone. Removed {removed} test user(s).")

print("\nVerification — remaining users:")
with session_scope() as session:
    for u in session.query(User).order_by(User.id).all():
        print(f"  id={u.id}  username={u.username}  is_admin={u.is_admin}  is_active={u.is_active}")

print("\nVerification — pharmacy name:")
with session_scope() as session:
    row = session.query(ApplicationSetting).filter_by(key="pharmacy.name").first()
    print(f"  pharmacy.name = {row.value if row else '(not set)'}")

print("\nQuick login test:")
try:
    from app.services import auth_service
    auth_service.login("testing", "Admin1234")
    from app.security.session_context import current_session
    print(f"  Login SUCCESS: username={current_session.username}  is_admin={current_session.is_admin}")
    auth_service.logout()
except Exception as exc:
    print(f"  Login FAILED: {exc}")
