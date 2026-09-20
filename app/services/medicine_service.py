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


@require_permission("medicine.view")
def find_batch(medicine_id: int, batch_number: str) -> dict | None:
    """
    Return basic info for a batch if it exists, or None if it doesn't.
    Used by AddBatchDialog to detect restock vs new batch.
    """
    with session_scope() as session:
        from sqlalchemy.orm import selectinload as _sel
        from app.models.location import Shelf, Rack, Wardrobe

        batch = (
            session.query(MedicineBatch)
            .options(
                _sel(MedicineBatch.shelf)
                    .selectinload(Shelf.rack)
                    .selectinload(Rack.wardrobe),
            )
            .filter(
                MedicineBatch.medicine_id == medicine_id,
                MedicineBatch.batch_number == batch_number,
            )
            .one_or_none()
        )
        if batch is None:
            return None

        wardrobe = rack = shelf = ""
        if batch.shelf:
            try:
                shelf    = batch.shelf.code
                rack     = batch.shelf.rack.code if batch.shelf.rack else ""
                wardrobe = batch.shelf.rack.wardrobe.code if (
                    batch.shelf.rack and batch.shelf.rack.wardrobe) else ""
            except Exception:
                pass

        return {
            "batch_id":       batch.id,
            "batch_number":   batch.batch_number,
            "quantity":       batch.quantity,
            "purchase_price": float(batch.purchase_price),
            "selling_price":  float(batch.selling_price),
            "expiry_date":    batch.expiry_date.isoformat(),
            "wardrobe":       wardrobe,
            "rack":           rack,
            "shelf":          shelf,
        }


@require_permission("medicine.add")
def add_stock_to_existing_batch(
    *,
    medicine_id: int,
    batch_number: str,
    quantity: int,
    purchase_price: Optional[float] = None,
    selling_price: Optional[float] = None,
) -> int:
    """
    Add more quantity to a batch that already exists (same batch number,
    same medicine).  Used when a new delivery arrives under the same batch
    number as a previous one.

    Optionally updates the purchase/selling price on the batch if new
    prices are provided — useful when the supplier charges a different
    price on a restock.

    Returns the batch id.
    """
    if quantity <= 0:
        raise ValidationError("Quantity to add must be positive.")

    with session_scope() as session:
        batch_repo = MedicineBatchRepository(session)
        batch = batch_repo.get_by_medicine_and_number(medicine_id, batch_number)
        if batch is None:
            raise NotFoundError(
                f"Batch '{batch_number}' not found for medicine {medicine_id}. "
                "Use Add Batch to create a new batch."
            )

        old_qty = batch.quantity

        if purchase_price is not None and purchase_price >= 0:
            batch.purchase_price = purchase_price
        if selling_price is not None and selling_price >= 0:
            batch.selling_price = selling_price
        session.add(batch)

        stock_service.apply_stock_change(
            session,
            batch=batch,
            delta=quantity,
            txn_type=StockTxnType.ADJUSTMENT_IN,
            user_id=current_session.user_id,
            reason=f"Stock restock on existing batch '{batch_number}'",
        )

        audit_service.record(
            session,
            user_id=current_session.user_id,
            action="BATCH_RESTOCKED",
            entity="medicine_batches",
            entity_id=batch.id,
            old_value={"quantity": old_qty},
            new_value={
                "quantity": old_qty + quantity,
                "added": quantity,
                "batch_number": batch_number,
                "purchase_price": float(batch.purchase_price),
                "selling_price": float(batch.selling_price),
            },
        )
        return batch.id

    # Clear expiry alert cache after restock so dashboard/inventory refresh
    try:
        from app.ui.common.expiry_alert import ExpiryAlertManager
        ExpiryAlertManager.reset_for_session()
    except Exception:
        pass


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
                "medicine_id": b.medicine_id,
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


@require_permission("medicine.edit")
def edit_batch(
    *,
    batch_id: int,
    purchase_price: Optional[float] = None,
    selling_price: Optional[float] = None,
    expiry_date: Optional[date] = None,
    wardrobe_code: Optional[str] = None,
    rack_code: Optional[str] = None,
    shelf_code: Optional[str] = None,
) -> None:
    """
    Update prices, expiry date or shelf location on an existing batch.
    Only the fields that are explicitly provided are changed — pass None
    to leave a field unchanged.
    """
    with session_scope() as session:
        batch = session.get(MedicineBatch, batch_id)
        if batch is None:
            raise NotFoundError(f"Batch {batch_id} not found.")

        old_values: dict = {}
        new_values: dict = {}

        if purchase_price is not None:
            if purchase_price < 0:
                raise ValidationError("Purchase price cannot be negative.")
            old_values["purchase_price"] = float(batch.purchase_price)
            batch.purchase_price = purchase_price
            new_values["purchase_price"] = purchase_price

        if selling_price is not None:
            if selling_price < 0:
                raise ValidationError("Selling price cannot be negative.")
            old_values["selling_price"] = float(batch.selling_price)
            batch.selling_price = selling_price
            new_values["selling_price"] = selling_price

        if expiry_date is not None:
            old_values["expiry_date"] = str(batch.expiry_date)
            batch.expiry_date = expiry_date
            new_values["expiry_date"] = str(expiry_date)

        # Update shelf location if all three codes are provided
        if wardrobe_code and rack_code and shelf_code:
            shelf = LocationRepository(session).get_or_create_full_location(
                wardrobe_code, rack_code, shelf_code
            )
            old_values["shelf_id"] = batch.shelf_id
            batch.shelf_id = shelf.id
            new_values["shelf"] = f"{wardrobe_code}/{rack_code}/{shelf_code}"

        if not new_values:
            return  # Nothing to update

        session.add(batch)
        audit_service.record(
            session,
            user_id=current_session.user_id,
            action="BATCH_EDITED",
            entity="medicine_batches",
            entity_id=batch_id,
            old_value=old_values,
            new_value=new_values,
        )

    # Expiry date changed — clear cached alert data so the expiry section
    # refreshes and no longer shows this batch if it is now in the future.
    if expiry_date is not None:
        try:
            from app.ui.common.expiry_alert import ExpiryAlertManager
            ExpiryAlertManager.reset_for_session()
        except Exception:
            pass


@require_permission("medicine.view")
def get_medicine_detail_by_batch(batch_id: int) -> dict:
    """Return price/location info for a single batch — used by EditBatchDialog."""
    with session_scope() as session:
        from sqlalchemy.orm import selectinload as _sel
        from app.models.location import Shelf, Rack, Wardrobe

        batch = (
            session.query(MedicineBatch)
            .options(
                _sel(MedicineBatch.shelf)
                    .selectinload(Shelf.rack)
                    .selectinload(Rack.wardrobe),
            )
            .filter(MedicineBatch.id == batch_id)
            .one_or_none()
        )
        if batch is None:
            raise NotFoundError(f"Batch {batch_id} not found.")

        wardrobe = rack = shelf = ""
        if batch.shelf:
            try:
                shelf    = batch.shelf.code
                rack     = batch.shelf.rack.code if batch.shelf.rack else ""
                wardrobe = batch.shelf.rack.wardrobe.code if (batch.shelf.rack and batch.shelf.rack.wardrobe) else ""
            except Exception:
                pass

        return {
            "batch_id":       batch.id,
            "batch_number":   batch.batch_number,
            "purchase_price": float(batch.purchase_price),
            "selling_price":  float(batch.selling_price),
            "expiry_date":    batch.expiry_date.isoformat(),
            "wardrobe":       wardrobe,
            "rack":           rack,
            "shelf":          shelf,
        }
