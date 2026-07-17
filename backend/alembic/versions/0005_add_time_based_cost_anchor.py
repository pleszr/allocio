"""add time based cost anchor

Revision ID: 0005
Revises: 0004
Create Date: 2026-07-17

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0005"
down_revision: Union[str, None] = "0004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("time_based_costs", sa.Column("first_due_date", sa.Date(), nullable=True))


def downgrade() -> None:
    op.drop_column("time_based_costs", "first_due_date")
