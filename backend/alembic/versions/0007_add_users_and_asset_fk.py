"""add users table and asset.user_id foreign key

Revision ID: 0007
Revises: 0006
Create Date: 2026-07-23

Fresh-DB migration: no data backfill. The dev database is recreated before applying it.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "0007"
down_revision: Union[str, None] = "0006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("google_sub", sa.String(), nullable=False),
        sa.Column("email", sa.String(), nullable=False),
        sa.Column("name", sa.String(), server_default=sa.text("''"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("google_sub"),
    )
    op.create_foreign_key("fk_assets_user_id_users", "assets", "users", ["user_id"], ["id"])


def downgrade() -> None:
    op.drop_constraint("fk_assets_user_id_users", "assets", type_="foreignkey")
    op.drop_table("users")
