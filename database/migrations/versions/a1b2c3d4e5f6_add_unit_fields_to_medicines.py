"""add unit fields to medicines

Revision ID: a1b2c3d4e5f6
Revises: d00be4ff0c9d
Create Date: 2026-09-06 12:00:00.000000

Adds:
  medicines.base_unit   VARCHAR(32)   — canonical base unit (e.g. "Tablet")
  medicines.pack_unit   VARCHAR(32)   — pack/strip/box unit label
  medicines.units_per_pack  INTEGER   — how many base units in one pack unit

These columns are all nullable / have defaults so existing rows are
unaffected.  No data migration needed — existing medicines default to
units_per_pack=1 (no pack conversion) and NULL base_unit/pack_unit.
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a1b2c3d4e5f6"
down_revision: Union[str, None] = "d00be4ff0c9d"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add new columns to medicines table
    with op.batch_alter_table("medicines", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("base_unit", sa.String(length=32), nullable=True)
        )
        batch_op.add_column(
            sa.Column("pack_unit", sa.String(length=32), nullable=True)
        )
        batch_op.add_column(
            sa.Column(
                "units_per_pack",
                sa.Integer(),
                nullable=False,
                server_default="1",
            )
        )

    # Back-fill: copy existing `unit` value into `base_unit` where set
    op.execute(
        "UPDATE medicines SET base_unit = unit WHERE unit IS NOT NULL AND base_unit IS NULL"
    )


def downgrade() -> None:
    with op.batch_alter_table("medicines", schema=None) as batch_op:
        batch_op.drop_column("units_per_pack")
        batch_op.drop_column("pack_unit")
        batch_op.drop_column("base_unit")
