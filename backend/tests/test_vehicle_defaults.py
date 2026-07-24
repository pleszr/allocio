import sys
import uuid
from decimal import Decimal
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.domain.vehicle_defaults import (  # noqa: E402
    DEFAULT_MAINTENANCE_ITEMS,
    DEFAULT_TIME_BASED_COSTS,
    DEFAULT_USAGE_BASED_COST,
    build_selected_rows,
    vehicle_catalog_keys,
)


def test_template_counts():
    assert len(DEFAULT_TIME_BASED_COSTS) == 6
    assert len(DEFAULT_MAINTENANCE_ITEMS) == 14


def test_technical_key_uniqueness_within_each_group():
    time_keys = [t.technical_key for t in DEFAULT_TIME_BASED_COSTS]
    assert len(set(time_keys)) == len(time_keys)
    maintenance_keys = [m.technical_key for m in DEFAULT_MAINTENANCE_ITEMS]
    assert len(set(maintenance_keys)) == len(maintenance_keys)


def test_every_template_has_non_empty_label_and_technical_key():
    for template in (*DEFAULT_TIME_BASED_COSTS, DEFAULT_USAGE_BASED_COST, *DEFAULT_MAINTENANCE_ITEMS):
        assert template.label
        assert template.technical_key


def test_time_based_rows_use_months_unit():
    assert all(t.interval_unit == "months" for t in DEFAULT_TIME_BASED_COSTS)


def test_usage_based_reserve_shape():
    assert DEFAULT_USAGE_BASED_COST.currency == "HUF"
    assert DEFAULT_USAGE_BASED_COST.amount_per_unit == Decimal("10")
    assert DEFAULT_USAGE_BASED_COST.usage_unit == "km"


def test_comprehensive_insurance_present_as_single_key():
    keys = [t.technical_key for t in DEFAULT_TIME_BASED_COSTS]
    assert keys.count("comprehensive_insurance") == 1


def test_tire_rows_map_to_correct_tire_type():
    by_key = {m.technical_key: m for m in DEFAULT_MAINTENANCE_ITEMS}
    assert by_key["all_season_tires"].tire_type == "all_season"
    assert by_key["winter_tires"].tire_type == "winter"
    assert by_key["summer_tires"].tire_type == "summer"


def test_annual_service_present():
    assert any(m.technical_key == "annual_service" for m in DEFAULT_MAINTENANCE_ITEMS)


def test_other_present_with_both_intervals_none():
    other = next(m for m in DEFAULT_MAINTENANCE_ITEMS if m.technical_key == "other")
    assert other.interval_km is None
    assert other.interval_months is None


def test_maintenance_interval_invariant_except_other():
    for template in DEFAULT_MAINTENANCE_ITEMS:
        if template.technical_key == "other":
            continue
        assert template.interval_km is not None or template.interval_months is not None


def test_vehicle_catalog_keys_is_frozenset_of_all_keys():
    keys = vehicle_catalog_keys()
    assert isinstance(keys, frozenset)
    assert len(keys) == 6 + 1 + 14
    assert {t.technical_key for t in DEFAULT_TIME_BASED_COSTS} <= keys
    assert DEFAULT_USAGE_BASED_COST.technical_key in keys
    assert {m.technical_key for m in DEFAULT_MAINTENANCE_ITEMS} <= keys


def test_build_selected_rows_clones_only_selected_across_groups():
    selected = {"mandatory_liability_insurance", "usage_based_reserve", "all_season_tires"}
    time_based, usage_based, maintenance = build_selected_rows(uuid.uuid4(), selected, "HUF")

    assert [r.technical_key for r in time_based] == ["mandatory_liability_insurance"]
    assert [r.technical_key for r in usage_based] == ["usage_based_reserve"]
    assert [r.technical_key for r in maintenance] == ["all_season_tires"]


def test_build_selected_rows_empty_selection_returns_three_empty_lists():
    time_based, usage_based, maintenance = build_selected_rows(uuid.uuid4(), set(), "HUF")
    assert (time_based, usage_based, maintenance) == ([], [], [])


def test_build_selected_rows_sets_asset_id_and_is_active():
    asset_id = uuid.uuid4()
    selected = {"mandatory_liability_insurance", "usage_based_reserve", "all_season_tires"}
    time_based, usage_based, maintenance = build_selected_rows(asset_id, selected, "HUF")
    for row in (*time_based, *usage_based, *maintenance):
        assert row.asset_id == asset_id
        assert row.is_active is True


def test_build_selected_rows_usage_reserve_adopts_passed_currency():
    time_based, usage_based, maintenance = build_selected_rows(uuid.uuid4(), {"usage_based_reserve"}, "EUR")
    assert usage_based[0].currency == "EUR"


def test_build_selected_rows_preserves_template_order():
    selected = {"comprehensive_insurance", "seasonal_tire_change", "vehicle_tax"}
    time_based, _, _ = build_selected_rows(uuid.uuid4(), selected, "HUF")
    # Template order is seasonal_tire_change, ..., comprehensive_insurance, vehicle_tax.
    assert [r.technical_key for r in time_based] == [
        "seasonal_tire_change",
        "comprehensive_insurance",
        "vehicle_tax",
    ]


def test_build_selected_rows_is_deterministic():
    asset_id = uuid.uuid4()
    selected = {"mandatory_liability_insurance", "usage_based_reserve", "all_season_tires"}
    first = build_selected_rows(asset_id, selected, "HUF")
    second = build_selected_rows(asset_id, selected, "HUF")

    def snapshot(groups):
        time_based, usage_based, maintenance = groups
        return (
            [(r.technical_key, r.label, r.amount, r.interval_value, r.interval_unit) for r in time_based],
            [(r.technical_key, r.label, r.amount_per_unit, r.usage_unit, r.currency) for r in usage_based],
            [
                (r.technical_key, r.label, r.interval_km, r.interval_months, r.tire_type, r.estimated_cost)
                for r in maintenance
            ],
        )

    assert snapshot(first) == snapshot(second)


def test_build_selected_rows_field_mapping_spot_checks():
    selected = {"mandatory_liability_insurance", "usage_based_reserve", "all_season_tires"}
    time_based, usage_based, maintenance = build_selected_rows(uuid.uuid4(), selected, "HUF")

    liability = next(r for r in time_based if r.technical_key == "mandatory_liability_insurance")
    assert liability.amount == Decimal("50119")
    assert liability.interval_value == 12
    assert liability.interval_unit == "months"

    reserve = usage_based[0]
    assert reserve.technical_key == "usage_based_reserve"
    assert reserve.amount_per_unit == Decimal("10")
    assert reserve.usage_unit == "km"
    assert reserve.currency == "HUF"

    all_season = next(r for r in maintenance if r.technical_key == "all_season_tires")
    assert all_season.tire_type == "all_season"
    assert all_season.interval_km == 50000
    assert all_season.interval_months == 36
