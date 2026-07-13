"""generalize usage-unit columns so the accrual path is asset-agnostic

Revision ID: 0004
Revises: 0003
Create Date: 2026-07-13

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0004"
down_revision: Union[str, None] = "0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column("usage_based_costs", "amount_per_km", new_column_name="amount_per_unit")
    op.add_column(
        "usage_based_costs",
        sa.Column("usage_unit", sa.String(), server_default=sa.text("'km'"), nullable=False),
    )

    op.alter_column("check_ins", "odometer_start", new_column_name="usage_start", nullable=True)
    op.alter_column("check_ins", "odometer_end", new_column_name="usage_end", nullable=True)
    op.alter_column("check_ins", "usage_km", new_column_name="usage_amount", nullable=True)

    op.alter_column("expense_events", "odometer_at_event", new_column_name="usage_counter_at_event")


def downgrade() -> None:
    op.alter_column("expense_events", "usage_counter_at_event", new_column_name="odometer_at_event")

    op.alter_column("check_ins", "usage_amount", new_column_name="usage_km", nullable=False)
    op.alter_column("check_ins", "usage_end", new_column_name="odometer_end", nullable=False)
    op.alter_column("check_ins", "usage_start", new_column_name="odometer_start", nullable=False)

    op.drop_column("usage_based_costs", "usage_unit")
    op.alter_column("usage_based_costs", "amount_per_unit", new_column_name="amount_per_km")
