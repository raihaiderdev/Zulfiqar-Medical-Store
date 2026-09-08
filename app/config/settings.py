"""
Central application configuration.

Reads from environment variables (see .env.example) with sane local-first
defaults so the app runs offline out of the box.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

# Project root = two levels up from this file (app/config/settings.py -> project root)
BASE_DIR = Path(__file__).resolve().parent.parent.parent

DATABASE_DIR = BASE_DIR / "database"
BACKUP_DIR = BASE_DIR / "backups"
LOG_DIR = BASE_DIR / "logs"
REPORTS_DIR = BASE_DIR / "reports"
ASSETS_DIR = BASE_DIR / "assets"

for _dir in (DATABASE_DIR, BACKUP_DIR, LOG_DIR, REPORTS_DIR):
    _dir.mkdir(parents=True, exist_ok=True)

DEFAULT_DB_PATH = DATABASE_DIR / "pharmacy.db"


@dataclass(frozen=True)
class AppSettings:
    database_url: str = os.environ.get("PHARMACY_DB_URL", f"sqlite:///{DEFAULT_DB_PATH}")
    currency: str = os.environ.get("PHARMACY_CURRENCY", "PKR")
    invoice_prefix: str = os.environ.get("PHARMACY_INVOICE_PREFIX", "INV")
    low_stock_default_threshold: int = int(os.environ.get("PHARMACY_LOW_STOCK_THRESHOLD", "10"))
    expiry_warning_days_default: int = int(os.environ.get("PHARMACY_EXPIRY_WARNING_DAYS", "90"))
    session_timeout_minutes: int = int(os.environ.get("PHARMACY_SESSION_TIMEOUT_MIN", "30"))
    backup_retention_count: int = int(os.environ.get("PHARMACY_BACKUP_RETENTION", "14"))
    max_discount_percent: float = float(os.environ.get("PHARMACY_MAX_DISCOUNT_PERCENT", "20"))
    expiry_clearance_override_enabled: bool = os.environ.get("PHARMACY_EXPIRY_CLEARANCE_OVERRIDE", "false").lower() == "true"
    app_version: str = "1.0.0"


settings = AppSettings()
