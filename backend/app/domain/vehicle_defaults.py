"""Authoritative default vehicle templates and a deterministic selective clone builder.

The templates are pure data (no SQLAlchemy import) so the authoritative source stays
portable and versioned in git. `build_selected_rows` bridges the chosen templates to unsaved
ORM rows for one asset; the asset-creation service owns persistence when the vehicle template
is applied. `vehicle_catalog_keys` is the source of truth for which keys are pickable.

Every time-based and usage-based row carries a default amount per supported currency
(`HUF`/`EUR`/`USD`) rather than one bare number, so a bucket in any of those currencies gets a
plausible default regardless of the owner's currency. The USD and EUR figures are a rough flat
placeholder conversion of the curated HUF figures (1 USD ~= 360 HUF, 1 EUR ~= 400 HUF) — not a
live or authoritative exchange rate, and not verified market pricing for those currencies. They
exist only as an editable starting default (the caller can always override them at clone time);
review and adjust before treating them as accurate. Maintenance items have no curated cost in any
currency yet (`estimated_costs` is `None` for every row today), so none is invented here either.
"""

import uuid
from dataclasses import dataclass
from decimal import Decimal

from app.domain.cost import MaintenanceItem, TimeBasedCost, UsageBasedCost


@dataclass(frozen=True)
class TimeBasedCostTemplate:
    """Recurring time-driven cost baseline (user-editable at clone time)."""

    technical_key: str
    label: str
    amounts: dict[str, Decimal]
    interval_value: int
    interval_unit: str


@dataclass(frozen=True)
class UsageBasedCostTemplate:
    """Per-usage-unit reserve baseline; one active usage-based row per asset."""

    technical_key: str
    label: str
    amounts_per_unit: dict[str, Decimal]
    usage_unit: str


@dataclass(frozen=True)
class MaintenanceItemTemplate:
    """Tracked maintenance/replacement item baseline with optional km/month intervals."""

    technical_key: str
    label: str
    interval_km: int | None
    interval_months: int | None
    tire_type: str | None
    estimated_costs: dict[str, Decimal] | None


DEFAULT_TIME_BASED_COSTS: tuple[TimeBasedCostTemplate, ...] = (
    TimeBasedCostTemplate(
        "seasonal_tire_change",
        "Seasonal tire change",
        {"HUF": Decimal("14000"), "USD": Decimal("40"), "EUR": Decimal("35")},
        6,
        "months",
    ),
    TimeBasedCostTemplate(
        "vehicle_inspection",
        "Vehicle inspection",
        {"HUF": Decimal("40000"), "USD": Decimal("110"), "EUR": Decimal("100")},
        24,
        "months",
    ),
    TimeBasedCostTemplate(
        "mandatory_liability_insurance",
        "Mandatory liability insurance",
        {"HUF": Decimal("50119"), "USD": Decimal("140"), "EUR": Decimal("125")},
        12,
        "months",
    ),
    TimeBasedCostTemplate(
        "comprehensive_insurance",
        "Comprehensive insurance",
        {"HUF": Decimal("11650"), "USD": Decimal("32"), "EUR": Decimal("29")},
        12,
        "months",
    ),
    TimeBasedCostTemplate(
        "vehicle_tax",
        "Vehicle tax",
        {"HUF": Decimal("9570"), "USD": Decimal("27"), "EUR": Decimal("24")},
        6,
        "months",
    ),
    TimeBasedCostTemplate(
        "motorway_vignette",
        "Motorway vignette",
        {"HUF": Decimal("7190"), "USD": Decimal("20"), "EUR": Decimal("18")},
        12,
        "months",
    ),
)

DEFAULT_USAGE_BASED_COST: UsageBasedCostTemplate = UsageBasedCostTemplate(
    "usage_based_reserve",
    "Usage-based reserve",
    {"HUF": Decimal("10"), "USD": Decimal("0.03"), "EUR": Decimal("0.025")},
    "km",
)

DEFAULT_MAINTENANCE_ITEMS: tuple[MaintenanceItemTemplate, ...] = (
    MaintenanceItemTemplate("front_brake_disc", "Front brake discs", 90000, 90, None, None),
    MaintenanceItemTemplate("rear_brake_disc", "Rear brake discs", 90000, 90, None, None),
    MaintenanceItemTemplate("front_brake_pad", "Front brake pads", 45000, 36, None, None),
    MaintenanceItemTemplate("rear_brake_pad", "Rear brake pads", 45000, 45, None, None),
    MaintenanceItemTemplate("annual_service", "Annual service", 12000, 12, None, None),
    MaintenanceItemTemplate("automatic_transmission_fluid", "Automatic transmission fluid", 60000, 60, None, None),
    MaintenanceItemTemplate("fuel_filter", "Fuel filter", 45000, 36, None, None),
    MaintenanceItemTemplate("water_pump", "Water pump", 200000, 120, None, None),
    MaintenanceItemTemplate("timing_system", "Timing system", 200000, 120, None, None),
    MaintenanceItemTemplate("battery", "Battery", 100000, 60, None, None),
    MaintenanceItemTemplate("all_season_tires", "All-season tires", 50000, 36, "all_season", None),
    MaintenanceItemTemplate("winter_tires", "Winter tires", 40000, 60, "winter", None),
    MaintenanceItemTemplate("summer_tires", "Summer tires", 50000, 60, "summer", None),
    MaintenanceItemTemplate("other", "Other", None, None, None, None),
)


