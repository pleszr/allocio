"""Authoritative default vehicle templates and a deterministic clone builder.

The templates are pure data (no SQLAlchemy import) so the authoritative source stays
portable and versioned in git. `build_default_rows` bridges them to unsaved ORM rows for
one asset; the asset-creation service owns persistence when the vehicle template is applied.
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
    """Per-kilometer reserve baseline; one active usage-based row per asset."""

    technical_key: str
    label: str
    amount_per_km: Decimal
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
    "usage_based_reserve", "Usage-based reserve", Decimal("10"), "HUF"
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


def build_default_rows(
    asset_id: uuid.UUID,
) -> tuple[list[TimeBasedCost], list[UsageBasedCost], list[MaintenanceItem]]:
    """Clone the default templates into unsaved ORM rows for one asset.

    Returns time-based, usage-based, and maintenance rows in template order with identical
    field values on every call. Does not open a session or persist anything.
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
    ]
    usage_based = [
        UsageBasedCost(
            asset_id=asset_id,
            label=DEFAULT_USAGE_BASED_COST.label,
            technical_key=DEFAULT_USAGE_BASED_COST.technical_key,
            amount_per_km=DEFAULT_USAGE_BASED_COST.amount_per_km,
            currency=DEFAULT_USAGE_BASED_COST.currency,
            is_active=True,
        )
    ]
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
    ]
    return time_based, usage_based, maintenance
