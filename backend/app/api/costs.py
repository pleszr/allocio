"""Cost-management router: list, create, edit, and deactivate an asset's cost rows."""
import uuid

from fastapi import APIRouter, Depends, Response, status

from app.api.schemas.requests import (
    CreateMaintenanceItemRequest,
    CreateTimeBasedCostRequest,
    CreateUsageBasedCostRequest,
    UpdateMaintenanceItemRequest,
    UpdateTimeBasedCostRequest,
    UpdateUsageBasedCostRequest,
)
from app.api.schemas.responses import MaintenanceItemResponse, TimeBasedCostResponse, UsageBasedCostResponse
from app.common.message_bundle import INTERNAL_ERROR
from app.services.cost_service import CostService
from app.services.dependencies import get_cost_service, get_current_user_id

router = APIRouter(prefix="/api", tags=["costs"])


def _serialize_time_based(row, service: CostService) -> TimeBasedCostResponse:
    """Serialize a time-based cost row and attach its computed next-due date via the service."""
    base = TimeBasedCostResponse.model_validate(row)
    return base.model_copy(update={"next_due_date": service.next_due_for(row)})


@router.get(
    "/assets/{asset_id}/time-based-costs",
    summary="List an asset's time-based costs",
    description="Returns every time-based cost row for the asset, active and inactive, so a client "
    "can render the full set. Scoped to the owning user; unknown or unowned assets return 404.",
    response_model=list[TimeBasedCostResponse],
    status_code=status.HTTP_200_OK,
    responses={
        200: {"description": "All time-based cost rows for the asset."},
        404: {"description": "Asset not found."},
        500: {"description": INTERNAL_ERROR},
    },
)
def list_time_based_costs(
    asset_id: uuid.UUID,
    user_id: uuid.UUID = Depends(get_current_user_id),
    service: CostService = Depends(get_cost_service),
) -> list[TimeBasedCostResponse]:
    """Delegate to the service and serialize each row."""
    rows = service.list_time_based_costs(user_id=user_id, asset_id=asset_id)
    return [_serialize_time_based(row, service) for row in rows]


@router.post(
    "/assets/{asset_id}/time-based-costs",
    summary="Add a custom time-based cost",
    description="Creates a user-defined time-based cost row on the asset. `technical_key` stays null "
    "for custom rows. Returns the created row and its canonical `Location`.",
    response_model=TimeBasedCostResponse,
    status_code=status.HTTP_201_CREATED,
    responses={
        201: {"description": "Time-based cost row created."},
        404: {"description": "Asset not found."},
        422: {"description": "Validation error in request body."},
        500: {"description": INTERNAL_ERROR},
    },
)
def create_time_based_cost(
    asset_id: uuid.UUID,
    body: CreateTimeBasedCostRequest,
    response: Response,
    user_id: uuid.UUID = Depends(get_current_user_id),
    service: CostService = Depends(get_cost_service),
) -> TimeBasedCostResponse:
    """Delegate creation to the service and set the `Location` header on the created row."""
    row = service.create_time_based_cost(
        user_id=user_id,
        asset_id=asset_id,
        label=body.label,
        amount=body.amount,
        interval_value=body.interval_value,
        interval_unit=body.interval_unit,
        first_due_date=body.first_due_date,
        notes=body.notes,
    )
    response.headers["Location"] = f"/api/assets/{asset_id}/time-based-costs/{row.id}"
    return _serialize_time_based(row, service)


