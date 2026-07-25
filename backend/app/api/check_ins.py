"""Check-in router: preview a period's financial result without writing, then post it and its events."""
import uuid

from fastapi import APIRouter, Depends, Response, status

from app.api.schemas.requests import LogExpenseRequest, PostCheckInRequest, PreviewCheckInRequest
from app.api.schemas.responses import (
    AllocationEventResponse,
    AllocationLineResponse,
    CheckInPostResponse,
    CheckInPreviewResponse,
    CheckInResponse,
    ExpenseEventResponse,
    ExpenseLineResponse,
)
from app.common.message_bundle import INTERNAL_ERROR
from app.services.check_in_service import CheckInPreview, CheckInService, ExpenseDraft
from app.services.dependencies import get_check_in_service, get_current_user_id

router = APIRouter(prefix="/api", tags=["check-ins"])


@router.post(
    "/assets/{asset_id}/check-ins/preview",
    summary="Preview a check-in period",
    description="Computes allocation lines, full/covered/out-of-pocket expense splits, and a "
    "non-negative bucket balance without writing records. Deterministic for the same input and "
    "stored state, and the exact basis for posting.",
    response_model=CheckInPreviewResponse,
    status_code=status.HTTP_200_OK,
    responses={
        200: {"description": "Computed period preview."},
        404: {"description": "Asset or bucket not found."},
        422: {"description": "Validation error in request body or invalid period/usage bounds."},
        500: {"description": INTERNAL_ERROR},
    },
)
def preview_check_in(
    asset_id: uuid.UUID,
    body: PreviewCheckInRequest,
    user_id: uuid.UUID = Depends(get_current_user_id),
    service: CheckInService = Depends(get_check_in_service),
) -> CheckInPreviewResponse:
    """Delegate the computation to the service and serialize the previewed period."""
    preview = service.preview_check_in(
        user_id=user_id,
        asset_id=asset_id,
        period_end=body.period_end,
        usage_end=body.usage_end,
        active_tire_type=body.active_tire_type,
        expenses=_to_drafts(body.expenses),
    )
    return _to_preview_response(preview)


@router.post(
    "/assets/{asset_id}/check-ins",
    summary="Post a check-in",
    description="Persists a posted check-in plus one allocation event per active cost and one expense event "
    "per submitted expense, in a single transaction. Amounts match the immediately preceding preview.",
    response_model=CheckInPostResponse,
    status_code=status.HTTP_201_CREATED,
    responses={
        201: {"description": "Check-in and its events created."},
        404: {"description": "Asset or bucket not found."},
        422: {"description": "Validation error in request body, invalid period/usage bounds, or bad source."},
        500: {"description": INTERNAL_ERROR},
    },
)
def post_check_in(
    asset_id: uuid.UUID,
    body: PostCheckInRequest,
    response: Response,
    user_id: uuid.UUID = Depends(get_current_user_id),
    service: CheckInService = Depends(get_check_in_service),
) -> CheckInPostResponse:
    """Delegate posting to the service, set the `Location` header, and serialize the created records."""
    check_in, allocation_events, expense_events = service.post_check_in(
        user_id=user_id,
        asset_id=asset_id,
        period_end=body.period_end,
        usage_end=body.usage_end,
        active_tire_type=body.active_tire_type,
        expenses=_to_drafts(body.expenses),
        notes=body.notes,
    )
    response.headers["Location"] = f"/api/assets/{asset_id}/check-ins/{check_in.id}"
    return CheckInPostResponse(
        check_in=CheckInResponse.model_validate(check_in),
        allocation_events=[AllocationEventResponse.model_validate(event) for event in allocation_events],
        expense_events=[ExpenseEventResponse.model_validate(event) for event in expense_events],
    )


def _to_drafts(expenses: list[LogExpenseRequest]) -> list[ExpenseDraft]:
    """Map request-body expense items to service-layer drafts, keeping the api layer off the domain layer."""
    return [
        ExpenseDraft(
            kind=item.kind,
            amount=item.amount,
            event_date=item.event_date,
            usage_counter_at_event=item.usage_counter_at_event,
            comment=item.comment,
            source_type=item.source_type,
            source_id=item.source_id,
            paid_out_of_pocket_override=item.paid_out_of_pocket_override,
        )
        for item in expenses
    ]


def _to_preview_response(preview: CheckInPreview) -> CheckInPreviewResponse:
    """Serialize a computed preview into its response model."""
    computation = preview.computation
    return CheckInPreviewResponse(
        asset_id=preview.asset_id,
        period_start=preview.period_start,
        period_end=preview.period_end,
        usage_start=preview.usage_start,
        usage_end=preview.usage_end,
        elapsed_days=computation.elapsed_days,
        usage_amount=computation.usage_amount,
        active_tire_type=preview.active_tire_type,
        allocation_lines=[
            AllocationLineResponse(
                source_type=line.source_type, source_id=line.source_id, label=line.label, amount=line.amount
            )
            for line in computation.allocation_lines
        ],
        expense_lines=[
            ExpenseLineResponse(
                kind=line.kind,
                amount=line.amount,
                bucket_amount=line.bucket_amount,
                paid_out_of_pocket=line.paid_out_of_pocket,
                event_date=line.event_date,
                comment=line.comment,
                source_type=line.source_type,
                source_id=line.source_id,
                usage_counter_at_event=line.usage_counter_at_event,
            )
            for line in computation.expense_lines
        ],
        balance_before=computation.balance_before,
        total_allocation=computation.total_allocation,
        total_expense=computation.total_expense,
        total_bucket_expense=computation.total_bucket_expense,
        paid_out_of_pocket=computation.paid_out_of_pocket,
        net_bucket_change=computation.net_bucket_change,
        balance_after=computation.balance_after,
    )
