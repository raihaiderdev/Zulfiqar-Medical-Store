"""Add doctor_fees table and permissions

Revision ID: d4e5f6a7b8c9
Revises: c3d4e5f6a7b8
Create Date: 2026-10-25 12:00:00.000000

Adds:
  doctor_fees table

Permissions seeded:
  doctor_fees.view
  doctor_fees.record
  doctor_fees.correct
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "d4e5f6a7b8c9"
down_revision: Union[str, None] = "c3d4e5f6a7b8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "doctor_fees",
        sa.Column("id",                  sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("fee_date",            sa.Date(), nullable=False, index=True),
        sa.Column("doctor_name",         sa.String(180), nullable=False, index=True),
        sa.Column("amount",              sa.Numeric(12, 2), nullable=False),
        sa.Column("payment_method",      sa.String(32)),
        sa.Column("patient_reference",   sa.String(120)),
        sa.Column("notes",               sa.String(500)),
        sa.Column("sale_reference",      sa.String(32), index=True),
        sa.Column("status",              sa.String(16), nullable=False, server_default="ACTIVE"),
        sa.Column("created_by_user_id",  sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("created_at",          sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at",          sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("amount >= 0", name="ck_doctor_fee_amount_nonneg"),
    )

    for key, desc in [
        ("doctor_fees.view",    "View doctor fee records and daily collection summary"),
        ("doctor_fees.record",  "Record new doctor fee entries (standalone or via POS bill)"),
        ("doctor_fees.correct", "Correct or void a doctor fee entry"),
    ]:
        op.execute(
            sa.text(
                "INSERT OR IGNORE INTO permissions (key, description, admin_only) "
                f"VALUES ('{key}', '{desc}', 0)"
            )
        )


def downgrade() -> None:
    for key in ("doctor_fees.view", "doctor_fees.record", "doctor_fees.correct"):
        op.execute(sa.text(
            "DELETE FROM user_permissions WHERE permission_id IN "
            f"(SELECT id FROM permissions WHERE key = '{key}')"
        ))
        op.execute(sa.text(f"DELETE FROM permissions WHERE key = '{key}'"))
    op.drop_table("doctor_fees")