@router.patch(
    "/assets/{asset_id}/time-based-costs/{cost_id}",
    summary="Edit or deactivate a time-based cost",
    description="Partially updates a time-based cost row. Only the fields sent are applied; toggling "
    "`is_active` deactivates or reactivates the row. `technical_key` is never editable.",
    response_model=TimeBasedCostResponse,
    status_code=status.HTTP_200_OK,
    responses={
        200: {"description": "Time-based cost row updated."},
        404: {"description": "Asset or cost row not found."},
        422: {"description": "Validation error in request body."},
        500: {"description": INTERNAL_ERROR},
    },
)
def update_time_based_cost(
    asset_id: uuid.UUID,
    cost_id: uuid.UUID,
    body: UpdateTimeBasedCostRequest,
    user_id: uuid.UUID = Depends(get_current_user_id),
    service: CostService = Depends(get_cost_service),
) -> TimeBasedCostResponse:
    """Delegate a partial update, passing only the fields the client actually sent."""
    row = service.update_time_based_cost(
        user_id=user_id, asset_id=asset_id, cost_id=cost_id, changes=body.model_dump(exclude_unset=True)
    )
    return _serialize_time_based(row, service)


@router.get(
    "/assets/{asset_id}/usage-based-costs",
    summary="List an asset's usage-based costs",
    description="Returns every usage-based cost component for the asset, active and inactive, so a client "
    "can render the full set. Scoped to the owning user; unknown or unowned assets return 404.",
    response_model=list[UsageBasedCostResponse],
    status_code=status.HTTP_200_OK,
    responses={
        200: {"description": "All usage-based cost components for the asset."},
        404: {"description": "Asset not found."},
        500: {"description": INTERNAL_ERROR},
    },
)
def list_usage_based_costs(
    asset_id: uuid.UUID,
    user_id: uuid.UUID = Depends(get_current_user_id),
    service: CostService = Depends(get_cost_service),
) -> list[UsageBasedCostResponse]:
    """Delegate to the service and serialize each row."""
    rows = service.list_usage_based_costs(user_id=user_id, asset_id=asset_id)
    return [UsageBasedCostResponse.model_validate(row) for row in rows]


@router.post(
    "/assets/{asset_id}/usage-based-costs",
    summary="Add a usage-based cost component",
    description="Creates a usage-based cost component on the asset. `currency` is derived from the asset's "
    "bucket and `technical_key` stays null for user rows. Returns the created row and its canonical `Location`.",
    response_model=UsageBasedCostResponse,
    status_code=status.HTTP_201_CREATED,
    responses={
        201: {"description": "Usage-based cost component created."},
        404: {"description": "Asset or bucket not found."},
        422: {"description": "Validation error in request body."},
        500: {"description": INTERNAL_ERROR},
    },
)
def create_usage_based_cost(
    asset_id: uuid.UUID,
    body: CreateUsageBasedCostRequest,
    response: Response,
    user_id: uuid.UUID = Depends(get_current_user_id),
    service: CostService = Depends(get_cost_service),
) -> UsageBasedCostResponse:
    """Delegate creation to the service and set the `Location` header on the created row."""
    row = service.create_usage_based_cost(
        user_id=user_id,
        asset_id=asset_id,
        label=body.label,
        amount_per_unit=body.amount_per_unit,
        usage_unit=body.usage_unit,
        notes=body.notes,
    )
    response.headers["Location"] = f"/api/assets/{asset_id}/usage-based-costs/{row.id}"
    return UsageBasedCostResponse.model_validate(row)


@router.patch(
    "/assets/{asset_id}/usage-based-costs/{cost_id}",
    summary="Edit or deactivate a usage-based cost",
    description="Partially updates a usage-based cost component. Only the fields sent are applied; toggling "
    "`is_active` deactivates or reactivates the row. `technical_key` and `currency` are never editable.",
    response_model=UsageBasedCostResponse,
    status_code=status.HTTP_200_OK,
    responses={
        200: {"description": "Usage-based cost component updated."},
        404: {"description": "Asset or cost row not found."},
        422: {"description": "Validation error in request body."},
        500: {"description": INTERNAL_ERROR},
    },
)
def update_usage_based_cost(
    asset_id: uuid.UUID,
    cost_id: uuid.UUID,
    body: UpdateUsageBasedCostRequest,
    user_id: uuid.UUID = Depends(get_current_user_id),
    service: CostService = Depends(get_cost_service),
) -> UsageBasedCostResponse:
    """Delegate a partial update, passing only the fields the client actually sent."""
    row = service.update_usage_based_cost(
        user_id=user_id, asset_id=asset_id, cost_id=cost_id, changes=body.model_dump(exclude_unset=True)
    )
    return UsageBasedCostResponse.model_validate(row)


