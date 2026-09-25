"""Phase 2 — purchase orders, cashier shifts, new permissions

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a7
Create Date: 2026-09-24 13:00:00.000000

Adds:
  purchase_orders
  purchase_order_items
  purchase_order_receipts
  purchase_order_receipt_items
  cashier_shifts

Also seeds three new permission rows:
  purchase_orders.create
  purchase_orders.approve
  purchase_orders.receive
  shifts.manage
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "c3d4e5f6a7b8"
down_revision: Union[str, None] = "b2c3d4e5f6a7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── purchase_orders ────────────────────────────────────────────────────
    op.create_table(
        "purchase_orders",
        sa.Column("id",                     sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("supplier_id",            sa.Integer(), sa.ForeignKey("suppliers.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("po_number",              sa.String(32), nullable=False, unique=True),
        sa.Column("order_date",             sa.Date(), nullable=False),
        sa.Column("expected_delivery_date", sa.Date()),
        sa.Column("status",                 sa.String(24), nullable=False, server_default="DRAFT"),
        sa.Column("notes",                  sa.Text()),
        sa.Column("created_by_user_id",     sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("approved_by_user_id",    sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("created_at",             sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at",             sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_po_supplier",  "purchase_orders", ["supplier_id"])
    op.create_index("ix_po_status",    "purchase_orders", ["status"])
    op.create_index("ix_po_number",    "purchase_orders", ["po_number"])

    # ── purchase_order_items ───────────────────────────────────────────────
    op.create_table(
        "purchase_order_items",
        sa.Column("id",                 sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("purchase_order_id",  sa.Integer(), sa.ForeignKey("purchase_orders.id", ondelete="CASCADE"), nullable=False),
        sa.Column("medicine_id",        sa.Integer(), sa.ForeignKey("medicines.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("ordered_quantity",   sa.Integer(), nullable=False),
        sa.Column("unit_price",         sa.Numeric(12, 2), nullable=False),
        sa.Column("notes",              sa.String(255)),
        sa.Column("created_at",         sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at",         sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("ordered_quantity > 0", name="ck_poi_qty_positive"),
    )
    op.create_index("ix_poi_po", "purchase_order_items", ["purchase_order_id"])

    # ── purchase_order_receipts ────────────────────────────────────────────
    op.create_table(
        "purchase_order_receipts",
        sa.Column("id",                    sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("purchase_order_id",     sa.Integer(), sa.ForeignKey("purchase_orders.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("purchase_id",           sa.Integer(), sa.ForeignKey("purchases.id", ondelete="SET NULL")),
        sa.Column("received_date",         sa.Date(), nullable=False),
        sa.Column("received_by_user_id",   sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("notes",                 sa.String(500)),
        sa.Column("created_at",            sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at",            sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_por_po", "purchase_order_receipts", ["purchase_order_id"])

    # ── purchase_order_receipt_items ───────────────────────────────────────
    op.create_table(
        "purchase_order_receipt_items",
        sa.Column("id",                 sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("receipt_id",         sa.Integer(), sa.ForeignKey("purchase_order_receipts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("po_item_id",         sa.Integer(), sa.ForeignKey("purchase_order_items.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("received_quantity",  sa.Integer(), nullable=False),
        sa.Column("batch_number",       sa.String(64), nullable=False),
        sa.Column("purchase_price",     sa.Numeric(12, 2), nullable=False),
        sa.Column("selling_price",      sa.Numeric(12, 2), nullable=False),
        sa.Column("expiry_date",        sa.Date(), nullable=False),
        sa.Column("created_at",         sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at",         sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("received_quantity > 0", name="ck_pori_qty_positive"),
    )

    # ── cashier_shifts ─────────────────────────────────────────────────────
    op.create_table(
        "cashier_shifts",
        sa.Column("id",                   sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("cashier_id",           sa.Integer(), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("opened_at",            sa.DateTime(timezone=True), nullable=False),
        sa.Column("closed_at",            sa.DateTime(timezone=True)),
        sa.Column("status",               sa.String(8), nullable=False, server_default="OPEN"),
        sa.Column("opening_cash",         sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("actual_closing_cash",  sa.Numeric(12, 2)),
        sa.Column("notes",                sa.Text()),
        sa.Column("created_at",           sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at",           sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_shift_cashier", "cashier_shifts", ["cashier_id"])
    op.create_index("ix_shift_status",  "cashier_shifts", ["status"])

    for key, desc in [
        ("purchase_orders.create",  "Create draft purchase orders"),
        ("purchase_orders.approve", "Approve purchase orders"),
        ("purchase_orders.receive", "Receive goods against a purchase order"),
        ("shifts.manage",           "Open and close cashier shifts"),
    ]:
        op.execute(
            sa.text(
                "INSERT OR IGNORE INTO permissions (key, description, admin_only) "
                f"VALUES ('{key}', '{desc}', 0)"
            )
        )


def downgrade() -> None:
    for key in ("purchase_orders.create", "purchase_orders.approve",
                "purchase_orders.receive", "shifts.manage"):
        op.execute(sa.text(
            "DELETE FROM user_permissions WHERE permission_id IN "
            f"(SELECT id FROM permissions WHERE key = '{key}')"
        ))
        op.execute(sa.text(f"DELETE FROM permissions WHERE key = '{key}'"))

    op.drop_table("purchase_order_receipt_items")
    op.drop_table("purchase_order_receipts")
    op.drop_table("purchase_order_items")
    op.drop_table("purchase_orders")
    op.drop_table("cashier_shifts")
