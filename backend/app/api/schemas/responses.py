"""Pydantic response models. Shape what the API returns; never imported by services."""
from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    """Liveness response."""

    status: str = Field(description="Service status. Always 'ok' on success.", examples=["ok"])
