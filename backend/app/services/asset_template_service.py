"""Read-only access to creation templates' code-backed cost catalogs."""

from dataclasses import dataclass
from decimal import Decimal

from app.common.exceptions import NotFoundError
from app.domain.asset_templates import ASSET_TEMPLATES
from app.domain.template_catalog import (
    MaintenanceItemTemplate,
    TimeBasedCostTemplate,
    UsageBasedCostTemplate,
)


@dataclass(frozen=True)
class TemplateCatalog:
    """The complete pickable default cost set for one creation template."""

    template_key: str
    time_based_costs: list[TimeBasedCostTemplate]
    usage_based_costs: list[UsageBasedCostTemplate]
    maintenance_items: list[MaintenanceItemTemplate]
    manual_extra_monthly_amounts: dict[str, Decimal]


class AssetTemplateService:
    """Returns the static cost catalog for a creation template. Read-only; needs no session."""

    def get_catalog(self, template_key: str) -> TemplateCatalog:
        """Resolve a template and return its ordered catalog, or 404 for an unknown key."""
        template = ASSET_TEMPLATES.get(template_key)
        if template is None:
            raise NotFoundError(f"No catalog for template '{template_key}'.")
        return TemplateCatalog(
            template_key=template_key,
            time_based_costs=list(template.catalog.time_based_costs),
            usage_based_costs=list(template.catalog.usage_based_costs),
            maintenance_items=list(template.catalog.maintenance_items),
            manual_extra_monthly_amounts=dict(template.manual_extra_monthly_amounts),
        )
