"""Authoritative built-in Pet template defaults."""

from decimal import Decimal

from app.domain.template_catalog import TemplateCatalog, TimeBasedCostTemplate


DEFAULT_TIME_BASED_COSTS: tuple[TimeBasedCostTemplate, ...] = (
    TimeBasedCostTemplate(
        "pet_insurance",
        "Pet insurance",
        {"HUF": Decimal("30000"), "EUR": Decimal("75"), "USD": Decimal("83")},
        12,
        "months",
    ),
    TimeBasedCostTemplate(
        "annual_vaccinations",
        "Annual vaccinations",
        {"HUF": Decimal("20000"), "EUR": Decimal("50"), "USD": Decimal("56")},
        12,
        "months",
    ),
)

PET_CATALOG = TemplateCatalog(
    time_based_costs=DEFAULT_TIME_BASED_COSTS,
    usage_based_costs=(),
    maintenance_items=(),
)
