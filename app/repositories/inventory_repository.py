from __future__ import annotations

from datetime import date, timedelta
from typing import Optional

from sqlalchemy import or_
from sqlalchemy.orm import Session, selectinload

from app.models import Category, Customer, Manufacturer, Medicine, MedicineBatch, Rack, Shelf, Supplier, Wardrobe
from app.repositories.base import BaseRepository


class CategoryRepository(BaseRepository[Category]):
    model = Category

    def get_or_create(self, name: str) -> Category:
        obj = self.session.query(Category).filter(Category.name == name).one_or_none()
        if obj is None:
            obj = Category(name=name)
            self.session.add(obj)
            self.session.flush()
        return obj


class ManufacturerRepository(BaseRepository[Manufacturer]):
    model = Manufacturer

    def get_or_create(self, name: str) -> Manufacturer:
        obj = self.session.query(Manufacturer).filter(Manufacturer.name == name).one_or_none()
        if obj is None:
            obj = Manufacturer(name=name)
            self.session.add(obj)
            self.session.flush()
        return obj


class MedicineRepository(BaseRepository[Medicine]):
    model = Medicine

    def get_by_barcode(self, barcode: str) -> Optional[Medicine]:
        return self.session.query(Medicine).filter(Medicine.barcode == barcode).one_or_none()

    def search(self, term: str, active_only: bool = True, limit: int = 10000) -> list[Medicine]:
        # Eager-load the full relationship tree needed after the session closes:
        #   batches → shelf → rack → wardrobe  (for location display)
        #   batches → supplier                 (for supplier name display)
        # Without this, accessing b.shelf or b.supplier on a detached instance
        # raises DetachedInstanceError.
        query = self.session.query(Medicine).options(
            selectinload(Medicine.batches).selectinload(MedicineBatch.shelf).selectinload(Shelf.rack).selectinload(Rack.wardrobe),
            selectinload(Medicine.batches).selectinload(MedicineBatch.supplier),
        )
        if active_only:
            query = query.filter(Medicine.is_active.is_(True))
        if term:
            like = f"%{term}%"
            query = query.filter(
                or_(
                    Medicine.name.ilike(like),
                    Medicine.generic_formula.ilike(like),
                    Medicine.brand_name.ilike(like),
                    Medicine.barcode.ilike(like),
                )
            )
        return query.order_by(Medicine.name).limit(limit).all()

    def list_active(self) -> list[Medicine]:
        return self.session.query(Medicine).filter(Medicine.is_active.is_(True)).order_by(Medicine.name).all()


