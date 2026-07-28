"""Built-in asset templates and their code-backed creation defaults.

A template names an asset type and declares what a fresh asset inherits when the user selects
it at creation time. Each registry entry owns its catalog and editable per-currency monthly
manual-extra defaults.
"""

from dataclasses import dataclass
from decimal import Decimal

from app.domain.house_defaults import HOUSE_CATALOG
from app.domain.template_catalog import TemplateCatalog
from app.domain.vehicle_defaults import VEHICLE_CATALOG


@dataclass(frozen=True)
class AssetTemplate:
    """A selectable creation preset and all code-backed defaults it supplies."""

    key: str
    asset_type: str
    has_vehicle_profile: bool
    catalog: TemplateCatalog
    manual_extra_monthly_amounts: dict[str, Decimal]


VEHICLE_TEMPLATE = AssetTemplate(
    key="vehicle",
    asset_type="vehicle",
    has_vehicle_profile=True,
    catalog=VEHICLE_CATALOG,
    manual_extra_monthly_amounts={
        "HUF": Decimal("0"),
        "EUR": Decimal("0"),
        "USD": Decimal("0"),
    },
)
HOUSE_TEMPLATE = AssetTemplate(
    key="house",
    asset_type="house",
    has_vehicle_profile=False,
    catalog=HOUSE_CATALOG,
    manual_extra_monthly_amounts={
        "HUF": Decimal("18000"),
        "EUR": Decimal("45"),
        "USD": Decimal("50"),
    },
)

ASSET_TEMPLATES: dict[str, AssetTemplate] = {
    VEHICLE_TEMPLATE.key: VEHICLE_TEMPLATE,
    HOUSE_TEMPLATE.key: HOUSE_TEMPLATE,
}
