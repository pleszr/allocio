"""Authoritative built-in House template defaults."""

from decimal import Decimal

from app.domain.template_catalog import TemplateCatalog, TimeBasedCostTemplate


DEFAULT_TIME_BASED_COSTS: tuple[TimeBasedCostTemplate, ...] = (
    TimeBasedCostTemplate(
        "building_tax",
        "Building tax",
        {"HUF": Decimal("38000"), "EUR": Decimal("95"), "USD": Decimal("106")},
        12,
        "months",
    ),
    TimeBasedCostTemplate(
        "home_insurance",
        "Home insurance",
        {"HUF": Decimal("80000"), "EUR": Decimal("200"), "USD": Decimal("222")},
        12,
        "months",
    ),
    TimeBasedCostTemplate(
        "boiler_cleaning",
        "Boiler cleaning",
        {"HUF": Decimal("35000"), "EUR": Decimal("88"), "USD": Decimal("97")},
        12,
        "months",
    ),
    TimeBasedCostTemplate(
        "air_conditioner_cleaning",
        "Air-conditioner cleaning",
        {"HUF": Decimal("45000"), "EUR": Decimal("113"), "USD": Decimal("125")},
        12,
        "months",
    ),
)

HOUSE_CATALOG = TemplateCatalog(
    time_based_costs=DEFAULT_TIME_BASED_COSTS,
    usage_based_costs=(),
    maintenance_items=(),
)
