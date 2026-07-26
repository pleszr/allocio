"""Asset collection router."""
import uuid

from fastapi import APIRouter, Depends, Query, Response, status

from app.api.costs import _serialize_maintenance, _serialize_time_based
from app.api.schemas.requests import CreateAssetRequest, UpdateManualExtraRequest
from app.api.schemas.responses import (
    ActivityItemResponse,
    AverageAllocationResponse,
    AssetDetailResponse,
    AssetSummaryResponse,
    BalanceHistoryResponse,
    BalancePointResponse,
    CheckInExpenseLineResponse,
    CheckInHistoryResponse,
    CheckInHistoryRowResponse,
    CreateAssetResponse,
    ManualExtraResponse,
    NextMaintenanceResponse,
    UpcomingExpenseResponse,
    WorkspaceOverviewResponse,
    WorkspaceTotalsResponse,
)
from app.common.message_bundle import INTERNAL_ERROR
from app.services.asset_detail_service import AssetDetail, AssetDetailService
from app.services.asset_service import AssetService, CostOverride, VehicleDetails
from app.services.balance_history_service import BalanceHistory, BalanceHistoryService
from app.services.check_in_history_service import CheckInHistory, CheckInHistoryService
from app.services.cost_service import CostService
from app.services.dependencies import (
    get_asset_detail_service,
    get_asset_service,
    get_balance_history_service,
    get_check_in_history_service,
    get_cost_service,
    get_current_user_id,
    get_workspace_service,
)
from app.services.workspace_service import WorkspaceOverview, WorkspaceService

router = APIRouter(prefix="/api", tags=["assets"])


