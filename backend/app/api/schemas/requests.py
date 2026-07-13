"""Pydantic request models. Validate what the API accepts; never imported by services."""
from datetime import date
from decimal import Decimal
from typing import Literal, TypeAlias

from pydantic import BaseModel, Field, model_validator

IntervalUnit: TypeAlias = Literal["months", "years"]
TireType: TypeAlias = Literal["summer", "winter", "all_season"]
AssetTemplateKey: TypeAlias = Literal["vehicle"]


class VehicleDetailsInput(BaseModel):
    """Vehicle-profile fields, accepted only when the vehicle template is selected."""

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


class CreateAssetRequest(BaseModel):
    """Body for creating an asset. `user_id` and bucket currency are server-set, not accepted here.

    A bare asset needs a free-form `type`. Selecting a `template` prefills the type and default cost
    rows instead; the vehicle template additionally accepts a `vehicle` detail block.
    """

    name: str = Field(
        description="Human-readable asset name shown in the UI.", max_length=120, examples=["My Car"]
    )
    type: str | None = Field(
        default=None,
        max_length=60,
        description="Free-form asset type. Required for a bare asset; a template supplies it otherwise.",
        examples=["house"],
    )
    template: AssetTemplateKey | None = Field(
        default=None,
        description="Built-in creation template to apply. Omit for a bare asset with no default rows.",
        examples=["vehicle"],
    )
    vehicle: VehicleDetailsInput | None = Field(
        default=None, description="Vehicle profile details; only valid with the vehicle template."
    )

    @model_validator(mode="after")
    def _check_template_and_type(self) -> "CreateAssetRequest":
        """Enforce the template/type/vehicle-block rules that a single field cannot express."""
        if self.template is None:
            if not self.type:
                raise ValueError("A template-less asset must set a type.")
            if self.vehicle is not None:
                raise ValueError("Vehicle details require the vehicle template.")
            return self
        if self.template == "vehicle" and self.type not in (None, "vehicle"):
            raise ValueError("The vehicle template sets type to 'vehicle'; a conflicting type is not allowed.")
        return self


class CreateTimeBasedCostRequest(BaseModel):
    """Body for adding a custom time-based cost row. `technical_key` stays null for user rows."""

    label: str = Field(description="Human-readable cost label.", max_length=120, examples=["Vehicle inspection"])
    amount: Decimal = Field(ge=0, description="Cost amount per interval.", examples=[25000])
    interval_value: int = Field(gt=0, description="Number of interval units between occurrences.", examples=[12])
    interval_unit: IntervalUnit = Field(description="Unit of the recurrence interval.", examples=["months"])
    notes: str | None = Field(default=None, max_length=2000, description="Optional free-text notes for the cost.")


class UpdateTimeBasedCostRequest(BaseModel):
    """Partial update for a time-based cost. Only fields the client sends are applied."""

    label: str | None = Field(default=None, max_length=120, description="Human-readable cost label.")
    amount: Decimal | None = Field(default=None, ge=0, description="Cost amount per interval.")
    interval_value: int | None = Field(default=None, gt=0, description="Number of interval units between occurrences.")
    interval_unit: IntervalUnit | None = Field(default=None, description="Unit of the recurrence interval.")
    notes: str | None = Field(default=None, max_length=2000, description="Optional free-text notes for the cost.")
    is_active: bool | None = Field(default=None, description="Whether the cost row drives future calculations.")


class UpdateUsageBasedCostRequest(BaseModel):
    """Partial update for the single usage-based reserve. The reserve is never toggled here."""

    amount_per_unit: Decimal | None = Field(default=None, ge=0, description="Reserve amount accrued per usage unit.")
    notes: str | None = Field(default=None, max_length=2000, description="Optional free-text notes for the reserve.")


class CreateMaintenanceItemRequest(BaseModel):
    """Body for adding a custom maintenance item. Requires at least one service interval."""

    label: str = Field(description="Human-readable item label.", max_length=120, examples=["Brake pads"])
    interval_km: int | None = Field(default=None, gt=0, description="Kilometer interval between services, if any.")
    interval_months: int | None = Field(default=None, gt=0, description="Month interval between services, if any.")
    last_serviced_at_date: date | None = Field(default=None, description="Date the item was last serviced, if known.")
    last_serviced_at_odometer: int | None = Field(
        default=None, ge=0, description="Odometer at last service in kilometers, if known."
    )
    estimated_cost: Decimal | None = Field(default=None, ge=0, description="Estimated cost of the item, if known.")
    tire_type: TireType | None = Field(default=None, description="Tire type for tire items, if applicable.")
    notes: str | None = Field(default=None, max_length=2000, description="Optional free-text notes for the item.")

    @model_validator(mode="after")
    def _require_an_interval(self) -> "CreateMaintenanceItemRequest":
        """Reject a custom item with no interval: only the seeded `other` row may omit both."""
        if self.interval_km is None and self.interval_months is None:
            raise ValueError("A maintenance item must set interval_km or interval_months.")
        return self


class UpdateMaintenanceItemRequest(BaseModel):
    """Partial update for a maintenance item. The interval rule is enforced in the service post-merge."""

    label: str | None = Field(default=None, max_length=120, description="Human-readable item label.")
    interval_km: int | None = Field(default=None, gt=0, description="Kilometer interval between services, if any.")
    interval_months: int | None = Field(default=None, gt=0, description="Month interval between services, if any.")
    last_serviced_at_date: date | None = Field(default=None, description="Date the item was last serviced, if known.")
    last_serviced_at_odometer: int | None = Field(
        default=None, ge=0, description="Odometer at last service in kilometers, if known."
    )
    estimated_cost: Decimal | None = Field(default=None, ge=0, description="Estimated cost of the item, if known.")
    tire_type: TireType | None = Field(default=None, description="Tire type for tire items, if applicable.")
    notes: str | None = Field(default=None, max_length=2000, description="Optional free-text notes for the item.")
    is_active: bool | None = Field(default=None, description="Whether the item drives future calculations.")
