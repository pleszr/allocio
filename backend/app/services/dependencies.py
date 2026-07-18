import uuid

from fastapi import Depends
from sqlalchemy.orm import Session

from app.db import get_session
from app.services.asset_detail_service import AssetDetailService
from app.services.asset_service import AssetService
from app.services.balance_history_service import BalanceHistoryService
from app.services.check_in_service import CheckInService
from app.services.cost_service import CostService
from app.services.expense_service import ExpenseService
from app.services.workspace_service import WorkspaceService

# Placeholder identity until real auth lands; every write is attributed to this dev user.
DEV_USER_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")


def get_current_user_id() -> uuid.UUID:
    """Return the current user id. Stub injection seam that real auth will replace."""
    return DEV_USER_ID


def get_asset_service(session: Session = Depends(get_session)) -> AssetService:
    """Bind an `AssetService` to the request-scoped session."""
    return AssetService(session)


def get_cost_service(session: Session = Depends(get_session)) -> CostService:
    """Provide a `CostService` for the cost-management routes over the request-scoped session."""
    return CostService(session)


def get_expense_service(session: Session = Depends(get_session)) -> ExpenseService:
    """Provide an `ExpenseService` for the expense-logging routes over the request-scoped session."""
    return ExpenseService(session)


def get_check_in_service(session: Session = Depends(get_session)) -> CheckInService:
    """Provide a `CheckInService` for the check-in preview and posting routes over the request-scoped session."""
    return CheckInService(session)


def get_workspace_service(session: Session = Depends(get_session)) -> WorkspaceService:
    """Provide a `WorkspaceService` for the read-only workspace overview route over the request-scoped session."""
    return WorkspaceService(session)


def get_balance_history_service(session: Session = Depends(get_session)) -> BalanceHistoryService:
    """Provide a `BalanceHistoryService` for the read-only balance-history route over the request-scoped session."""
    return BalanceHistoryService(session)


def get_asset_detail_service(session: Session = Depends(get_session)) -> AssetDetailService:
    """Provide an `AssetDetailService` for the read-only asset detail route over the request-scoped session."""
    return AssetDetailService(session)
