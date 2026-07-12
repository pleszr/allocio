"""Vehicle collection router."""
import uuid

from fastapi import APIRouter, Depends, Response, status

from app.api.schemas.requests import CreateVehicleRequest
from app.api.schemas.responses import CreateVehicleResponse
from app.common.message_bundle import INTERNAL_ERROR
from app.services.dependencies import get_current_user_id, get_vehicle_service
from app.services.vehicle_service import VehicleService

router = APIRouter(prefix="/api", tags=["vehicles"])


@router.post(
    "/vehicles",
    summary="Create a vehicle and its default cost set",
    description="""Creates a vehicle asset, its profile, a savings bucket, and the cloned default
    time-based, usage-based, and maintenance cost rows in one transaction. Returns the full
    created record set so a client can render it without a second request.""",
    response_model=CreateVehicleResponse,
    status_code=status.HTTP_201_CREATED,
    responses={
        201: {"description": "Vehicle and its default cost set were created."},
        422: {"description": "Validation error in request body."},
        500: {"description": INTERNAL_ERROR},
    },
)
def create_vehicle(
    body: CreateVehicleRequest,
    response: Response,
    user_id: uuid.UUID = Depends(get_current_user_id),
    service: VehicleService = Depends(get_vehicle_service),
) -> CreateVehicleResponse:
    """Delegate creation to the service and set the `Location` header on the created asset."""
    created = service.create_vehicle(
        user_id=user_id,
        name=body.name,
        year=body.year,
        make=body.make,
        model=body.model,
        starting_odometer=body.starting_odometer,
    )
    response.headers["Location"] = f"/api/vehicles/{created.asset.id}"
    return CreateVehicleResponse.model_validate(created)
