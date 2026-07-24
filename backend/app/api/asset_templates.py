"""Asset-template router: read a creation template's pickable cost catalog."""

from fastapi import APIRouter, Depends, status

from app.api.schemas.responses import (
    AssetTemplateCatalogResponse,
    TemplateMaintenanceItem,
    TemplateTimeBasedCostItem,
    TemplateUsageBasedCostItem,
)
from app.common.message_bundle import INTERNAL_ERROR
from app.services.asset_template_service import AssetTemplateService, TemplateCatalog
from app.services.dependencies import get_asset_template_service

router = APIRouter(prefix="/api", tags=["asset-templates"])


@router.get(
    "/asset-templates/{template_key}/catalog",
    summary="Read a creation template's pickable cost catalog",
    description="""Returns the complete code-backed default cost set for a creation template, grouped
    into recurring time-based costs, a usage-based reserve, and maintenance/replacement items. The
    client uses this to build a selection UI; the chosen `technical_key`s are then passed to asset
    creation. Templates without a catalog (only the vehicle template has one today) return 404.""",
    response_model=AssetTemplateCatalogResponse,
    status_code=status.HTTP_200_OK,
    responses={
        200: {"description": "The template's grouped pickable cost catalog."},
        404: {"description": "No catalog exists for this template key."},
        500: {"description": INTERNAL_ERROR},
    },
)
def get_template_catalog(
    template_key: str,
    service: AssetTemplateService = Depends(get_asset_template_service),
) -> AssetTemplateCatalogResponse:
    """Delegate to the template service and map its catalog DTO to the response model."""
    catalog = service.get_catalog(template_key)
    return _to_catalog_response(catalog)


def _to_catalog_response(catalog: TemplateCatalog) -> AssetTemplateCatalogResponse:
    """Map the service `TemplateCatalog` DTO to its response, keeping the api layer off domain types."""
    return AssetTemplateCatalogResponse(
        template_key=catalog.template_key,
        time_based_costs=[
            TemplateTimeBasedCostItem(
                technical_key=item.technical_key,
                label=item.label,
                amounts=item.amounts,
                interval_value=item.interval_value,
                interval_unit=item.interval_unit,
            )
            for item in catalog.time_based_costs
        ],
        usage_based_costs=[
            TemplateUsageBasedCostItem(
                technical_key=catalog.usage_based_cost.technical_key,
                label=catalog.usage_based_cost.label,
                amounts_per_unit=catalog.usage_based_cost.amounts_per_unit,
                usage_unit=catalog.usage_based_cost.usage_unit,
            )
        ],
        maintenance_items=[
            TemplateMaintenanceItem(
                technical_key=item.technical_key,
                label=item.label,
                interval_km=item.interval_km,
                interval_months=item.interval_months,
                tire_type=item.tire_type,
                estimated_costs=item.estimated_costs,
            )
            for item in catalog.maintenance_items
        ],
    )
