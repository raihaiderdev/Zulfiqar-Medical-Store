"""
Shared enumerations. Kept as plain Python Enums stored as SQLite TEXT
(via SQLAlchemy's Enum type) so values stay human-readable in the .db file
for easier debugging/backup inspection.
"""
from __future__ import annotations

import enum


class DosageForm(str, enum.Enum):
    TABLET = "TABLET"
    CAPSULE = "CAPSULE"
    SYRUP = "SYRUP"
    INJECTION = "INJECTION"
    CREAM = "CREAM"
    OINTMENT = "OINTMENT"
    DROPS = "DROPS"
    INHALER = "INHALER"
    SACHET = "SACHET"
    SUSPENSION = "SUSPENSION"
    OTHER = "OTHER"


class StockTxnType(str, enum.Enum):
    PURCHASE = "PURCHASE"
    SALE = "SALE"
    SALE_RETURN = "SALE_RETURN"
    PURCHASE_RETURN = "PURCHASE_RETURN"
    ADJUSTMENT_IN = "ADJUSTMENT_IN"
    ADJUSTMENT_OUT = "ADJUSTMENT_OUT"
    EXPIRED = "EXPIRED"
    DAMAGED = "DAMAGED"


class PaymentStatus(str, enum.Enum):
    PAID = "PAID"
    PARTIAL = "PARTIAL"
    UNPAID = "UNPAID"


class SaleStatus(str, enum.Enum):
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"
    REFUNDED = "REFUNDED"
    PARTIALLY_REFUNDED = "PARTIALLY_REFUNDED"


class ExpenseCategoryType(str, enum.Enum):
    RENT = "RENT"
    ELECTRICITY = "ELECTRICITY"
    SALARY = "SALARY"
    TRANSPORT = "TRANSPORT"
    MAINTENANCE = "MAINTENANCE"
    OTHER = "OTHER"
