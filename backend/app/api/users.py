"""User settings router: read and replace the caller's workspace-wide preferences.

Both routes resolve the caller via `get_current_user_id` (the dev id under `AUTH_DISABLED`, else the
session user) and delegate to `UserSettingsService`. `PUT` is a full replace of the settings
resource, so a valid body always carries both fields.
"""

import uuid

from fastapi import APIRouter, Depends, status

from app.api.schemas.requests import UpdateUserSettingsRequest
from app.api.schemas.responses import UserSettingsResponse
from app.common.message_bundle import INTERNAL_ERROR
from app.services.dependencies import get_current_user_id, get_user_settings_service
from app.services.user_settings_service import UserSettingsService

router = APIRouter(prefix="/api/users", tags=["users"])


@router.get(
    "/me/settings",
    summary="Read the current user's settings",
    description="""Returns the authenticated caller's workspace-wide settings: display currency and
    language preference. A fresh user carries the server defaults (HUF / en) until they change them.""",
    response_model=UserSettingsResponse,
    status_code=status.HTTP_200_OK,
    responses={
        200: {"description": "The caller's current settings."},
        401: {"description": "No active session / not signed in."},
        500: {"description": INTERNAL_ERROR},
    },
)
def get_my_settings(
    user_id: uuid.UUID = Depends(get_current_user_id),
    service: UserSettingsService = Depends(get_user_settings_service),
) -> UserSettingsResponse:
    """Delegate to the settings service and map the user row to the settings response."""
    user = service.get_settings(user_id)
    return UserSettingsResponse.model_validate(user)


@router.put(
    "/me/settings",
    summary="Replace the current user's settings",
    description="""Fully replaces the authenticated caller's display currency and language preference,
    persists them, and echoes the saved values so the client can trust the stored state. An
    out-of-range currency or language is rejected as a 422 by the request schema.""",
    response_model=UserSettingsResponse,
    status_code=status.HTTP_200_OK,
    responses={
        200: {"description": "Settings updated; the saved values are returned."},
        401: {"description": "No active session / not signed in."},
        422: {"description": "Validation error in request body (invalid currency or language)."},
        500: {"description": INTERNAL_ERROR},
    },
)
def replace_my_settings(
    body: UpdateUserSettingsRequest,
    user_id: uuid.UUID = Depends(get_current_user_id),
    service: UserSettingsService = Depends(get_user_settings_service),
) -> UserSettingsResponse:
    """Delegate the full-replace update to the settings service and map the saved row to the response."""
    user = service.update_settings(user_id, body.default_currency, body.language)
    return UserSettingsResponse.model_validate(user)
