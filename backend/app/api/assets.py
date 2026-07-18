"""Asset collection router."""
import uuid

from fastapi import APIRouter, Depends, Query, Response, status

from app.api.schemas.requests import CreateAssetRequest
from app.api.schemas.responses import (
    AssetSummaryResponse,
    BalanceHistoryResponse,
    BalancePointResponse,
    CreateAssetResponse,
    WorkspaceOverviewResponse,
    WorkspaceTotalsResponse,
)
from app.common.message_bundle import INTERNAL_ERROR
from app.services.asset_service import AssetService, VehicleDetails
from app.services.balance_history_service import BalanceHistory, BalanceHistoryService
from app.services.dependencies import (
    get_asset_service,
    get_balance_history_service,
    get_current_user_id,
    get_workspace_service,
)
from app.services.workspace_service import WorkspaceOverview, WorkspaceService

router = APIRouter(prefix="/api", tags=["assets"])


@router.post(
    "/assets",
    summary="Create an asset, optionally from a template",
    description="""Creates an asset and its savings bucket. A bare asset needs a free-form type and
    gets no default rows. Selecting a template prefills the type and clones its default time-based,
    usage-based, and maintenance cost rows; the vehicle template also attaches a vehicle profile.
    Returns the full created record set so a client can render it without a second request.""",
    response_model=CreateAssetResponse,
    status_code=status.HTTP_201_CREATED,
    responses={
        201: {"description": "Asset and any template-supplied rows were created."},
        422: {"description": "Validation error in request body."},
        500: {"description": INTERNAL_ERROR},
    },
)
def create_asset(
    body: CreateAssetRequest,
    response: Response,
    user_id: uuid.UUID = Depends(get_current_user_id),
    service: AssetService = Depends(get_asset_service),
) -> CreateAssetResponse:
    """Delegate creation to the service and set the `Location` header on the created asset."""
    vehicle_details = None if body.vehicle is None else VehicleDetails(**body.vehicle.model_dump())
    created = service.create_asset(
        user_id=user_id,
        name=body.name,
        asset_type=body.type,
        template_key=body.template,
        vehicle_details=vehicle_details,
        subtitle=body.subtitle,
        attributes=body.attributes,
    )
    response.headers["Location"] = f"/api/assets/{created.asset.id}"
    return CreateAssetResponse.model_validate(created)


@router.get(
    "/assets",
    summary="List assets with balances and health",
    description="""Returns every asset the authenticated user owns with its calculator-derived bucket
    balance, recommended monthly allocation, and deterministic health status, plus the workspace
    totals the Home screen needs — all in one call, with no per-asset follow-up request. An empty
    workspace returns a 200 with an empty list and zeroed totals.""",
    response_model=WorkspaceOverviewResponse,
    status_code=status.HTTP_200_OK,
    responses={
        200: {"description": "Owned assets with derived figures and workspace totals."},
        500: {"description": INTERNAL_ERROR},
    },
)
def list_assets(
    user_id: uuid.UUID = Depends(get_current_user_id),
    service: WorkspaceService = Depends(get_workspace_service),
) -> WorkspaceOverviewResponse:
    """Delegate to the workspace service and map its overview DTO to the response model."""
    overview = service.list_workspace(user_id)
    return _to_overview_response(overview)


@router.get(
    "/assets/{asset_id}/balance-history",
    summary="Reconstruct an asset's monthly bucket-balance history",
    description="""Returns an ordered (oldest → newest) monthly series of event-derived bucket balances
    for one owned asset, suitable for a dashboard sparkline. Each point is the cumulative balance
    (sum of allocations minus expenses) as of that month; the newest point is a live snapshot as of
    today. The default window is 12 months, overridable with `?months=N` (1-60); assets younger than
    the window return a shorter valid series, and an asset with no events returns a single
    current-month zero point.""",
    response_model=BalanceHistoryResponse,
    status_code=status.HTTP_200_OK,
    responses={
        200: {"description": "Ordered monthly balance points for the asset's bucket."},
        404: {"description": "Asset or bucket not found for this user."},
        422: {"description": "months query param out of range (must be 1-60)."},
        500: {"description": INTERNAL_ERROR},
    },
)
def get_balance_history(
    asset_id: uuid.UUID,
    months: int = Query(12, ge=1, le=60),
    user_id: uuid.UUID = Depends(get_current_user_id),
    service: BalanceHistoryService = Depends(get_balance_history_service),
) -> BalanceHistoryResponse:
    """Delegate to the balance-history service and map its DTO to the response model."""
    history = service.balance_history(user_id, asset_id, months)
    return _to_balance_history_response(history)


def _to_balance_history_response(history: BalanceHistory) -> BalanceHistoryResponse:
    """Map the service `BalanceHistory` DTO to its Pydantic response, keeping the api layer off service DTOs."""
    return BalanceHistoryResponse(
        asset_id=history.asset_id,
        currency=history.currency,
        points=[
            BalancePointResponse(month=point.month, as_of=point.as_of, balance=point.balance)
            for point in history.points
        ],
    )


def _to_overview_response(overview: WorkspaceOverview) -> WorkspaceOverviewResponse:
    """Map the service `WorkspaceOverview` DTO to its Pydantic response, keeping the api layer off service DTOs."""
    return WorkspaceOverviewResponse(
        assets=[
            AssetSummaryResponse(
                id=summary.asset_id,
                type=summary.type,
                name=summary.name,
                subtitle=summary.subtitle,
                status=summary.status,
                currency=summary.currency,
                balance=summary.balance,
                recommended_monthly_allocation=summary.recommended_monthly_allocation,
                health=summary.health,
            )
            for summary in overview.assets
        ],
        totals=WorkspaceTotalsResponse(
            total_balance=overview.totals.total_balance,
            total_recommended_monthly_allocation=overview.totals.total_recommended_monthly_allocation,
            alert_count=overview.totals.alert_count,
        ),
    )
