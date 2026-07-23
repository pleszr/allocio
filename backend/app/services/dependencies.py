import uuid

from fastapi import Depends, Request
from sqlalchemy.orm import Session

from app.common.exceptions import AuthenticationError
from app.config import settings
from app.db import get_session
from app.services.asset_detail_service import AssetDetailService
from app.services.asset_service import AssetService
from app.services.asset_template_service import AssetTemplateService
from app.services.auth_service import AuthService
from app.services.balance_history_service import BalanceHistoryService
from app.services.check_in_service import CheckInService
from app.services.cost_service import CostService
from app.services.expense_service import ExpenseService
from app.services.workspace_service import WorkspaceService

# Fixed dev identity used only under the `AUTH_DISABLED` bypass; the startup hook ensures a matching
# users row so the asset FK holds. Real requests resolve their id from the signed session cookie.
DEV_USER_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")


def get_current_user_id(request: Request) -> uuid.UUID:
    """Resolve the caller's user id from the session, or the dev user under `AUTH_DISABLED`.

    Raises `AuthenticationError` (401) when auth is enabled and no session user is present. FastAPI
    injects `request`; routes that `Depends(get_current_user_id)` need no change.
    """
    if settings.auth_disabled:
        return DEV_USER_ID
    user_id = request.session.get("user_id")
    if not user_id:
        raise AuthenticationError()
    return uuid.UUID(user_id)


def get_auth_service(session: Session = Depends(get_session)) -> AuthService:
    """Bind an `AuthService` to the request-scoped session for the auth-callback and `/me` routes."""
    return AuthService(session)


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


def get_asset_template_service() -> AssetTemplateService:
    """Provide an `AssetTemplateService` for the template-catalog read route; the catalog is static, no session."""
    return AssetTemplateService()
