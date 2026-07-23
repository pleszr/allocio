"""FastAPI app composition. Mounts routers and middleware; holds no business logic."""
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse
from starlette.middleware.sessions import SessionMiddleware

from app.api import asset_templates, assets, auth, check_ins, costs, expenses, health, users
from app.common.exceptions import AuthenticationError, NotFoundError, ValidationError
from app.config import settings
from app.db import SessionLocal
from app.repository import user_repository
from app.services.dependencies import DEV_USER_ID

# When `session_secret` is unset we must be under the dev bypass (the config validator requires it
# otherwise), so a fixed insecure key lets the middleware mount without real creds.
_SESSION_SECRET = settings.session_secret or "dev-insecure-session-key"


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    """On startup under `AUTH_DISABLED`, ensure the dev user row exists so the asset FK is satisfiable."""
    if settings.auth_disabled:
        session = SessionLocal()
        try:
            user_repository.ensure_dev_user(session, DEV_USER_ID)
            session.commit()
        finally:
            session.close()
    yield


app = FastAPI(title="Allocio API", lifespan=lifespan)

app.add_middleware(SessionMiddleware, secret_key=_SESSION_SECRET, same_site="lax", https_only=False)

app.include_router(health.router)
app.include_router(auth.router)
app.include_router(users.router)
app.include_router(assets.router)
app.include_router(asset_templates.router)
app.include_router(costs.router)
app.include_router(expenses.router)
app.include_router(check_ins.router)


@app.exception_handler(AuthenticationError)
async def _authentication_handler(_: Request, exc: AuthenticationError) -> JSONResponse:
    return JSONResponse(status_code=status.HTTP_401_UNAUTHORIZED, content={"detail": str(exc)})


@app.exception_handler(NotFoundError)
async def _not_found_handler(_: Request, exc: NotFoundError) -> JSONResponse:
    return JSONResponse(status_code=status.HTTP_404_NOT_FOUND, content={"detail": str(exc)})


@app.exception_handler(ValidationError)
async def _validation_handler(_: Request, exc: ValidationError) -> JSONResponse:
    return JSONResponse(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, content={"detail": str(exc)})
