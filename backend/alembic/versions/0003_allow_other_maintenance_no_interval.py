"""allow the Other catch-all maintenance item to have no interval

Revision ID: 0003
Revises: 0002
Create Date: 2026-07-12

"""
from typing import Sequence, Union

from alembic import op

revision: str = "0003"
down_revision: Union[str, None] = "0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_CONSTRAINT = "ck_maintenance_items_interval_present"
_WITH_OTHER = "interval_km IS NOT NULL OR interval_months IS NOT NULL OR technical_key = 'other'"
_WITHOUT_OTHER = "interval_km IS NOT NULL OR interval_months IS NOT NULL"


def upgrade() -> None:
    op.drop_constraint(_CONSTRAINT, "maintenance_items", type_="check")
    op.create_check_constraint(_CONSTRAINT, "maintenance_items", _WITH_OTHER)


def downgrade() -> None:
    op.drop_constraint(_CONSTRAINT, "maintenance_items", type_="check")
    op.create_check_constraint(_CONSTRAINT, "maintenance_items", _WITHOUT_OTHER)
