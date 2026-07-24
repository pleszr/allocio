"""add user settings columns (default_currency, language)

Revision ID: 0008
Revises: 0007
Create Date: 2026-07-23

Adds the two workspace-wide preference columns the settings panel (#67) edits. Both are NOT NULL
with a server default, so the single ALTER backfills every existing row (dev user included) in one
statement — no separate data migration is needed.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0008"
down_revision: Union[str, None] = "0007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("default_currency", sa.String(length=3), server_default=sa.text("'HUF'"), nullable=False),
    )
    op.add_column(
        "users",
        sa.Column("language", sa.String(length=16), server_default=sa.text("'en'"), nullable=False),
    )


def downgrade() -> None:
    op.drop_column("users", "language")
    op.drop_column("users", "default_currency")
