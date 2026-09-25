"""add stock.intelligence permission

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-09-24 12:00:00.000000

Adds the 'stock.intelligence' permission key for Phase 1 Smart Inventory
Intelligence features (reorder suggestions, expiry risk, dead stock,
ABC classification).

This is a data-only migration — no schema changes.
The permission row is inserted idempotently.
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "b2c3d4e5f6a7"
down_revision: Union[str, None] = "a1b2c3d4e5f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Insert the new permission row if it doesn't already exist.
    # This is safe to run on both fresh installs and existing databases.
    op.execute(
        sa.text(
            "INSERT OR IGNORE INTO permissions (key, description, admin_only) "
            "VALUES ('stock.intelligence', 'View smart reorder, expiry risk, dead stock, and analytics', 0)"
        )
    )


def downgrade() -> None:
    # Remove the permission and any grants referencing it.
    op.execute(
        sa.text(
            "DELETE FROM user_permissions WHERE permission_id IN "
            "(SELECT id FROM permissions WHERE key = 'stock.intelligence')"
        )
    )
    op.execute(
        sa.text("DELETE FROM permissions WHERE key = 'stock.intelligence'")
    )
