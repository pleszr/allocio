"""Read-only access to a creation template's code-backed cost catalog.

Surfaces the pickable default cost rows for a template so the client can build a selection UI.
The catalog is static domain data (see `app.domain.vehicle_defaults`), so this service takes no
DB session and never mutates. Only `vehicle` carries a catalog today.
"""

from dataclasses import dataclass

from app.common.exceptions import NotFoundError
from app.domain.asset_templates import ASSET_TEMPLATES
from app.domain.vehicle_defaults import (
    DEFAULT_MAINTENANCE_ITEMS,
    DEFAULT_TIME_BASED_COSTS,
    DEFAULT_USAGE_BASED_COST,
    MaintenanceItemTemplate,
    TimeBasedCostTemplate,
    UsageBasedCostTemplate,
)


@dataclass(frozen=True)
class TemplateCatalog:
    """The complete pickable default cost set for one creation template."""

    template_key: str
    time_based_costs: list[TimeBasedCostTemplate]
    usage_based_cost: UsageBasedCostTemplate
    maintenance_items: list[MaintenanceItemTemplate]


class AssetTemplateService:
    """Returns the static cost catalog for a creation template. Read-only; needs no session."""

    def get_catalog(self, template_key: str) -> TemplateCatalog:
        """Resolve the template and return its cost catalog, or 404 when it carries none.

        An unknown key or a template without a catalog (only `vehicle` has one today) raises
        `NotFoundError`. Groups are returned in template order for a stable client shape.
        """
        template = ASSET_TEMPLATES.get(template_key)
        if template is None or not template.has_vehicle_profile:
            raise NotFoundError(f"No catalog for template '{template_key}'.")
        return self._vehicle_catalog(template_key)

    def _vehicle_catalog(self, template_key: str) -> TemplateCatalog:
        """Assemble the vehicle catalog from the code-backed default constants."""
        return TemplateCatalog(
            template_key=template_key,
            time_based_costs=list(DEFAULT_TIME_BASED_COSTS),
            usage_based_cost=DEFAULT_USAGE_BASED_COST,
            maintenance_items=list(DEFAULT_MAINTENANCE_ITEMS),
        )
