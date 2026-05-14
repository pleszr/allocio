"""Liveness router."""
from fastapi import APIRouter, status

from app.api.schemas.responses import HealthResponse

router = APIRouter(prefix="/api", tags=["health"])


@router.get(
    "/health",
    summary="Liveness probe",
    description="Always returns `ok` when the process is running.",
    response_model=HealthResponse,
    status_code=status.HTTP_200_OK,
    responses={200: {"description": "Service is alive."}},
)
def health() -> HealthResponse:
    """Return a static liveness payload."""
    return HealthResponse(status="ok")
