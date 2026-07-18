"""add asset subtitle and attributes

Revision ID: 0006
Revises: 0005
Create Date: 2026-07-18

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "0006"
down_revision: Union[str, None] = "0005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("assets", sa.Column("subtitle", sa.String(), nullable=True))
    op.add_column("assets", sa.Column("attributes", postgresql.JSONB(astext_type=sa.Text()), nullable=True))


def downgrade() -> None:
    op.drop_column("assets", "attributes")
    op.drop_column("assets", "subtitle")
