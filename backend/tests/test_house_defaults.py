import uuid
from decimal import Decimal

from app.domain.asset_templates import HOUSE_TEMPLATE
from app.domain.house_defaults import DEFAULT_TIME_BASED_COSTS, HOUSE_CATALOG
from app.domain.template_catalog import (
    build_selected_rows,
    catalog_keys,
    overridable_catalog_keys,
)


def test_house_catalog_has_exact_ordered_annual_defaults() -> None:
    assert [
        (
            row.technical_key,
            row.label,
            row.interval_value,
            row.interval_unit,
            row.amounts,
        )
        for row in DEFAULT_TIME_BASED_COSTS
    ] == [
        (
            "building_tax",
            "Building tax",
            12,
            "months",
            {"HUF": Decimal("38000"), "EUR": Decimal("95"), "USD": Decimal("106")},
        ),
        (
            "home_insurance",
            "Home insurance",
            12,
            "months",
            {"HUF": Decimal("80000"), "EUR": Decimal("200"), "USD": Decimal("222")},
        ),
        (
            "boiler_cleaning",
            "Boiler cleaning",
            12,
            "months",
            {"HUF": Decimal("35000"), "EUR": Decimal("88"), "USD": Decimal("97")},
        ),
        (
            "air_conditioner_cleaning",
            "Air-conditioner cleaning",
            12,
            "months",
            {"HUF": Decimal("45000"), "EUR": Decimal("113"), "USD": Decimal("125")},
        ),
    ]
    assert HOUSE_CATALOG.usage_based_costs == ()
    assert HOUSE_CATALOG.maintenance_items == ()


def test_house_template_has_exact_manual_extra_defaults() -> None:
    assert HOUSE_TEMPLATE.manual_extra_monthly_amounts == {
        "HUF": Decimal("18000"),
        "EUR": Decimal("45"),
        "USD": Decimal("50"),
    }


def test_house_catalog_key_sets_contain_only_time_based_rows() -> None:
    expected = frozenset(
        {
            "building_tax",
            "home_insurance",
            "boiler_cleaning",
            "air_conditioner_cleaning",
        }
    )
    assert catalog_keys(HOUSE_CATALOG) == expected
    assert overridable_catalog_keys(HOUSE_CATALOG) == expected


def test_house_catalog_selective_clone_uses_currency_and_overrides() -> None:
    asset_id = uuid.uuid4()
    time_based, usage_based, maintenance = build_selected_rows(
        HOUSE_CATALOG,
        asset_id,
        {"building_tax", "boiler_cleaning"},
        "EUR",
        amount_overrides={"boiler_cleaning": Decimal("99")},
        interval_overrides={"building_tax": (1, "years")},
    )

    assert usage_based == []
    assert maintenance == []
    assert [row.technical_key for row in time_based] == [
        "building_tax",
        "boiler_cleaning",
    ]
    assert time_based[0].asset_id == asset_id
    assert time_based[0].amount == Decimal("95")
    assert (time_based[0].interval_value, time_based[0].interval_unit) == (1, "years")
    assert time_based[1].amount == Decimal("99")
    assert (time_based[1].interval_value, time_based[1].interval_unit) == (12, "months")
    assert all(row.is_active for row in time_based)


def test_house_catalog_empty_selection_clones_no_rows() -> None:
    assert build_selected_rows(HOUSE_CATALOG, uuid.uuid4(), set(), "HUF") == (
        [],
        [],
        [],
    )