@router.post(
    "/assets",
    summary="Create an asset, optionally from a template",
    description="""Creates an asset and its savings bucket. A bare asset needs a free-form type and
    gets no default rows. Selecting a template prefills the type and attaches a vehicle profile
    when the template carries one; template cost rows are cloned only when their `technical_key`
    is listed in `selected_cost_keys` (omitting it clones no rows — there is no implicit clone-all).
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
    cost_service: CostService = Depends(get_cost_service),
) -> CreateAssetResponse:
    """Delegate creation to the service and set the `Location` header on the created asset."""
    vehicle_details = None if body.vehicle is None else VehicleDetails(**body.vehicle.model_dump())
    cost_overrides = (
        None
        if body.cost_overrides is None
        else [
            CostOverride(
                technical_key=o.technical_key,
                amount=o.amount,
                interval_value=o.interval_value,
                interval_unit=o.interval_unit,
            )
            for o in body.cost_overrides
        ]
    )
    created = service.create_asset(
        user_id=user_id,
        name=body.name,
        asset_type=body.type,
        template_key=body.template,
        vehicle_details=vehicle_details,
        selected_cost_keys=body.selected_cost_keys,
        cost_overrides=cost_overrides,
    )
    response.headers["Location"] = f"/api/assets/{created.asset.id}"
    return CreateAssetResponse.model_validate(
        {
            "asset": created.asset,
            "profile": created.profile,
            "bucket": created.bucket,
            "time_based_costs": [
                _serialize_time_based(cost_service.time_based_cost_view(row))
                for row in created.time_based_costs
            ],
            "usage_based_costs": created.usage_based_costs,
            "maintenance_items": created.maintenance_items,
        }
    )


@router.get(
    "/assets",
    summary="List assets with balances and monthly allocations",
    description="""Returns every asset the authenticated user owns with its calculator-derived bucket
    balance and recommended monthly allocation, plus the workspace totals the Home screen needs —
    all in one call, with no per-asset follow-up request. An empty workspace returns a 200 with an
    empty list and zeroed totals.""",
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
    (sum of allocations minus bucket-covered expense portions) as of that month; the newest point
    is a live snapshot as of today. The default window is 12 months, overridable with `?months=N`
    (1-60); assets younger than the window return a shorter valid series, and an asset with no
    events returns a single current-month zero point.""",
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


@router.get(
    "/assets/{asset_id}/check-in-history",
    summary="List an asset's posted check-ins as a running ledger",
    description="""Returns every posted check-in for one owned asset, ordered oldest → newest, each
    row carrying its usage, allocation total, full/covered/out-of-pocket expense split, bucket net
    change, and running balance. An asset with no posted check-ins returns a 200 with an empty list.""",
    response_model=CheckInHistoryResponse,
    status_code=status.HTTP_200_OK,
    responses={
        200: {"description": "Ordered check-in ledger rows for the asset."},
        404: {"description": "Asset or bucket not found for this user."},
        500: {"description": INTERNAL_ERROR},
    },
)
def get_check_in_history(
    asset_id: uuid.UUID,
    user_id: uuid.UUID = Depends(get_current_user_id),
    service: CheckInHistoryService = Depends(get_check_in_history_service),
) -> CheckInHistoryResponse:
    """Delegate to the check-in-history service and map its DTO to the response model."""
    history = service.check_in_history(user_id, asset_id)
    return _to_check_in_history_response(history)


@router.put(
    "/assets/{asset_id}/manual-extra",
    summary="Replace an asset's manual extra monthly buffer",
    description="""Full-replace write for the flat monthly buffer added on top of an asset's modeled
    time- and usage-based accruals. The new value folds into recommended_monthly_allocation
    everywhere it's shown and is prorated into future check-in allocations.""",
    response_model=ManualExtraResponse,
    status_code=status.HTTP_200_OK,
    responses={
        200: {"description": "The updated manual extra monthly buffer."},
        404: {"description": "Asset not found for this user."},
        422: {"description": "amount is negative."},
        500: {"description": INTERNAL_ERROR},
    },
)
def update_manual_extra(
    asset_id: uuid.UUID,
    body: UpdateManualExtraRequest,
    user_id: uuid.UUID = Depends(get_current_user_id),
    service: AssetService = Depends(get_asset_service),
) -> ManualExtraResponse:
    """Delegate to the asset service and wrap the updated value."""
    updated = service.update_manual_extra_monthly(user_id, asset_id, body.amount)
    return ManualExtraResponse(manual_extra_monthly=updated)


@router.get(
    "/assets/{asset_id}",
    summary="Read one asset's detail payload",
    description="""Returns the composed dashboard payload for one owned asset: derived balance,
    recommended monthly and daily accrual, current usage and last check-in, vehicle lifecycle,
    trailing monthly-cost, nearest kilometer-based maintenance, every maintenance item with its
    computed status, and a merged recent-activity feed including out-of-pocket expense funding.
    Type-agnostic — vehicle signals are null for assets without a vehicle profile. Unknown or unowned
    assets return 404.""",
    response_model=AssetDetailResponse,
    status_code=status.HTTP_200_OK,
    responses={
        200: {"description": "The asset's composed detail payload."},
        404: {"description": "Asset not found for this user."},
        500: {"description": INTERNAL_ERROR},
    },
)
def get_asset_detail(
    asset_id: uuid.UUID,
    user_id: uuid.UUID = Depends(get_current_user_id),
    service: AssetDetailService = Depends(get_asset_detail_service),
) -> AssetDetailResponse:
    """Delegate to the asset-detail service and map its DTO to the response model."""
    detail = service.get_detail(user_id, asset_id)
    return _to_asset_detail_response(detail)


def _to_asset_detail_response(detail: AssetDetail) -> AssetDetailResponse:
    """Map the service `AssetDetail` DTO to its Pydantic response, keeping the api layer off service DTOs."""
    return AssetDetailResponse(
        id=detail.asset_id,
        type=detail.type,
        name=detail.name,
        status=detail.status,
        currency=detail.currency,
        balance=detail.balance,
        recommended_monthly_allocation=detail.recommended_monthly_allocation,
        daily_accrual=detail.daily_accrual,
        vehicle_age_years=detail.vehicle_age_years,
        tracked_in_app_months=detail.tracked_in_app_months,
        average_monthly_cost=detail.average_monthly_cost,
        avg_monthly_paid_out_of_pocket=detail.avg_monthly_paid_out_of_pocket,
        next_maintenance=(
            NextMaintenanceResponse(
                label=detail.next_maintenance.label,
                remaining_km=detail.next_maintenance.remaining_km,
            )
            if detail.next_maintenance is not None
            else None
        ),
        tracks_usage=detail.tracks_usage,
        current_usage=detail.current_usage,
        usage_since_last_check_in=detail.usage_since_last_check_in,
        last_check_in_date=detail.last_check_in_date,
        maintenance_items=[_serialize_maintenance(view) for view in detail.maintenance_items],
        recent_activity=[
            ActivityItemResponse(
                event_date=item.date,
                kind=item.kind,
                label=item.label,
                amount=item.amount,
                paid_out_of_pocket=item.paid_out_of_pocket,
            )
            for item in detail.recent_activity
        ],
        upcoming_expenses=[
            UpcomingExpenseResponse(
                name=item.name,
                category=item.category,
                days_until=item.days_until,
                amount=item.amount,
                overdue=item.overdue,
            )
            for item in detail.upcoming_expenses
        ],
        manual_extra_monthly=detail.manual_extra_monthly,
        manual_extra_recommended=detail.manual_extra_recommended,
        average_monthly_usage=detail.average_monthly_usage,
        average_allocation=AverageAllocationResponse(
            months=detail.average_allocation.months,
            amount=detail.average_allocation.amount,
        ),
    )


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


def _to_check_in_history_response(history: CheckInHistory) -> CheckInHistoryResponse:
    """Map the service `CheckInHistory` DTO to its Pydantic response, keeping the api layer off service DTOs."""
    return CheckInHistoryResponse(
        asset_id=history.asset_id,
        currency=history.currency,
        rows=[
            CheckInHistoryRowResponse(
                check_in_id=row.check_in_id,
                period_end=row.period_end,
                usage_end=row.usage_end,
                usage_since_last=row.usage_since_last,
                elapsed_days=row.elapsed_days,
                allocated=row.allocated,
                expense=row.expense,
                bucket_expense=row.bucket_expense,
                paid_out_of_pocket=row.paid_out_of_pocket,
                net=row.net,
                balance=row.balance,
                expenses=[
                    CheckInExpenseLineResponse(
                        kind=line.kind,
                        amount=line.amount,
                        bucket_amount=line.bucket_amount,
                        paid_out_of_pocket=line.paid_out_of_pocket,
                        event_date=line.event_date,
                        comment=line.comment,
                        source_type=line.source_type,
                        source_id=line.source_id,
                        usage_counter_at_event=line.usage_counter_at_event,
                        label=line.label,
                    )
                    for line in row.expenses
                ],
            )
            for row in history.rows
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
                status=summary.status,
                currency=summary.currency,
                balance=summary.balance,
                recommended_monthly_allocation=summary.recommended_monthly_allocation,
            )
            for summary in overview.assets
        ],
        totals=WorkspaceTotalsResponse(
            total_balance=overview.totals.total_balance,
            total_recommended_monthly_allocation=overview.totals.total_recommended_monthly_allocation,
        ),
    )
