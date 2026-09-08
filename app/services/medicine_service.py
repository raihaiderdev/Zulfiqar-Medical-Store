"""
Medicine catalog + manual batch entry (Phase 1 §5, §6, §7, §11).
Purchase-driven batch creation lives in purchase_service.py instead, since
that path also has to create a Purchase/PurchaseItem and a PURCHASE-typed
stock transaction.
"""
from __future__ import annotations

from datetime import date
from typing import Optional

from app.database.session import session_scope
from app.models import Medicine, MedicineBatch
from app.models.enums import DosageForm, StockTxnType
from app.repositories.inventory_repository import (
    CategoryRepository,
    LocationRepository,
    ManufacturerRepository,
    MedicineBatchRepository,
    MedicineRepository,
    SupplierRepository,
)
from app.security.decorators import require_permission
from app.security.session_context import current_session
from app.services import audit_service, stock_service
from app.utils.exceptions import ConflictError, NotFoundError, ValidationError


@require_permission("medicine.add")
def add_medicine(
    *,
    name: str,
    generic_formula: Optional[str] = None,
    brand_name: Optional[str] = None,
    category_name: Optional[str] = None,
    manufacturer_name: Optional[str] = None,
    dosage_form: DosageForm = DosageForm.TABLET,
    strength: Optional[str] = None,
    pack_size: Optional[str] = None,
    unit: Optional[str] = None,
    base_unit: Optional[str] = None,
    pack_unit: Optional[str] = None,
    units_per_pack: int = 1,
    barcode: Optional[str] = None,
    min_stock_level: int = 10,
    reorder_level: int = 20,
    notes: Optional[str] = None,
) -> int:
    name = name.strip()
    if not name:
        raise ValidationError("Medicine name is required.")

    with session_scope() as session:
        if barcode:
            existing = MedicineRepository(session).get_by_barcode(barcode)
            if existing:
                raise ConflictError(f"Barcode '{barcode}' is already assigned to '{existing.name}'.")

        category = CategoryRepository(session).get_or_create(category_name) if category_name else None
        manufacturer = ManufacturerRepository(session).get_or_create(manufacturer_name) if manufacturer_name else None

        medicine = Medicine(
            name=name,
            generic_formula=generic_formula,
            brand_name=brand_name,
            category_id=category.id if category else None,
            manufacturer_id=manufacturer.id if manufacturer else None,
            dosage_form=dosage_form,
            strength=strength,
            pack_size=pack_size,
            unit=unit,
            barcode=barcode or None,
            min_stock_level=min_stock_level,
            reorder_level=reorder_level,
            notes=notes,
        )
        session.add(medicine)
        session.flush()

        audit_service.record(
            session,
            user_id=current_session.user_id,
            action="MEDICINE_ADDED",
            entity="medicines",
            entity_id=medicine.id,
            new_value={"name": name, "barcode": barcode},
        )
        return medicine.id


@require_permission("medicine.edit")
def edit_medicine(medicine_id: int, **fields) -> None:
    allowed = {
        "name", "generic_formula", "brand_name", "dosage_form", "strength", "pack_size",
        "unit", "base_unit", "pack_unit", "units_per_pack",
        "barcode", "min_stock_level", "reorder_level", "notes", "is_active",
    }
    unknown = set(fields) - allowed
    if unknown:
        raise ValidationError(f"Cannot edit unknown field(s): {', '.join(sorted(unknown))}")

    with session_scope() as session:
        medicine = session.get(Medicine, medicine_id)
        if medicine is None:
            raise NotFoundError(f"Medicine {medicine_id} not found.")

        old_value = {k: getattr(medicine, k) for k in fields}
        for key, value in fields.items():
            setattr(medicine, key, value)
        session.add(medicine)

        audit_service.record(
            session,
            user_id=current_session.user_id,
            action="MEDICINE_EDITED",
            entity="medicines",
            entity_id=medicine.id,
            old_value=old_value,
            new_value=fields,
        )


