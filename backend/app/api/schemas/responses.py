"""Pydantic response models. Shape what the API returns; never imported by services."""
from pydantic import BaseModel, ConfigDict, Field


class GreetingResponse(BaseModel):
    """The first seeded greeting."""

    model_config = ConfigDict(from_attributes=True)

    id: int = Field(description="Stable greeting id from the database.", examples=[1])
    message: str = Field(description="Greeting message text.", examples=["hello world"])


class HealthResponse(BaseModel):
    """Liveness response."""

    status: str = Field(description="Service status. Always 'ok' on success.", examples=["ok"])
