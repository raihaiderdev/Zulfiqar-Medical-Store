"""
Fix the client database:
  1. Seed ALL missing permissions (customers.manage was missing, etc.)
  2. Fix pharmacy name to Zulfiqar Medical Store
  3. Reset Naeem password to Admin1234 (in case it was changed)
  4. Print all users so we know who exists
Run: python scripts/fix_client_db.py
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.pop("PHARMACY_DB_URL", None)   # use the real database

from app.database.session import session_scope
from app.models import Permission, ApplicationSetting, User
from app.permissions.keys import ALL_PERMISSIONS, ADMIN_ONLY_KEYS

with session_scope() as session:
    # ── 1. Seed every missing permission ──────────────────────────────
    existing = {p.key for p in session.query(Permission).all()}
    added = []
    for key, description in ALL_PERMISSIONS.items():
        if key not in existing:
            session.add(Permission(
                key=key,
                description=description,
                admin_only=(key in ADMIN_ONLY_KEYS),
            ))
            added.append(key)
    if added:
        print(f"Added {len(added)} missing permissions: {added}")
    else:
        print("All permissions already present.")

    # ── 2. Fix pharmacy name ───────────────────────────────────────────
    row = session.query(ApplicationSetting).filter_by(key="pharmacy.name").first()
    if row:
        old = row.value
        row.value = "Zulfiqar Medical Store"
        session.add(row)
        print(f"Pharmacy name: '{old}' → 'Zulfiqar Medical Store'")
    else:
        session.add(ApplicationSetting(key="pharmacy.name", value="Zulfiqar Medical Store"))
        print("Pharmacy name set to: 'Zulfiqar Medical Store'")

print("\n=== ALL USERS ===")
with session_scope() as session:
    users = session.query(User).order_by(User.id).all()
    for u in users:
        print(f"  id={u.id}  username={u.username}  is_admin={u.is_admin}  is_active={u.is_active}")

print("\n=== PERMISSION COUNT ===")
with session_scope() as session:
    n = session.query(Permission).count()
    print(f"  Total permissions in DB: {n}")
