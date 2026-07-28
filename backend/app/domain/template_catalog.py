"""Generic code-backed template catalog structures and selective row cloning."""

import uuid
from dataclasses import dataclass
from decimal import Decimal

from app.domain.cost import MaintenanceItem, TimeBasedCost, UsageBasedCost


@dataclass(frozen=True)
class TimeBasedCostTemplate:
    """Recurring time-driven cost baseline that callers may edit while cloning."""

    technical_key: str
    label: str
    amounts: dict[str, Decimal]
    interval_value: int
    interval_unit: str


@dataclass(frozen=True)
class UsageBasedCostTemplate:
    """Per-usage-unit reserve baseline that callers may edit while cloning."""

    technical_key: str
    label: str
    amounts_per_unit: dict[str, Decimal]
    usage_unit: str


@dataclass(frozen=True)
class MaintenanceItemTemplate:
    """Tracked maintenance or replacement baseline."""

    technical_key: str
    label: str
    interval_km: int | None
    interval_months: int | None
    tire_type: str | None
    estimated_costs: dict[str, Decimal] | None


@dataclass(frozen=True)
class TemplateCatalog:
    """One template's ordered time, usage, and maintenance default rows."""

    time_based_costs: tuple[TimeBasedCostTemplate, ...]
    usage_based_costs: tuple[UsageBasedCostTemplate, ...]
    maintenance_items: tuple[MaintenanceItemTemplate, ...]


def catalog_keys(catalog: TemplateCatalog) -> frozenset[str]:
    """Return every pickable technical key in a catalog."""
    return frozenset(
        template.technical_key
        for template in (
            *catalog.time_based_costs,
            *catalog.usage_based_costs,
            *catalog.maintenance_items,
        )
    )


def overridable_catalog_keys(catalog: TemplateCatalog) -> frozenset[str]:
    """Return the time- and usage-based keys that accept clone-time overrides."""
    return frozenset(
        template.technical_key
        for template in (*catalog.time_based_costs, *catalog.usage_based_costs)
    )


def build_selected_rows(
    catalog: TemplateCatalog,
    asset_id: uuid.UUID,
    selected_keys: set[str],
    currency: str,
    amount_overrides: dict[str, Decimal] | None = None,
    interval_overrides: dict[str, tuple[int, str]] | None = None,
) -> tuple[list[TimeBasedCost], list[UsageBasedCost], list[MaintenanceItem]]:
    """Clone selected catalog rows into unsaved asset-owned rows in catalog order."""
    resolved_amounts = amount_overrides or {}
    resolved_intervals = interval_overrides or {}
    time_based = [
        _build_time_based_row(
            asset_id,
            template,
            currency,
            resolved_amounts,
            resolved_intervals,
        )
        for template in catalog.time_based_costs
        if template.technical_key in selected_keys
    ]
    usage_based = [
        UsageBasedCost(
            asset_id=asset_id,
            label=template.label,
            technical_key=template.technical_key,
            amount_per_unit=resolved_amounts.get(
                template.technical_key, template.amounts_per_unit[currency]
            ),
            usage_unit=template.usage_unit,
            currency=currency,
            is_active=True,
        )
        for template in catalog.usage_based_costs
        if template.technical_key in selected_keys
    ]
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
        for template in catalog.maintenance_items
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
    """Clone one time-based row with optional amount and interval overrides."""
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
