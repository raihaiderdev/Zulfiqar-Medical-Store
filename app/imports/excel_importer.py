"""
Excel import pipeline (Phase 1 §9, §10). Flow: detect_columns -> user maps
columns in the UI -> preview_import (validates every row, never touches
the DB) -> commit_import (imports only after the caller has confirmed the
preview, inside one DB transaction so a mid-import failure can't leave
partial inventory changes).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any, Optional

import pandas as pd

from app.database.session import session_scope
from app.models import Medicine
from app.models.enums import DosageForm, StockTxnType
from app.repositories.inventory_repository import (
    LocationRepository,
    MedicineBatchRepository,
    MedicineRepository,
    SupplierRepository,
)
from app.security.decorators import require_permission
from app.security.session_context import current_session
from app.services import audit_service, stock_service
from app.utils.exceptions import ValidationError

# Canonical fields the importer understands. The UI maps each Excel column
# header to one of these keys — see Phase 1 §9's "Excel Column Mapping" screen.
CANONICAL_FIELDS = [
    "medicine_name", "formula", "batch_number", "purchase_price", "selling_price",
    "quantity", "expiry_date", "manufacturing_date", "wardrobe", "rack", "shelf",
    "supplier", "barcode",
]
REQUIRED_FIELDS = {"medicine_name", "batch_number", "purchase_price", "selling_price", "quantity", "expiry_date"}


@dataclass
class RowResult:
    row_number: int  # 1-based, matches the Excel sheet
    data: dict[str, Any]
    errors: list[str] = field(default_factory=list)
    is_duplicate: bool = False

    @property
    def is_valid(self) -> bool:
        return not self.errors and not self.is_duplicate


@dataclass
class ImportPreview:
    total_rows: int
    valid_rows: list[RowResult]
    invalid_rows: list[RowResult]
    duplicate_rows: list[RowResult]

    @property
    def summary(self) -> dict[str, int]:
        return {
            "total_rows": self.total_rows,
            "valid_rows": len(self.valid_rows),
            "invalid_rows": len(self.invalid_rows),
            "duplicate_rows": len(self.duplicate_rows),
        }


@dataclass
class ImportResult:
    imported_rows: int
    skipped_rows: int
    created_medicines: int
    created_batches: int


def detect_columns(file_path: str, sheet_name: int | str = 0) -> list[str]:
    df = pd.read_excel(file_path, sheet_name=sheet_name, nrows=0) if not file_path.endswith(".csv") else pd.read_csv(
        file_path, nrows=0
    )
    return list(df.columns)


def _read_dataframe(file_path: str, sheet_name: int | str = 0) -> pd.DataFrame:
    if file_path.endswith(".csv"):
        return pd.read_csv(file_path, dtype=str, keep_default_na=False)
    return pd.read_excel(file_path, sheet_name=sheet_name, dtype=str, keep_default_na=False)


def _parse_date(value: str) -> Optional[date]:
    value = (value or "").strip()
    if not value:
        return None
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%m/%d/%Y"):
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            continue
    try:
        return pd.to_datetime(value).date()
    except Exception:
        return None


def _parse_number(value: str) -> Optional[float]:
    value = (value or "").strip().replace(",", "")
    if not value:
        return None
    try:
        return float(value)
    except ValueError:
        return None


def _validate_row(row_number: int, mapped: dict[str, str]) -> RowResult:
    errors: list[str] = []
    data: dict[str, Any] = {}

    medicine_name = (mapped.get("medicine_name") or "").strip()
    if not medicine_name:
        errors.append("Missing medicine name.")
    data["medicine_name"] = medicine_name

    batch_number = (mapped.get("batch_number") or "").strip()
    if not batch_number:
        errors.append("Missing batch number.")
    data["batch_number"] = batch_number

    quantity = _parse_number(mapped.get("quantity", ""))
    if quantity is None:
        errors.append("Quantity is missing or not numeric.")
    elif quantity < 0:
        errors.append("Quantity cannot be negative.")
    data["quantity"] = int(quantity) if quantity is not None else None

    purchase_price = _parse_number(mapped.get("purchase_price", ""))
    if purchase_price is None or purchase_price < 0:
        errors.append("Purchase price is missing, not numeric, or negative.")
    data["purchase_price"] = purchase_price

    selling_price = _parse_number(mapped.get("selling_price", ""))
    if selling_price is None or selling_price < 0:
        errors.append("Selling price is missing, not numeric, or negative.")
    data["selling_price"] = selling_price

    expiry_date = _parse_date(mapped.get("expiry_date", ""))
    if expiry_date is None:
        errors.append("Expiry date is missing or unparseable.")
    elif expiry_date < date.today():
        errors.append("Expiry date is in the past.")
    data["expiry_date"] = expiry_date

    manufacturing_date = _parse_date(mapped.get("manufacturing_date", ""))
    data["manufacturing_date"] = manufacturing_date

    for optional_field in ("formula", "wardrobe", "rack", "shelf", "supplier", "barcode"):
        data[optional_field] = (mapped.get(optional_field) or "").strip() or None

    return RowResult(row_number=row_number, data=data, errors=errors)


def preview_import(file_path: str, column_mapping: dict[str, str], sheet_name: int | str = 0) -> ImportPreview:
    """
    `column_mapping` maps Excel column headers -> canonical field names,
    e.g. {"Drug Name": "medicine_name", "Qty": "quantity", ...}. Does not
    touch the database — safe to call repeatedly while the user adjusts
    the mapping in the UI.
    """
    missing_targets = REQUIRED_FIELDS - set(column_mapping.values())
    if missing_targets:
        raise ValidationError(f"Column mapping is missing required field(s): {', '.join(sorted(missing_targets))}")

    df = _read_dataframe(file_path, sheet_name)
    reverse_mapping = {excel_col: canonical for excel_col, canonical in column_mapping.items()}

    seen_keys: set[tuple[str, str]] = set()
    results: list[RowResult] = []

    for idx, row in df.iterrows():
        mapped = {canonical: row.get(excel_col, "") for excel_col, canonical in reverse_mapping.items()}
        result = _validate_row(row_number=idx + 2, mapped=mapped)  # +2: header row + 1-based

        key = (result.data.get("medicine_name", "").lower(), result.data.get("batch_number", "").lower())
        # Only flag as duplicate when BOTH key parts are non-empty AND the
        # key has already been seen.  Rows with empty name/batch are already
        # caught by _validate_row, so the all(key) guard avoids accidentally
        # marking every blank-named row as a duplicate of every other one.
        if all(key) and key in seen_keys:
            result.is_duplicate = True
        else:
            seen_keys.add(key)
        results.append(result)

    valid = [r for r in results if r.is_valid]
    invalid = [r for r in results if r.errors]
    duplicates = [r for r in results if r.is_duplicate and not r.errors]

    return ImportPreview(total_rows=len(results), valid_rows=valid, invalid_rows=invalid, duplicate_rows=duplicates)


@require_permission("medicine.import_excel")
def commit_import(preview: ImportPreview) -> ImportResult:
    """
    Imports only `preview.valid_rows`. Runs as a single DB transaction —
    per Phase 1 §10, a failure partway must not partially corrupt the
    database, so any exception here rolls back everything via
    `session_scope()`.
    """
    created_medicines = 0
    created_batches = 0

    with session_scope() as session:
        medicine_repo = MedicineRepository(session)
        batch_repo = MedicineBatchRepository(session)
        location_repo = LocationRepository(session)
        supplier_repo = SupplierRepository(session)

        for row in preview.valid_rows:
            d = row.data
            medicine = (
                session.query(Medicine)
                .filter(Medicine.name == d["medicine_name"])
                .one_or_none()
            )
            if medicine is None:
                medicine = Medicine(
                    name=d["medicine_name"],
                    generic_formula=d.get("formula"),
                    barcode=d.get("barcode") or None,
                    dosage_form=DosageForm.OTHER,
                )
                session.add(medicine)
                session.flush()
                created_medicines += 1

            if batch_repo.get_by_medicine_and_number(medicine.id, d["batch_number"]):
                continue  # already imported previously — skip rather than duplicate

            shelf = None
            if d.get("wardrobe") and d.get("rack") and d.get("shelf"):
                shelf = location_repo.get_or_create_full_location(d["wardrobe"], d["rack"], d["shelf"])

            supplier = supplier_repo.get_or_create(d["supplier"]) if d.get("supplier") else None

            from app.models import MedicineBatch

            batch = MedicineBatch(
                medicine_id=medicine.id,
                shelf_id=shelf.id if shelf else None,
                supplier_id=supplier.id if supplier else None,
                batch_number=d["batch_number"],
                purchase_price=d["purchase_price"],
                selling_price=d["selling_price"],
                quantity=0,
                manufacturing_date=d.get("manufacturing_date"),
                expiry_date=d["expiry_date"],
            )
            session.add(batch)
            session.flush()
            created_batches += 1

            if d["quantity"]:
                stock_service.apply_stock_change(
                    session,
                    batch=batch,
                    delta=d["quantity"],
                    txn_type=StockTxnType.ADJUSTMENT_IN,
                    user_id=current_session.user_id,
                    reason="Excel import",
                )

        audit_service.record(
            session,
            user_id=current_session.user_id,
            action="EXCEL_IMPORT_COMMITTED",
            entity="medicines",
            new_value={
                "imported_rows": len(preview.valid_rows),
                "created_medicines": created_medicines,
                "created_batches": created_batches,
            },
        )

    return ImportResult(
        imported_rows=len(preview.valid_rows),
        skipped_rows=preview.total_rows - len(preview.valid_rows),
        created_medicines=created_medicines,
        created_batches=created_batches,
    )
