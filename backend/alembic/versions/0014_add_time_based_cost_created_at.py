"""add time_based_costs.created_at

Records when each recurring cost row was created so a next-due date can be derived from it when the
row carries no explicit anchor. Existing rows are backfilled from their asset's creation time, a
closer estimate of when the cost's cycle began than the migration run time.

Revision ID: 0014
Revises: 0013
Create Date: 2026-08-16
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "0014"
down_revision: Union[str, None] = "0013"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "time_based_costs",
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.execute(
        "UPDATE time_based_costs t SET created_at = a.created_at FROM assets a WHERE t.asset_id = a.id"
    )


def downgrade() -> None:
    op.drop_column("time_based_costs", "created_at")
