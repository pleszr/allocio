"""Authoritative default vehicle templates and a deterministic selective clone builder.

The templates are pure data (no SQLAlchemy import) so the authoritative source stays
portable and versioned in git. `build_selected_rows` bridges the chosen templates to unsaved
ORM rows for one asset; the asset-creation service owns persistence when the vehicle template
is applied. `vehicle_catalog_keys` is the source of truth for which keys are pickable.
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
    amount: Decimal
    interval_value: int
    interval_unit: str


@dataclass(frozen=True)
class UsageBasedCostTemplate:
    """Per-usage-unit reserve baseline; one active usage-based row per asset."""

    technical_key: str
    label: str
    amount_per_unit: Decimal
    usage_unit: str
    currency: str


@dataclass(frozen=True)
class MaintenanceItemTemplate:
    """Tracked maintenance/replacement item baseline with optional km/month intervals."""

    technical_key: str
    label: str
    interval_km: int | None
    interval_months: int | None
    tire_type: str | None
    estimated_cost: Decimal | None


DEFAULT_TIME_BASED_COSTS: tuple[TimeBasedCostTemplate, ...] = (
    TimeBasedCostTemplate("seasonal_tire_change", "Seasonal tire change", Decimal("14000"), 6, "months"),
    TimeBasedCostTemplate("vehicle_inspection", "Vehicle inspection", Decimal("40000"), 24, "months"),
    TimeBasedCostTemplate(
        "mandatory_liability_insurance", "Mandatory liability insurance", Decimal("50119"), 12, "months"
    ),
    TimeBasedCostTemplate("comprehensive_insurance", "Comprehensive insurance", Decimal("11650"), 12, "months"),
    TimeBasedCostTemplate("vehicle_tax", "Vehicle tax", Decimal("9570"), 6, "months"),
    TimeBasedCostTemplate("motorway_vignette", "Motorway vignette", Decimal("7190"), 12, "months"),
)

DEFAULT_USAGE_BASED_COST: UsageBasedCostTemplate = UsageBasedCostTemplate(
    "usage_based_reserve", "Usage-based reserve", Decimal("10"), "km", "HUF"
)

DEFAULT_MAINTENANCE_ITEMS: tuple[MaintenanceItemTemplate, ...] = (
    MaintenanceItemTemplate("front_brake_disc", "Front brake discs", 90000, 90, None, None),
    MaintenanceItemTemplate("rear_brake_disc", "Rear brake discs", 90000, 90, None, None),
    MaintenanceItemTemplate("front_brake_pad", "Front brake pads", 45000, 45, None, None),
    MaintenanceItemTemplate("rear_brake_pad", "Rear brake pads", 45000, 45, None, None),
    MaintenanceItemTemplate("annual_service", "Annual service", 12000, 12, None, None),
    MaintenanceItemTemplate("automatic_transmission_fluid", "Automatic transmission fluid", 60000, 96, None, None),
    MaintenanceItemTemplate("fuel_filter", "Fuel filter", 45000, 36, None, None),
    MaintenanceItemTemplate("water_pump", "Water pump", 200000, 120, None, None),
    MaintenanceItemTemplate("timing_system", "Timing system", 160000, 120, None, None),
    MaintenanceItemTemplate("battery", "Battery", 100000, 60, None, None),
    MaintenanceItemTemplate("all_season_tires", "All-season tires", 50000, 36, "all_season", None),
    MaintenanceItemTemplate("winter_tires", "Winter tires", 40000, 72, "winter", None),
    MaintenanceItemTemplate("summer_tires", "Summer tires", 40000, 72, "summer", None),
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


def build_selected_rows(
    asset_id: uuid.UUID, selected_keys: set[str]
) -> tuple[list[TimeBasedCost], list[UsageBasedCost], list[MaintenanceItem]]:
    """Clone only the selected default templates into unsaved ORM rows for one asset.

    A template row is cloned only when its `technical_key` is in `selected_keys`, preserving
    template order within each group. An empty `selected_keys` returns three empty lists. Field
    mapping is deterministic; does not open a session or persist anything.
    """
    time_based = [
        TimeBasedCost(
            asset_id=asset_id,
            label=template.label,
            technical_key=template.technical_key,
            amount=template.amount,
            interval_value=template.interval_value,
            interval_unit=template.interval_unit,
            is_active=True,
        )
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
                amount_per_unit=DEFAULT_USAGE_BASED_COST.amount_per_unit,
                usage_unit=DEFAULT_USAGE_BASED_COST.usage_unit,
                currency=DEFAULT_USAGE_BASED_COST.currency,
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
            estimated_cost=template.estimated_cost,
            is_active=True,
        )
        for template in DEFAULT_MAINTENANCE_ITEMS
        if template.technical_key in selected_keys
    ]
    return time_based, usage_based, maintenance
