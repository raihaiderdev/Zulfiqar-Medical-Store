"""
Canonical permission keys — the single source of truth referenced by both
the seed script (which rows go into `permissions`) and the service layer
(which decorators/checks gate each action).

`ADMIN_ONLY_KEYS` are never grantable to a non-admin user, even if a stray
row exists in user_permissions — the service layer checks `user.is_admin`
first for these regardless of what's stored.
"""
from __future__ import annotations

GRANTABLE_PERMISSIONS: dict[str, str] = {
    "medicine.view": "View medicines",
    "medicine.add": "Add medicines",
    "medicine.edit": "Edit medicines",
    "medicine.import_excel": "Import medicines from Excel",
    "stock.view": "View stock levels",
    "stock.adjust": "Create manual stock adjustments",
    "stock.intelligence": "View smart reorder, expiry risk, dead stock, and analytics",
    "sales.create": "Create sales (POS)",
    "sales.view": "View sales history",
    "sales.discount": "Apply discounts at sale (capped by admin-set max %)",
    "sales.print_invoice": "Print sales invoices",
    "sales.edit_invoice": "Edit / correct a completed invoice",
    "purchases.manage": "Record and manage purchases",
    "purchase_orders.create": "Create draft purchase orders",
    "purchase_orders.approve": "Approve purchase orders",
    "purchase_orders.receive": "Receive goods against a purchase order",
    "shifts.manage": "Open and close cashier shifts",
    "customers.manage": "Manage customers",
    "suppliers.manage": "Manage suppliers",
    "reports.view": "View reports",
    "returns.process": "Process sale/purchase returns",
}

ADMIN_ONLY_PERMISSIONS: dict[str, str] = {
    "users.manage": "Create/edit/deactivate users and set permissions",
    "settings.manage": "Change application settings",
    "backup.manage": "Backup and restore the database",
    "audit_log.view": "View the audit log",
}

ALL_PERMISSIONS: dict[str, str] = {**GRANTABLE_PERMISSIONS, **ADMIN_ONLY_PERMISSIONS}
ADMIN_ONLY_KEYS: frozenset[str] = frozenset(ADMIN_ONLY_PERMISSIONS.keys())