@require_permission("medicine.add")
def add_manual_batch(
    *,
    medicine_id: int,
    batch_number: str,
    purchase_price: float,
    selling_price: float,
    quantity: int,
    expiry_date: date,
    manufacturing_date: Optional[date] = None,
    wardrobe_code: Optional[str] = None,
    rack_code: Optional[str] = None,
    shelf_code: Optional[str] = None,
    supplier_id: Optional[int] = None,
) -> int:
    """Manual stock entry outside the purchase workflow (Phase 1 §11).
    Still fully traceable — records an ADJUSTMENT_IN stock transaction."""
    if quantity < 0:
        raise ValidationError("Initial quantity cannot be negative.")
    if purchase_price < 0 or selling_price < 0:
        raise ValidationError("Prices cannot be negative.")
    if expiry_date < date.today():
        raise ValidationError("Cannot add a batch that is already expired.")

    with session_scope() as session:
        medicine = session.get(Medicine, medicine_id)
        if medicine is None:
            raise NotFoundError(f"Medicine {medicine_id} not found.")

        batch_repo = MedicineBatchRepository(session)
        if batch_repo.get_by_medicine_and_number(medicine_id, batch_number):
            raise ConflictError(f"Batch '{batch_number}' already exists for this medicine.")

        shelf = None
        if wardrobe_code and rack_code and shelf_code:
            shelf = LocationRepository(session).get_or_create_full_location(wardrobe_code, rack_code, shelf_code)

        batch = MedicineBatch(
            medicine_id=medicine_id,
            shelf_id=shelf.id if shelf else None,
            supplier_id=supplier_id,
            batch_number=batch_number,
            purchase_price=purchase_price,
            selling_price=selling_price,
            quantity=0,  # set via stock_service below so the ledger stays authoritative
            manufacturing_date=manufacturing_date,
            expiry_date=expiry_date,
        )
        session.add(batch)
        session.flush()

        if quantity > 0:
            stock_service.apply_stock_change(
                session,
                batch=batch,
                delta=quantity,
                txn_type=StockTxnType.ADJUSTMENT_IN,
                user_id=current_session.user_id,
                reason="Manual batch entry",
            )

        audit_service.record(
            session,
            user_id=current_session.user_id,
            action="BATCH_MANUALLY_ADDED",
            entity="medicine_batches",
            entity_id=batch.id,
            new_value={"medicine_id": medicine_id, "batch_number": batch_number, "quantity": quantity},
        )
        return batch.id


@require_permission("medicine.view")
def search_medicines(term: str = "") -> list[Medicine]:
    with session_scope() as session:
        results = MedicineRepository(session).search(term)
        session.expunge_all()
        return results


@require_permission("stock.view")
def low_stock_report() -> list[dict]:
    with session_scope() as session:
        rows = MedicineBatchRepository(session).low_stock()
        return [
            {"medicine_id": m.id, "name": m.name, "current_quantity": qty, "min_stock_level": m.min_stock_level}
            for m, qty in rows
        ]


@require_permission("stock.view")
def expiry_report(warning_days: int = 90) -> dict:
    with session_scope() as session:
        repo = MedicineBatchRepository(session)
        expired = repo.expired()
        expiring = repo.expiring_within(warning_days)

        def _location(b: MedicineBatch) -> str:
            if b.shelf:
                try:
                    return b.shelf.full_location
                except Exception:
                    return ""
            return ""

        def _serialize(b: MedicineBatch) -> dict:
            return {
                "batch_id": b.id,
                "medicine_name": b.medicine.name,
                "batch_number": b.batch_number,
                "quantity": b.quantity,
                "expiry_date": b.expiry_date.isoformat(),
                "location": _location(b),
            }

        return {
            "expired": [_serialize(b) for b in expired],
            "expiring_within_days": warning_days,
            "expiring_soon": [_serialize(b) for b in expiring],
        }


