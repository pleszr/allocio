"""Greetings HTTP router."""
from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.api.schemas.responses import GreetingResponse
from app.common import message_bundle
from app.db import get_session
from app.services.dependencies import get_greetings_service
from app.services.greetings_service import GreetingsService

router = APIRouter(prefix="/api", tags=["greetings"])


@router.get(
    "/greeting",
    summary="Get the seeded greeting",
    description="Returns the first seeded greeting. Used as a smoke test for the deployment.",
    response_model=GreetingResponse,
    status_code=status.HTTP_200_OK,
    responses={
        200: {"description": "Greeting returned."},
        404: {"description": message_bundle.GREETING_NOT_FOUND},
        500: {"description": message_bundle.INTERNAL_ERROR},
    },
)
def get_greeting(
    session: Session = Depends(get_session),
    service: GreetingsService = Depends(get_greetings_service),
) -> GreetingResponse:
    """Return the first seeded greeting."""
    greeting = service.get_first(session)
    return GreetingResponse.model_validate(greeting)
