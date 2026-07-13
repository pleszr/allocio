"""Asset collection router."""
import uuid

from fastapi import APIRouter, Depends, Response, status

from app.api.schemas.requests import CreateAssetRequest
from app.api.schemas.responses import CreateAssetResponse
from app.common.message_bundle import INTERNAL_ERROR
from app.services.asset_service import AssetService, VehicleDetails
from app.services.dependencies import get_asset_service, get_current_user_id

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
    )
    response.headers["Location"] = f"/api/assets/{created.asset.id}"
    return CreateAssetResponse.model_validate(created)