@router.get(
    "/assets/{asset_id}/maintenance-items",
    summary="List an asset's maintenance items",
    description="Returns every maintenance item row for the asset, active and inactive. Scoped to the "
    "owning user; unknown or unowned assets return 404.",
    response_model=list[MaintenanceItemResponse],
    status_code=status.HTTP_200_OK,
    responses={
        200: {"description": "All maintenance item rows for the asset."},
        404: {"description": "Asset not found."},
        500: {"description": INTERNAL_ERROR},
    },
)
def list_maintenance_items(
    asset_id: uuid.UUID,
    user_id: uuid.UUID = Depends(get_current_user_id),
    service: CostService = Depends(get_cost_service),
) -> list[MaintenanceItemResponse]:
    """Delegate to the service and serialize each row."""
    rows = service.list_maintenance_items(user_id=user_id, asset_id=asset_id)
    return [MaintenanceItemResponse.model_validate(row) for row in rows]


@router.post(
    "/assets/{asset_id}/maintenance-items",
    summary="Add a custom maintenance item",
    description="Creates a user-defined maintenance item on the asset. At least one of `interval_km` "
    "or `interval_months` is required. Returns the created row and its canonical `Location`.",
    response_model=MaintenanceItemResponse,
    status_code=status.HTTP_201_CREATED,
    responses={
        201: {"description": "Maintenance item created."},
        404: {"description": "Asset not found."},
        422: {"description": "Validation error in request body."},
        500: {"description": INTERNAL_ERROR},
    },
)
def create_maintenance_item(
    asset_id: uuid.UUID,
    body: CreateMaintenanceItemRequest,
    response: Response,
    user_id: uuid.UUID = Depends(get_current_user_id),
    service: CostService = Depends(get_cost_service),
) -> MaintenanceItemResponse:
    """Delegate creation to the service and set the `Location` header on the created row."""
    row = service.create_maintenance_item(
        user_id=user_id,
        asset_id=asset_id,
        label=body.label,
        interval_km=body.interval_km,
        interval_months=body.interval_months,
        last_serviced_at_date=body.last_serviced_at_date,
        last_serviced_at_odometer=body.last_serviced_at_odometer,
        estimated_cost=body.estimated_cost,
        tire_type=body.tire_type,
        notes=body.notes,
    )
    response.headers["Location"] = f"/api/assets/{asset_id}/maintenance-items/{row.id}"
    return MaintenanceItemResponse.model_validate(row)


@router.patch(
    "/assets/{asset_id}/maintenance-items/{item_id}",
    summary="Edit or deactivate a maintenance item",
    description="Partially updates a maintenance item row. Only the fields sent are applied; toggling "
    "`is_active` deactivates or reactivates the row. A non-`other` row must keep at least one interval.",
    response_model=MaintenanceItemResponse,
    status_code=status.HTTP_200_OK,
    responses={
        200: {"description": "Maintenance item updated."},
        404: {"description": "Asset or maintenance item not found."},
        422: {"description": "Validation error in request body or merged interval rule."},
        500: {"description": INTERNAL_ERROR},
    },
)
def update_maintenance_item(
    asset_id: uuid.UUID,
    item_id: uuid.UUID,
    body: UpdateMaintenanceItemRequest,
    user_id: uuid.UUID = Depends(get_current_user_id),
    service: CostService = Depends(get_cost_service),
) -> MaintenanceItemResponse:
    """Delegate a partial update, passing only the fields the client actually sent."""
    row = service.update_maintenance_item(
        user_id=user_id, asset_id=asset_id, item_id=item_id, changes=body.model_dump(exclude_unset=True)
    )
    return MaintenanceItemResponse.model_validate(row)
