"""create greetings table and seed hello world

Revision ID: 0001
Revises:
Create Date: 2026-05-12

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "greetings",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("message", sa.String(), nullable=False),
    )
    op.bulk_insert(
        sa.table(
            "greetings",
            sa.column("id", sa.Integer),
            sa.column("message", sa.String),
        ),
        [{"id": 1, "message": "hello world"}],
    )


def downgrade() -> None:
    op.drop_table("greetings")
