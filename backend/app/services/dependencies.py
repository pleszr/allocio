import uuid

from fastapi import Depends
from sqlalchemy.orm import Session

from app.db import get_session
from app.services.cost_service import CostService
from app.services.vehicle_service import VehicleService

# Placeholder identity until real auth lands; every write is attributed to this dev user.
DEV_USER_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")


def get_current_user_id() -> uuid.UUID:
    """Return the current user id. Stub injection seam that real auth will replace."""
    return DEV_USER_ID


def get_vehicle_service(session: Session = Depends(get_session)) -> VehicleService:
    """Bind a `VehicleService` to the request-scoped session."""
    return VehicleService(session)


def get_cost_service(session: Session = Depends(get_session)) -> CostService:
    """Provide a `CostService` for the cost-management routes over the request-scoped session."""
    return CostService(session)
