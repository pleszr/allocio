from decimal import Decimal

from app.domain.pet_defaults import DEFAULT_TIME_BASED_COSTS, PET_CATALOG
from app.domain.template_catalog import TemplateCatalog


def test_pet_catalog_has_exact_ordered_annual_defaults() -> None:
    assert isinstance(PET_CATALOG, TemplateCatalog)
    assert [
        (
            row.technical_key,
            row.label,
            row.amounts,
            row.interval_value,
            row.interval_unit,
        )
        for row in DEFAULT_TIME_BASED_COSTS
    ] == [
        (
            "pet_insurance",
            "Pet insurance",
            {"HUF": Decimal("30000"), "EUR": Decimal("75"), "USD": Decimal("83")},
            12,
            "months",
        ),
        (
            "annual_vaccinations",
            "Annual vaccinations",
            {"HUF": Decimal("20000"), "EUR": Decimal("50"), "USD": Decimal("56")},
            12,
            "months",
        ),
    ]
    assert PET_CATALOG.time_based_costs is DEFAULT_TIME_BASED_COSTS
    assert PET_CATALOG.usage_based_costs == ()
    assert PET_CATALOG.maintenance_items == ()
