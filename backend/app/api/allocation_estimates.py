"""Non-persisting allocation-estimate resource."""

import uuid

from fastapi import APIRouter, Depends, status

from app.api.schemas.requests import AllocationEstimateRequest
from app.api.schemas.responses import AllocationEstimateLineResponse, AllocationEstimateResponse
from app.common.message_bundle import INTERNAL_ERROR
from app.services.allocation_estimate_service import (
    AllocationEstimateService,
    EstimateCostInput,
    EstimateCostOverride,
)
from app.services.dependencies import get_allocation_estimate_service, get_current_user_id

router = APIRouter(prefix="/api", tags=["allocation estimates"])


@router.post(
    "/allocation-estimates",
    summary="Estimate recurring allocation without persistence",
    description="Calculates canonical recurring-cost daily, monthly, and yearly amounts for the "
    "asset-creation review. Usage-based and maintenance selections are valid but excluded because "
    "the request has no usage history. This endpoint creates no domain records or events.",
    response_model=AllocationEstimateResponse,
    status_code=status.HTTP_200_OK,
    responses={
        200: {"description": "Canonical allocation estimate, including an empty zero estimate."},
        422: {"description": "Invalid template, cost key, override, amount, or interval."},
        500: {"description": INTERNAL_ERROR},
    },
)
def create_allocation_estimate(
    body: AllocationEstimateRequest,
    user_id: uuid.UUID = Depends(get_current_user_id),
    service: AllocationEstimateService = Depends(get_allocation_estimate_service),
) -> AllocationEstimateResponse:
    """Map the HTTP request to service DTOs and serialize its pure calculation result."""
    estimate = service.estimate(
        user_id=user_id,
        template_key=body.template,
        selected_cost_keys=body.selected_cost_keys,
        cost_overrides=[
            EstimateCostOverride(
                technical_key=item.technical_key,
                amount=item.amount,
                interval_value=item.interval_value,
                interval_unit=item.interval_unit,
            )
            for item in body.cost_overrides or ()
        ],
        custom_time_based_costs=[
            EstimateCostInput(
                client_key=item.client_key,
                label=item.label,
                amount=item.amount,
                interval_value=item.interval_value,
                interval_unit=item.interval_unit,
            )
            for item in body.custom_time_based_costs or ()
        ],
    )
    return AllocationEstimateResponse(
        currency=estimate.currency,
        lines=[
            AllocationEstimateLineResponse(
                key=line.key,
                label=line.label,
                reference_amount=line.reference_amount,
                annualized_amount=line.annualized_amount,
                monthly_amount=line.monthly_amount,
                daily_rate=line.daily_rate,
            )
            for line in estimate.lines
        ],
        daily_total=estimate.daily_total,
        monthly_total=estimate.monthly_total,
        yearly_total=estimate.yearly_total,
    )