def vehicle_catalog_keys() -> frozenset[str]:
    """Return every pickable `technical_key` across the vehicle catalog's three groups.

    This is the validation set for a caller's selection and the single source of truth for
    "what is pickable" — the read service and the create service both derive from it.
    """
    keys = {template.technical_key for template in DEFAULT_TIME_BASED_COSTS}
    keys.add(DEFAULT_USAGE_BASED_COST.technical_key)
    keys.update(template.technical_key for template in DEFAULT_MAINTENANCE_ITEMS)
    return frozenset(keys)


def overridable_catalog_keys() -> frozenset[str]:
    """Return the `technical_key`s that accept a value/interval override at clone time.

    Only time-based costs and the usage-based reserve carry an editable amount today;
    maintenance items have no curated cost in any currency yet, so they are excluded.
    """
    keys = {template.technical_key for template in DEFAULT_TIME_BASED_COSTS}
    keys.add(DEFAULT_USAGE_BASED_COST.technical_key)
    return frozenset(keys)


def build_selected_rows(
    asset_id: uuid.UUID,
    selected_keys: set[str],
    currency: str,
    amount_overrides: dict[str, Decimal] | None = None,
    interval_overrides: dict[str, tuple[int, str]] | None = None,
) -> tuple[list[TimeBasedCost], list[UsageBasedCost], list[MaintenanceItem]]:
    """Clone only the selected default templates into unsaved ORM rows for one asset.

    A template row is cloned only when its `technical_key` is in `selected_keys`, preserving
    template order within each group. An empty `selected_keys` returns three empty lists. Each
    cloned amount is the template's default for the passed-in `currency` unless
    `amount_overrides`/`interval_overrides` supply a caller-edited value for that row's
    `technical_key`, in which case the override wins. Field mapping is deterministic; does not
    open a session or persist anything.
    """
    amount_overrides = amount_overrides or {}
    interval_overrides = interval_overrides or {}
    time_based = [
        _build_time_based_row(asset_id, template, currency, amount_overrides, interval_overrides)
        for template in DEFAULT_TIME_BASED_COSTS
        if template.technical_key in selected_keys
    ]
    usage_based: list[UsageBasedCost] = []
    if DEFAULT_USAGE_BASED_COST.technical_key in selected_keys:
        usage_based.append(
            UsageBasedCost(
                asset_id=asset_id,
                label=DEFAULT_USAGE_BASED_COST.label,
                technical_key=DEFAULT_USAGE_BASED_COST.technical_key,
                amount_per_unit=amount_overrides.get(
                    DEFAULT_USAGE_BASED_COST.technical_key, DEFAULT_USAGE_BASED_COST.amounts_per_unit[currency]
                ),
                usage_unit=DEFAULT_USAGE_BASED_COST.usage_unit,
                currency=currency,
                is_active=True,
            )
        )
    maintenance = [
        MaintenanceItem(
            asset_id=asset_id,
            label=template.label,
            technical_key=template.technical_key,
            interval_km=template.interval_km,
            interval_months=template.interval_months,
            tire_type=template.tire_type,
            estimated_cost=template.estimated_costs[currency] if template.estimated_costs else None,
            is_active=True,
        )
        for template in DEFAULT_MAINTENANCE_ITEMS
        if template.technical_key in selected_keys
    ]
    return time_based, usage_based, maintenance


def _build_time_based_row(
    asset_id: uuid.UUID,
    template: TimeBasedCostTemplate,
    currency: str,
    amount_overrides: dict[str, Decimal],
    interval_overrides: dict[str, tuple[int, str]],
) -> TimeBasedCost:
    """Clone one time-based template row, applying an amount/interval override when supplied."""
    interval_value, interval_unit = interval_overrides.get(
        template.technical_key, (template.interval_value, template.interval_unit)
    )
    return TimeBasedCost(
        asset_id=asset_id,
        label=template.label,
        technical_key=template.technical_key,
        amount=amount_overrides.get(template.technical_key, template.amounts[currency]),
        interval_value=interval_value,
        interval_unit=interval_unit,
        is_active=True,
    )
