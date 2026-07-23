"""Google OAuth authentication router.

Server-side Authorization-Code flow: `/login` bounces the browser to Google, `/callback` exchanges
the code, upserts the user, and stores its id in a signed HttpOnly session cookie. `/me` reports the
current user and `/logout` clears the session.

`/login` and `/callback` are `GET` — a deliberate, documented exception to the nouns-only REST rule
in `python-patterns.md`, because OAuth redirects must be browser-navigable `GET`s.
"""

import uuid

from authlib.integrations.starlette_client import OAuth, OAuthError
from fastapi import APIRouter, Depends, Request, status
from fastapi.responses import RedirectResponse

from app.api.schemas.responses import CurrentUserResponse
from app.common.exceptions import AuthenticationError
from app.common.message_bundle import INTERNAL_ERROR
from app.config import settings
from app.services.auth_service import AuthService
from app.services.dependencies import DEV_USER_ID, get_auth_service

router = APIRouter(prefix="/api/auth", tags=["auth"])

# Register the Google client only when creds are present, so importing this module never crashes
# under the `AUTH_DISABLED` dev bypass (which runs without Google creds).
_oauth = OAuth()
if settings.google_client_id:
    _oauth.register(
        name="google",
        client_id=settings.google_client_id,
        client_secret=settings.google_client_secret,
        server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
        client_kwargs={"scope": "openid email profile"},
    )


@router.get(
    "/login",
    summary="Start Google sign-in",
    description="Redirects the browser to Google's consent screen (302). GET by OAuth-redirect necessity.",
    responses={
        302: {"description": "Redirect to Google's OAuth consent screen."},
        500: {"description": INTERNAL_ERROR},
    },
)
async def login(request: Request) -> RedirectResponse:
    """Build the fixed callback URL and hand off to Authlib's authorize redirect."""
    redirect_uri = f"{settings.oauth_redirect_base_url}/api/auth/callback"
    return await _oauth.google.authorize_redirect(request, redirect_uri)


@router.get(
    "/callback",
    summary="Google OAuth callback",
    description="""Exchanges the authorization code for a token, upserts the user, and opens a signed
    session before redirecting to the SPA. On any OAuth failure (state mismatch, denied consent,
    exchange error) it redirects to `/?auth_error=1` rather than returning a 500. GET by OAuth
    necessity.""",
    responses={
        302: {"description": "Redirect to `/` when authenticated, or `/?auth_error=1` on failure."},
        500: {"description": INTERNAL_ERROR},
    },
)
async def callback(request: Request, service: AuthService = Depends(get_auth_service)) -> RedirectResponse:
    """Complete the code exchange, persist the user, and set the session cookie."""
    try:
        claims = await _resolve_google_claims(request)
    except OAuthError:
        return RedirectResponse(url="/?auth_error=1", status_code=status.HTTP_302_FOUND)
    user = service.upsert_from_google(claims)
    request.session["user_id"] = str(user.id)
    return RedirectResponse(url="/", status_code=status.HTTP_302_FOUND)


@router.post(
    "/logout",
    summary="Sign out",
    description="Clears the session so the next `/me` returns 401. Returns no body.",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={204: {"description": "Session cleared."}},
)
async def logout(request: Request) -> None:
    """Drop every value in the session, ending the signed cookie's authority."""
    request.session.clear()


@router.get(
    "/me",
    summary="Current authenticated user",
    description="""Returns the signed-in user. Under `AUTH_DISABLED` it returns the synthetic dev user
    so the gated frontend renders without Google. Otherwise it reads the session; a missing session or
    a vanished user row yields 401.""",
    response_model=CurrentUserResponse,
    status_code=status.HTTP_200_OK,
    responses={
        200: {"description": "The authenticated (or dev) user."},
        401: {"description": "No active session / not signed in."},
        500: {"description": INTERNAL_ERROR},
    },
)
async def me(request: Request, service: AuthService = Depends(get_auth_service)) -> CurrentUserResponse:
    """Report the current user, honoring the dev bypass and clearing a stale session on a missing row."""
    if settings.auth_disabled:
        return CurrentUserResponse(id=DEV_USER_ID, email="dev@allocio.local", name="Dev User")
    session_user_id = request.session.get("user_id")
    if not session_user_id:
        raise AuthenticationError()
    user = service.get_user(uuid.UUID(session_user_id))
    if user is None:
        request.session.clear()
        raise AuthenticationError()
    return CurrentUserResponse(id=user.id, email=user.email, name=user.name)


async def _resolve_google_claims(request: Request) -> dict:
    """Exchange the callback code and return a plain `sub`/`email`/`name` claims dict.

    Keeps Authlib token/userinfo types out of the service layer. Prefers the OpenID `userinfo`
    parsed from the id_token; falls back to the userinfo endpoint if absent.
    """
    token = await _oauth.google.authorize_access_token(request)
    userinfo = token.get("userinfo") or await _oauth.google.userinfo(token=token)
    return {"sub": userinfo.get("sub"), "email": userinfo.get("email"), "name": userinfo.get("name")}