class MedicineBatchRepository(BaseRepository[MedicineBatch]):
    model = MedicineBatch

    def get_by_medicine_and_number(self, medicine_id: int, batch_number: str) -> Optional[MedicineBatch]:
        return (
            self.session.query(MedicineBatch)
            .filter(MedicineBatch.medicine_id == medicine_id, MedicineBatch.batch_number == batch_number)
            .one_or_none()
        )

    def fefo_candidates(self, medicine_id: int, as_of: Optional[date] = None) -> list[MedicineBatch]:
        """Non-expired, in-stock batches for a medicine, earliest expiry first
        (First-Expiry-First-Out) — the default sale allocation order."""
        as_of = as_of or date.today()
        return (
            self.session.query(MedicineBatch)
            .filter(
                MedicineBatch.medicine_id == medicine_id,
                MedicineBatch.is_active.is_(True),
                MedicineBatch.quantity > 0,
                MedicineBatch.expiry_date >= as_of,
            )
            .order_by(MedicineBatch.expiry_date.asc())
            .all()
        )

    def low_stock(self) -> list[tuple[Medicine, int]]:
        """Medicines whose total active-batch quantity is at/below min_stock_level.
        Uses selectinload to avoid N+1 queries when iterating batches."""
        results = []
        medicines = (
            self.session.query(Medicine)
            .options(selectinload(Medicine.batches))
            .filter(Medicine.is_active.is_(True))
            .all()
        )
        for medicine in medicines:
            total_qty = sum(b.quantity for b in medicine.batches if b.is_active)
            if total_qty <= medicine.min_stock_level:
                results.append((medicine, total_qty))
        return results

    def expiring_within(self, days: int, as_of: Optional[date] = None) -> list[MedicineBatch]:
        as_of = as_of or date.today()
        cutoff = as_of + timedelta(days=days)
        return (
            self.session.query(MedicineBatch)
            .options(
                selectinload(MedicineBatch.medicine),
                selectinload(MedicineBatch.supplier),
                selectinload(MedicineBatch.shelf).selectinload(Shelf.rack).selectinload(Rack.wardrobe),
            )
            .filter(
                MedicineBatch.is_active.is_(True),
                MedicineBatch.quantity > 0,
                MedicineBatch.expiry_date >= as_of,
                MedicineBatch.expiry_date <= cutoff,
            )
            .order_by(MedicineBatch.expiry_date.asc())
            .all()
        )

    def expired(self, as_of: Optional[date] = None) -> list[MedicineBatch]:
        as_of = as_of or date.today()
        return (
            self.session.query(MedicineBatch)
            .options(
                selectinload(MedicineBatch.medicine),
                selectinload(MedicineBatch.supplier),
                selectinload(MedicineBatch.shelf).selectinload(Shelf.rack).selectinload(Rack.wardrobe),
            )
            .filter(MedicineBatch.is_active.is_(True), MedicineBatch.quantity > 0, MedicineBatch.expiry_date < as_of)
            .order_by(MedicineBatch.expiry_date.asc())
            .all()
        )


class LocationRepository:
    def __init__(self, session: Session):
        self.session = session

    def get_or_create_wardrobe(self, code: str) -> Wardrobe:
        obj = self.session.query(Wardrobe).filter(Wardrobe.code == code).one_or_none()
        if obj is None:
            obj = Wardrobe(code=code)
            self.session.add(obj)
            self.session.flush()
        return obj

    def get_or_create_rack(self, wardrobe: Wardrobe, code: str) -> Rack:
        obj = (
            self.session.query(Rack)
            .filter(Rack.wardrobe_id == wardrobe.id, Rack.code == code)
            .one_or_none()
        )
        if obj is None:
            obj = Rack(wardrobe_id=wardrobe.id, code=code)
            self.session.add(obj)
            self.session.flush()
        return obj

    def get_or_create_shelf(self, rack: Rack, code: str) -> Shelf:
        obj = self.session.query(Shelf).filter(Shelf.rack_id == rack.id, Shelf.code == code).one_or_none()
        if obj is None:
            obj = Shelf(rack_id=rack.id, code=code)
            self.session.add(obj)
            self.session.flush()
        return obj

    def get_or_create_full_location(self, wardrobe_code: str, rack_code: str, shelf_code: str) -> Shelf:
        wardrobe = self.get_or_create_wardrobe(wardrobe_code)
        rack = self.get_or_create_rack(wardrobe, rack_code)
        return self.get_or_create_shelf(rack, shelf_code)


class SupplierRepository(BaseRepository[Supplier]):
    model = Supplier

    def get_or_create(self, name: str, phone: Optional[str] = None) -> Supplier:
        query = self.session.query(Supplier).filter(Supplier.name == name)
        obj = query.one_or_none()
        if obj is None:
            obj = Supplier(name=name, phone=phone)
            self.session.add(obj)
            self.session.flush()
        return obj

    def list_active(self) -> list[Supplier]:
        return self.session.query(Supplier).filter(Supplier.is_active.is_(True)).order_by(Supplier.name).all()


class CustomerRepository(BaseRepository[Customer]):
    model = Customer

    def list_active(self) -> list[Customer]:
        return self.session.query(Customer).filter(Customer.is_active.is_(True)).order_by(Customer.name).all()
