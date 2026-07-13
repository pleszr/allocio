"""FastAPI app composition. Mounts routers; holds no business logic."""
from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse

from app.api import assets, costs, health
from app.common.exceptions import NotFoundError, ValidationError

app = FastAPI(title="Allocio API")

app.include_router(health.router)
app.include_router(assets.router)
app.include_router(costs.router)


@app.exception_handler(NotFoundError)
async def _not_found_handler(_: Request, exc: NotFoundError) -> JSONResponse:
    return JSONResponse(status_code=status.HTTP_404_NOT_FOUND, content={"detail": str(exc)})


@app.exception_handler(ValidationError)
async def _validation_handler(_: Request, exc: ValidationError) -> JSONResponse:
    return JSONResponse(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, content={"detail": str(exc)})
