"""add paid-out-of-pocket expense funding

Revision ID: 0011
Revises: 0010
Create Date: 2026-07-25
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "0011"
down_revision: Union[str, None] = "0010"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "expense_events",
        sa.Column("paid_out_of_pocket", sa.Numeric(precision=14, scale=2), server_default="0", nullable=False),
    )
    op.create_check_constraint(
        "ck_expense_paid_out_of_pocket_nonnegative",
        "expense_events",
        "paid_out_of_pocket >= 0",
    )
    op.create_check_constraint(
        "ck_expense_paid_out_of_pocket_lte_amount",
        "expense_events",
        "paid_out_of_pocket <= amount",
    )


def downgrade() -> None:
    op.drop_constraint("ck_expense_paid_out_of_pocket_lte_amount", "expense_events", type_="check")
    op.drop_constraint("ck_expense_paid_out_of_pocket_nonnegative", "expense_events", type_="check")
    op.drop_column("expense_events", "paid_out_of_pocket")