@require_permission("medicine.view")
def get_medicine_detail(medicine_id: int) -> dict:
    """
    Return complete medicine info including all batch details with location
    and supplier — used by the detail panel in POS and Medicines pages (F7).
    """
    from datetime import date as _date
    from app.repositories.inventory_repository import MedicineBatchRepository
    from sqlalchemy.orm import selectinload
    from app.models.batch import MedicineBatch
    from app.models.location import Shelf, Rack, Wardrobe

    with session_scope() as session:
        # Eager-load the full relationship tree so we can safely access
        # b.shelf.rack.wardrobe and b.supplier inside this session without
        # triggering lazy loads — and so that the final dict we return
        # (plain Python, no ORM objects) is safe after the session closes.
        from sqlalchemy.orm import selectinload as _sel
        medicine = (
            session.query(Medicine)
            .options(
                _sel(Medicine.batches).selectinload(MedicineBatch.shelf)
                    .selectinload(Shelf.rack).selectinload(Rack.wardrobe),
                _sel(Medicine.batches).selectinload(MedicineBatch.supplier),
            )
            .filter(Medicine.id == medicine_id)
            .one_or_none()
        )
        if medicine is None:
            from app.utils.exceptions import NotFoundError
            raise NotFoundError(f"Medicine {medicine_id} not found.")

        today = _date.today()
        batches_data = []
        total_stock = 0

        for b in sorted(medicine.batches, key=lambda x: x.expiry_date):
            if not b.is_active:
                continue
            days_left = (b.expiry_date - today).days
            if days_left < 0:
                status = "EXPIRED"
            elif days_left <= 30:
                status = "EXPIRING VERY SOON"
            elif days_left <= 214:  # ~7 months
                status = "EXPIRING SOON"
            elif b.quantity <= 0:
                status = "OUT OF STOCK"
            else:
                status = "IN STOCK"

            # Access location INSIDE the session — all relationships are
            # already eager-loaded so this is safe.
            location = ""
            wardrobe_code = ""
            rack_code = ""
            shelf_code = ""
            if b.shelf is not None:
                try:
                    shelf_code = b.shelf.code
                    rack_code = b.shelf.rack.code if b.shelf.rack else ""
                    wardrobe_code = b.shelf.rack.wardrobe.code if (b.shelf.rack and b.shelf.rack.wardrobe) else ""
                    location = b.shelf.full_location
                except Exception:
                    pass

            supplier_name = b.supplier.name if b.supplier is not None else ""

            batches_data.append({
                "batch_id": b.id,
                "batch_number": b.batch_number,
                "quantity": b.quantity,
                "purchase_price": float(b.purchase_price),
                "selling_price": float(b.selling_price),
                "manufacturing_date": b.manufacturing_date.isoformat() if b.manufacturing_date else "",
                "expiry_date": b.expiry_date.isoformat(),
                "days_until_expiry": days_left,
                "location": location,
                "wardrobe": wardrobe_code,
                "rack": rack_code,
                "shelf": shelf_code,
                "supplier": supplier_name,
                "status": status,
            })
            total_stock += b.quantity

        if total_stock <= 0:
            overall_status = "OUT OF STOCK"
        elif total_stock <= medicine.min_stock_level:
            overall_status = "LOW STOCK"
        else:
            overall_status = "IN STOCK"

        return {
            "medicine_id": medicine.id,
            "name": medicine.name,
            "generic_formula": medicine.generic_formula or "",
            "brand_name": medicine.brand_name or "",
            "dosage_form": medicine.dosage_form.value,
            "strength": medicine.strength or "",
            "pack_size": medicine.pack_size or "",
            "base_unit": getattr(medicine, "base_unit", None) or medicine.unit or "",
            "pack_unit": getattr(medicine, "pack_unit", None) or "",
            "units_per_pack": getattr(medicine, "units_per_pack", None) or 1,
            "barcode": medicine.barcode or "",
            "min_stock_level": medicine.min_stock_level,
            "total_stock": total_stock,
            "overall_status": overall_status,
            "batches": batches_data,
        }
