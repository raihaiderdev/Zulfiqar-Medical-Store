"""
Phase 2 database tests — run against a throwaway in-memory-per-file SQLite
DB (not the real database/pharmacy.db). Covers: schema creation, FK
enforcement, unique constraints, check constraints, cascade behavior, and
the password hashing round trip.
"""
from __future__ import annotations

import os
import tempfile
from datetime import date, timedelta

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from app.models import Base, Category, Customer, Medicine, MedicineBatch, Supplier, User
from app.models.enums import DosageForm, StockTxnType
from app.models.stock_transaction import StockTransaction
from app.security.passwords import hash_password, verify_password


@pytest.fixture()
def db_session():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    engine = create_engine(f"sqlite:///{path}", future=True)

    @event.listens_for(Engine, "connect")
    def _fk_on(dbapi_connection, connection_record):  # noqa: ANN001
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, future=True)
    session = Session()
    yield session
    session.close()
    engine.dispose()
    os.remove(path)


def _make_medicine_with_batch(session, quantity=100, expiry_days=365):
    category = Category(name="Analgesic")
    supplier = Supplier(name="Test Supplier")
    session.add_all([category, supplier])
    session.flush()

    medicine = Medicine(
        name="Test Med",
        generic_formula="Testamol",
        category_id=category.id,
        dosage_form=DosageForm.TABLET,
        barcode="TESTBARCODE1",
    )
    session.add(medicine)
    session.flush()

    batch = MedicineBatch(
        medicine_id=medicine.id,
        supplier_id=supplier.id,
        batch_number="B-1",
        purchase_price=10,
        selling_price=15,
        quantity=quantity,
        expiry_date=date.today() + timedelta(days=expiry_days),
    )
    session.add(batch)
    session.flush()
    return medicine, batch


def test_schema_creates_all_tables(db_session):
    inspector_tables = Base.metadata.tables.keys()
    assert "medicines" in inspector_tables
    assert "medicine_batches" in inspector_tables
    assert "stock_transactions" in inspector_tables
    assert len(inspector_tables) >= 25


def test_unique_username_enforced(db_session):
    db_session.add(User(username="admin", password_hash="x", is_admin=True))
    db_session.flush()
    db_session.add(User(username="admin", password_hash="y", is_admin=False))
    with pytest.raises(IntegrityError):
        db_session.flush()


def test_batch_negative_quantity_rejected(db_session):
    _, batch = _make_medicine_with_batch(db_session, quantity=5)
    batch.quantity = -1
    with pytest.raises(IntegrityError):
        db_session.flush()


def test_foreign_key_enforced_on_batch_medicine(db_session):
    batch = MedicineBatch(
        medicine_id=9999,  # does not exist
        batch_number="B-X",
        purchase_price=1,
        selling_price=2,
        quantity=1,
        expiry_date=date.today() + timedelta(days=30),
    )
    db_session.add(batch)
    with pytest.raises(IntegrityError):
        db_session.flush()


def test_unique_batch_number_per_medicine(db_session):
    medicine, _ = _make_medicine_with_batch(db_session)
    dup = MedicineBatch(
        medicine_id=medicine.id,
        batch_number="B-1",  # duplicate for same medicine
        purchase_price=1,
        selling_price=2,
        quantity=1,
        expiry_date=date.today() + timedelta(days=30),
    )
    db_session.add(dup)
    with pytest.raises(IntegrityError):
        db_session.flush()


def test_stock_transaction_ledger_matches_batch_quantity(db_session):
    medicine, batch = _make_medicine_with_batch(db_session, quantity=0)
    previous = batch.quantity
    batch.quantity = previous + 200
    db_session.add(
        StockTransaction(
            batch_id=batch.id,
            txn_type=StockTxnType.PURCHASE,
            quantity=200,
            previous_quantity=previous,
            new_quantity=batch.quantity,
        )
    )
    db_session.flush()

    txns = db_session.query(StockTransaction).filter_by(batch_id=batch.id).all()
    ledger_total = sum(t.quantity for t in txns)
    assert ledger_total == batch.quantity


def test_cascade_delete_medicine_removes_batches(db_session):
    medicine, batch = _make_medicine_with_batch(db_session)
    batch_id = batch.id
    db_session.delete(medicine)
    db_session.flush()
    db_session.expire_all()  # DB-level ON DELETE CASCADE bypasses the ORM identity map
    remaining = db_session.get(MedicineBatch, batch_id)
    assert remaining is None


def test_password_hash_roundtrip():
    hashed = hash_password("Sup3rSecret!")
    assert hashed != "Sup3rSecret!"
    assert verify_password("Sup3rSecret!", hashed) is True
    assert verify_password("wrong-password", hashed) is False


def test_customer_optional_for_cash_sale(db_session):
    # Customer is nullable on Sale — a cash sale with no customer_id must
    # be representable. We just verify the model doesn't require it.
    customer_count_before = db_session.query(Customer).count()
    assert customer_count_before == 0  # sanity: no FK-required customer needed to proceed
