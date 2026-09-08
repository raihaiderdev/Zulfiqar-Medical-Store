from __future__ import annotations

from typing import Optional

from app.database.session import session_scope
from app.models import Customer, Supplier
from app.repositories.inventory_repository import CustomerRepository, SupplierRepository
from app.security.decorators import require_permission
from app.security.session_context import current_session
from app.services import audit_service
from app.utils.exceptions import NotFoundError, ValidationError


@require_permission("suppliers.manage")
def add_supplier(name: str, **fields) -> int:
    name = name.strip()
    if not name:
        raise ValidationError("Supplier name is required.")
    with session_scope() as session:
        supplier = Supplier(name=name, **fields)
        session.add(supplier)
        session.flush()
        audit_service.record(
            session, user_id=current_session.user_id, action="SUPPLIER_ADDED", entity="suppliers",
            entity_id=supplier.id, new_value={"name": name},
        )
        return supplier.id


@require_permission("suppliers.manage")
def edit_supplier(supplier_id: int, **fields) -> None:
    allowed = {"name", "company", "phone", "email", "address", "tax_registration_number", "notes"}
    unknown = set(fields) - allowed
    if unknown:
        raise ValidationError(f"Cannot edit unknown field(s): {', '.join(sorted(unknown))}")
    with session_scope() as session:
        supplier = session.get(Supplier, supplier_id)
        if supplier is None:
            raise NotFoundError(f"Supplier {supplier_id} not found.")
        old_value = {k: getattr(supplier, k) for k in fields}
        for key, value in fields.items():
            setattr(supplier, key, value)
        session.add(supplier)
        audit_service.record(
            session, user_id=current_session.user_id, action="SUPPLIER_EDITED",
            entity="suppliers", entity_id=supplier_id,
            old_value=old_value, new_value=fields,
        )


@require_permission("suppliers.manage")
def deactivate_supplier(supplier_id: int) -> None:
    with session_scope() as session:
        supplier = session.get(Supplier, supplier_id)
        if supplier is None:
            raise NotFoundError(f"Supplier {supplier_id} not found.")
        supplier.is_active = False
        session.add(supplier)
        audit_service.record(
            session, user_id=current_session.user_id, action="SUPPLIER_DEACTIVATED",
            entity="suppliers", entity_id=supplier_id,
        )


@require_permission("suppliers.manage")
def reactivate_supplier(supplier_id: int) -> None:
    with session_scope() as session:
        supplier = session.get(Supplier, supplier_id)
        if supplier is None:
            raise NotFoundError(f"Supplier {supplier_id} not found.")
        supplier.is_active = True
        session.add(supplier)
        audit_service.record(
            session, user_id=current_session.user_id, action="SUPPLIER_REACTIVATED",
            entity="suppliers", entity_id=supplier_id,
        )


@require_permission("suppliers.manage")
def list_suppliers() -> list[Supplier]:
    """Returns only active suppliers (used in dropdowns)."""
    with session_scope() as session:
        rows = SupplierRepository(session).list_active()
        session.expunge_all()
        return rows


@require_permission("suppliers.manage")
def list_all_suppliers() -> list[Supplier]:
    """Returns all suppliers including inactive (used in Suppliers page table)."""
    with session_scope() as session:
        rows = session.query(Supplier).order_by(Supplier.name).all()
        session.expunge_all()
        return rows


@require_permission("customers.manage")
def add_customer(name: str, **fields) -> int:
    name = name.strip()
    if not name:
        raise ValidationError("Customer name is required.")
    with session_scope() as session:
        customer = Customer(name=name, **fields)
        session.add(customer)
        session.flush()
        audit_service.record(
            session, user_id=current_session.user_id, action="CUSTOMER_ADDED", entity="customers",
            entity_id=customer.id, new_value={"name": name},
        )
        return customer.id


@require_permission("customers.manage")
def edit_customer(customer_id: int, **fields) -> None:
    allowed = {"name", "phone", "address", "email", "notes"}
    unknown = set(fields) - allowed
    if unknown:
        raise ValidationError(f"Cannot edit unknown field(s): {', '.join(sorted(unknown))}")
    with session_scope() as session:
        customer = session.get(Customer, customer_id)
        if customer is None:
            raise NotFoundError(f"Customer {customer_id} not found.")
        old_value = {k: getattr(customer, k) for k in fields}
        for key, value in fields.items():
            setattr(customer, key, value)
        session.add(customer)
        audit_service.record(
            session, user_id=current_session.user_id, action="CUSTOMER_EDITED",
            entity="customers", entity_id=customer_id,
            old_value=old_value, new_value=fields,
        )


@require_permission("customers.manage")
def deactivate_customer(customer_id: int) -> None:
    with session_scope() as session:
        customer = session.get(Customer, customer_id)
        if customer is None:
            raise NotFoundError(f"Customer {customer_id} not found.")
        customer.is_active = False
        session.add(customer)
        audit_service.record(
            session, user_id=current_session.user_id, action="CUSTOMER_DEACTIVATED",
            entity="customers", entity_id=customer_id,
        )


@require_permission("customers.manage")
def reactivate_customer(customer_id: int) -> None:
    with session_scope() as session:
        customer = session.get(Customer, customer_id)
        if customer is None:
            raise NotFoundError(f"Customer {customer_id} not found.")
        customer.is_active = True
        session.add(customer)
        audit_service.record(
            session, user_id=current_session.user_id, action="CUSTOMER_REACTIVATED",
            entity="customers", entity_id=customer_id,
        )


@require_permission("customers.manage")
def list_customers() -> list[Customer]:
    """Returns only active customers (used in dropdowns)."""
    with session_scope() as session:
        rows = CustomerRepository(session).list_active()
        session.expunge_all()
        return rows


@require_permission("customers.manage")
def list_all_customers() -> list[Customer]:
    """Returns all customers including inactive (used in Customers page table)."""
    with session_scope() as session:
        rows = session.query(Customer).order_by(Customer.name).all()
        session.expunge_all()
        return rows


@require_permission("customers.manage")
def customer_purchase_history(customer_id: int) -> list[dict]:
    from app.models import Sale

    with session_scope() as session:
        sales = session.query(Sale).filter(Sale.customer_id == customer_id).order_by(Sale.sale_date.desc()).all()
        return [
            {"invoice_number": s.invoice_number, "date": s.sale_date.isoformat(), "total": float(s.total)}
            for s in sales
        ]
