import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.db import Base  # noqa: E402
from app.domain import asset, check_in, cost  # noqa: E402, F401  (register mappers on Base.metadata)

EXPECTED_TABLES = {
    "assets",
    "vehicle_profiles",
    "buckets",
    "time_based_costs",
    "usage_based_costs",
    "maintenance_items",
    "check_ins",
    "allocation_events",
    "expense_events",
}


def test_all_vehicle_schema_tables_registered():
    assert EXPECTED_TABLES <= set(Base.metadata.tables)


def test_maintenance_interval_check_constraint_present():
    constraints = {constraint.name for constraint in Base.metadata.tables["maintenance_items"].constraints}
    assert "ck_maintenance_items_interval_present" in constraints


def test_vehicle_manufacture_year_is_nullable():
    assert Base.metadata.tables["vehicle_profiles"].columns["manufacture_year"].nullable is True
