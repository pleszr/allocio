"""add asset.manual_extra_monthly

Revision ID: 0010
Revises: 0009
Create Date: 2026-07-25

Adds the user-adjustable manual extra monthly buffer documented in docs/domain-model.md ("Manual
extra"). NOT NULL with a server default, so the single ALTER backfills every existing asset to 0
in one statement — no separate data migration is needed.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0010"
down_revision: Union[str, None] = "0009"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "assets",
        sa.Column("manual_extra_monthly", sa.Numeric(14, 2), server_default=sa.text("0"), nullable=False),
    )


def downgrade() -> None:
    op.drop_column("assets", "manual_extra_monthly")
