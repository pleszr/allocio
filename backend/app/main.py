"""FastAPI app composition. Mounts routers; holds no business logic."""
from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse

from app.api import health, vehicles
from app.common.exceptions import NotFoundError

app = FastAPI(title="Allocio API")

app.include_router(health.router)
app.include_router(vehicles.router)


@app.exception_handler(NotFoundError)
async def _not_found_handler(_: Request, exc: NotFoundError) -> JSONResponse:
    return JSONResponse(status_code=status.HTTP_404_NOT_FOUND, content={"detail": str(exc)})
