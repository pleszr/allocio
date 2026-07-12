"""Pydantic request models. Validate what the API accepts; never imported by services."""
from pydantic import BaseModel, Field


class CreateVehicleRequest(BaseModel):
    """Body for creating a vehicle. `user_id` and bucket currency are server-set, not accepted here."""

    name: str = Field(
        description="Human-readable vehicle name shown in the UI.", max_length=120, examples=["My Car"]
    )
    year: int | None = Field(default=None, description="Model year of the vehicle.", examples=[2018])
    make: str | None = Field(
        default=None, description="Manufacturer of the vehicle.", max_length=60, examples=["Toyota"]
    )
    model: str | None = Field(
        default=None, description="Model name of the vehicle.", max_length=60, examples=["Corolla"]
    )
    starting_odometer: int = Field(
        default=0, ge=0, description="Odometer reading in kilometers at creation time.", examples=[120000]
    )
