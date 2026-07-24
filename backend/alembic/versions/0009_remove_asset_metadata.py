"""remove obsolete asset metadata

Revision ID: 0009
Revises: 0008
Create Date: 2026-07-24

This migration intentionally discards every stored asset subtitle/attribute and vehicle
make/model/year value. Downgrade restores nullable column shapes only; deleted data cannot be
recovered.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision: str = "0009"
down_revision: Union[str, None] = "0008"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_column("assets", "attributes")
    op.drop_column("assets", "subtitle")
    op.drop_column("vehicle_profiles", "model")
    op.drop_column("vehicle_profiles", "make")
    op.drop_column("vehicle_profiles", "year")


def downgrade() -> None:
    op.add_column("vehicle_profiles", sa.Column("year", sa.Integer(), nullable=True))
    op.add_column("vehicle_profiles", sa.Column("make", sa.String(), nullable=True))
    op.add_column("vehicle_profiles", sa.Column("model", sa.String(), nullable=True))
    op.add_column("assets", sa.Column("subtitle", sa.String(), nullable=True))
    op.add_column(
        "assets",
        sa.Column("attributes", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )
