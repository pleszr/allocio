"""Expense-logging router: post auditable expense events to an asset's bucket and list them back."""
import uuid

from fastapi import APIRouter, Depends, Response, status

from app.api.schemas.requests import LogExpenseRequest
from app.api.schemas.responses import ExpenseEventResponse
from app.common.message_bundle import INTERNAL_ERROR
from app.services.dependencies import get_current_user_id, get_expense_service
from app.services.expense_service import ExpenseService

router = APIRouter(prefix="/api", tags=["expenses"])


@router.post(
    "/assets/{asset_id}/expenses",
    summary="Log an expense against an asset",
    description="Posts an immutable expense with a server-derived split between the bucket balance "
    "available on its event date and an out-of-pocket remainder. A `modeled` expense links a "
    "cost/maintenance source row; an `other` expense is a manual entry with no source. Returns the "
    "created event and its canonical `Location`.",
    response_model=ExpenseEventResponse,
    status_code=status.HTTP_201_CREATED,
    responses={
        201: {"description": "Expense event created."},
        404: {"description": "Asset not found."},
        422: {"description": "Validation error in request body or invalid source reference."},
        500: {"description": INTERNAL_ERROR},
    },
)
def log_expense(
    asset_id: uuid.UUID,
    body: LogExpenseRequest,
    response: Response,
    user_id: uuid.UUID = Depends(get_current_user_id),
    service: ExpenseService = Depends(get_expense_service),
) -> ExpenseEventResponse:
    """Delegate logging to the service and set the `Location` header on the created event."""
    row = service.log_expense(
        user_id=user_id,
        asset_id=asset_id,
        kind=body.kind,
        amount=body.amount,
        event_date=body.event_date,
        usage_counter_at_event=body.usage_counter_at_event,
        comment=body.comment,
        source_type=body.source_type,
        source_id=body.source_id,
    )
    response.headers["Location"] = f"/api/assets/{asset_id}/expenses/{row.id}"
    return ExpenseEventResponse.model_validate(row)


@router.get(
    "/assets/{asset_id}/expenses",
    summary="List an asset's expenses",
    description="Returns every posted expense event for the asset's bucket, ordered by event date. "
    "Scoped to the owning user; unknown or unowned assets return 404.",
    response_model=list[ExpenseEventResponse],
    status_code=status.HTTP_200_OK,
    responses={
        200: {"description": "All expense events for the asset."},
        404: {"description": "Asset not found."},
        500: {"description": INTERNAL_ERROR},
    },
)
def list_expenses(
    asset_id: uuid.UUID,
    user_id: uuid.UUID = Depends(get_current_user_id),
    service: ExpenseService = Depends(get_expense_service),
) -> list[ExpenseEventResponse]:
    """Delegate to the service and serialize each event."""
    rows = service.list_expenses(user_id=user_id, asset_id=asset_id)
    return [ExpenseEventResponse.model_validate(row) for row in rows]
