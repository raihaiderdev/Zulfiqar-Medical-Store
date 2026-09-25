"""
Import every model module here so that a single `from app.models import Base`
(or importing this package at all) guarantees Base.metadata is fully
populated before create_all() / Alembic autogenerate runs.
"""
from app.models.base import Base  # noqa: F401

from app.models.user import User, Permission, UserPermission  # noqa: F401
from app.models.audit_log import AuditLog  # noqa: F401
from app.models.location import Wardrobe, Rack, Shelf  # noqa: F401
from app.models.medicine import Category, Manufacturer, Medicine  # noqa: F401
from app.models.party import Supplier, Customer  # noqa: F401
from app.models.batch import MedicineBatch  # noqa: F401
from app.models.purchase import (  # noqa: F401
    Purchase,
    PurchaseItem,
    PurchaseReturn,
    PurchaseReturnItem,
)
from app.models.sale import Sale, SaleItem, SaleReturn, SaleReturnItem  # noqa: F401
from app.models.stock_transaction import StockTransaction  # noqa: F401
from app.models.expense import ExpenseCategory, Expense  # noqa: F401
from app.models.settings import ApplicationSetting, ReportSnapshot  # noqa: F401

# Phase 2 — Purchase Orders and Cashier Shifts
from app.models.purchase_order import (  # noqa: F401
    PurchaseOrder,
    PurchaseOrderItem,
    PurchaseOrderReceipt,
    PurchaseOrderReceiptItem,
    POStatus,
)
from app.models.cashier_shift import CashierShift, ShiftStatus  # noqa: F401

__all__ = [
    "Base",
    "User", "Permission", "UserPermission",
    "AuditLog",
    "Wardrobe", "Rack", "Shelf",
    "Category", "Manufacturer", "Medicine",
    "Supplier", "Customer",
    "MedicineBatch",
    "Purchase", "PurchaseItem", "PurchaseReturn", "PurchaseReturnItem",
    "Sale", "SaleItem", "SaleReturn", "SaleReturnItem",
    "StockTransaction",
    "ExpenseCategory", "Expense",
    "ApplicationSetting", "ReportSnapshot",
    # Phase 2
    "PurchaseOrder", "PurchaseOrderItem",
    "PurchaseOrderReceipt", "PurchaseOrderReceiptItem", "POStatus",
    "CashierShift", "ShiftStatus",
]
