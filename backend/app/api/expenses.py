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
        paid_out_of_pocket_override=body.paid_out_of_pocket_override,
        excluded_from_average=body.excluded_from_average,
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


def _list_source_expenses(
    service: ExpenseService, user_id: uuid.UUID, asset_id: uuid.UUID, source_type: str, source_id: uuid.UUID
) -> list[ExpenseEventResponse]:
    """Fetch and serialize the expenses linked to one cost/maintenance row for its detail popup."""
    rows = service.list_source_expenses(
        user_id=user_id, asset_id=asset_id, source_type=source_type, source_id=source_id
    )
    return [ExpenseEventResponse.model_validate(row) for row in rows]


@router.get(
    "/assets/{asset_id}/time-based-costs/{cost_id}/expenses",
    summary="List a time-based cost's posted expenses",
    description="Returns every posted expense linked to one time-based cost row, ascending by event "
    "date, for its history popup. Covers check-in-posted and standalone payments alike. Scoped to the "
    "owning user; an unknown asset or cost row returns 404.",
    response_model=list[ExpenseEventResponse],
    status_code=status.HTTP_200_OK,
    responses={
        200: {"description": "All posted expenses for the time-based cost."},
        404: {"description": "Asset or cost row not found."},
        500: {"description": INTERNAL_ERROR},
    },
)
def list_time_based_cost_expenses(
    asset_id: uuid.UUID,
    cost_id: uuid.UUID,
    user_id: uuid.UUID = Depends(get_current_user_id),
    service: ExpenseService = Depends(get_expense_service),
) -> list[ExpenseEventResponse]:
    """Delegate to the shared source-expense lookup with the time-based source type."""
    return _list_source_expenses(service, user_id, asset_id, "time_based_cost", cost_id)


@router.get(
    "/assets/{asset_id}/usage-based-costs/{cost_id}/expenses",
    summary="List a usage-based cost's posted expenses",
    description="Returns every posted expense linked to one usage-based cost component, ascending by "
    "event date, for its history popup. Covers check-in-posted and standalone payments alike. Scoped "
    "to the owning user; an unknown asset or cost row returns 404.",
    response_model=list[ExpenseEventResponse],
    status_code=status.HTTP_200_OK,
    responses={
        200: {"description": "All posted expenses for the usage-based cost."},
        404: {"description": "Asset or cost row not found."},
        500: {"description": INTERNAL_ERROR},
    },
)
def list_usage_based_cost_expenses(
    asset_id: uuid.UUID,
    cost_id: uuid.UUID,
    user_id: uuid.UUID = Depends(get_current_user_id),
    service: ExpenseService = Depends(get_expense_service),
) -> list[ExpenseEventResponse]:
    """Delegate to the shared source-expense lookup with the usage-based source type."""
    return _list_source_expenses(service, user_id, asset_id, "usage_based_cost", cost_id)


@router.get(
    "/assets/{asset_id}/maintenance-items/{item_id}/expenses",
    summary="List a maintenance item's posted expenses",
    description="Returns every posted expense linked to one maintenance item, ascending by event "
    "date, for its history popup. Covers check-in-posted and standalone payments alike. Scoped to the "
    "owning user; an unknown asset or maintenance item returns 404.",
    response_model=list[ExpenseEventResponse],
    status_code=status.HTTP_200_OK,
    responses={
        200: {"description": "All posted expenses for the maintenance item."},
        404: {"description": "Asset or maintenance item not found."},
        500: {"description": INTERNAL_ERROR},
    },
)
def list_maintenance_item_expenses(
    asset_id: uuid.UUID,
    item_id: uuid.UUID,
    user_id: uuid.UUID = Depends(get_current_user_id),
    service: ExpenseService = Depends(get_expense_service),
) -> list[ExpenseEventResponse]:
    """Delegate to the shared source-expense lookup with the maintenance source type."""
    return _list_source_expenses(service, user_id, asset_id, "maintenance_item", item_id)
