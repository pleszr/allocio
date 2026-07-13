"""Pydantic response models. Shape what the API returns; never imported by services."""
import uuid
from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


class HealthResponse(BaseModel):
    """Liveness response."""

    status: str = Field(description="Service status. Always 'ok' on success.", examples=["ok"])


class AssetResponse(BaseModel):
    """The tracked asset record created for the request."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID = Field(description="Server-generated asset id.")
    user_id: uuid.UUID = Field(description="Owner of the asset.")
    type: str = Field(description="Asset type, e.g. 'vehicle' or 'house'.", examples=["vehicle"])
    name: str = Field(description="Human-readable asset name.", examples=["My Car"])
    status: str = Field(description="Lifecycle status of the asset.", examples=["active"])
    created_at: datetime = Field(description="Server timestamp when the asset was created.")


class VehicleProfileResponse(BaseModel):
    """Vehicle-only metadata for the created asset."""

    model_config = ConfigDict(from_attributes=True)

    asset_id: uuid.UUID = Field(description="Owning asset id (also the primary key).")
    year: int | None = Field(description="Model year of the vehicle.", examples=[2018])
    make: str | None = Field(description="Manufacturer of the vehicle.", examples=["Toyota"])
    model: str | None = Field(description="Model name of the vehicle.", examples=["Corolla"])
    starting_odometer: int = Field(description="Odometer reading in kilometers at creation time.", examples=[120000])


class BucketResponse(BaseModel):
    """The savings bucket opened for the created asset."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID = Field(description="Server-generated bucket id.")
    asset_id: uuid.UUID = Field(description="Owning asset id.")
    currency: str = Field(description="ISO currency code for the bucket.", examples=["HUF"])
    opened_at: datetime = Field(description="Server timestamp when the bucket was opened.")


class TimeBasedCostResponse(BaseModel):
    """A cloned recurring time-driven cost row."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID = Field(description="Server-generated cost row id.")
    asset_id: uuid.UUID = Field(description="Owning asset id.")
    label: str = Field(description="Human-readable cost label.", examples=["Vehicle inspection"])
    technical_key: str | None = Field(description="Stable template key for this cost.", examples=["vehicle_inspection"])
    amount: Decimal = Field(description="Cost amount per interval.")
    interval_value: int = Field(description="Number of interval units between occurrences.", examples=[12])
    interval_unit: str = Field(description="Unit of the recurrence interval.", examples=["months"])
    notes: str | None = Field(description="Optional free-text notes for the cost.")
    is_active: bool = Field(description="Whether the cost row drives future calculations.")


class UsageBasedCostResponse(BaseModel):
    """The cloned per-usage-unit reserve row."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID = Field(description="Server-generated cost row id.")
    asset_id: uuid.UUID = Field(description="Owning asset id.")
    label: str = Field(description="Human-readable cost label.", examples=["Usage-based reserve"])
    technical_key: str | None = Field(
        description="Stable template key for this cost.", examples=["usage_based_reserve"]
    )
    amount_per_unit: Decimal = Field(description="Reserve amount accrued per usage unit.")
    usage_unit: str = Field(description="Unit the reserve accrues per (e.g. km).", examples=["km"])
    currency: str = Field(description="ISO currency code for the reserve.", examples=["HUF"])
    notes: str | None = Field(description="Optional free-text notes for the reserve.")
    is_active: bool = Field(description="Whether the reserve row drives future calculations.")


class MaintenanceItemResponse(BaseModel):
    """A cloned maintenance/replacement item row."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID = Field(description="Server-generated maintenance row id.")
    asset_id: uuid.UUID = Field(description="Owning asset id.")
    label: str = Field(description="Human-readable item label.", examples=["All-season tires"])
    technical_key: str | None = Field(description="Stable template key for this item.", examples=["all_season_tires"])
    interval_km: int | None = Field(description="Kilometer interval between services, if any.", examples=[50000])
    interval_months: int | None = Field(description="Month interval between services, if any.", examples=[36])
    last_serviced_at_date: date | None = Field(description="Date the item was last serviced, if known.")
    last_serviced_at_odometer: int | None = Field(description="Odometer at last service in kilometers, if known.")
    tire_type: str | None = Field(description="Tire type for tire items, if applicable.", examples=["all_season"])
    estimated_cost: Decimal | None = Field(description="Estimated cost of the item, if known.")
    notes: str | None = Field(description="Optional free-text notes for the item.")
    is_active: bool = Field(description="Whether the item drives future calculations.")


class CreateAssetResponse(BaseModel):
    """Full record set returned after creating an asset, so a client can render it without a refetch.

    `profile` is null and the cost lists are empty for a bare (template-less) asset.
    """

    model_config = ConfigDict(from_attributes=True)

    asset: AssetResponse = Field(description="The created asset record.")
    profile: VehicleProfileResponse | None = Field(description="The created vehicle profile, if a template supplied one.")
    bucket: BucketResponse = Field(description="The created savings bucket.")
    time_based_costs: list[TimeBasedCostResponse] = Field(description="Cloned recurring time-based cost rows.")
    usage_based_costs: list[UsageBasedCostResponse] = Field(description="Cloned per-usage-unit reserve rows.")
    maintenance_items: list[MaintenanceItemResponse] = Field(description="Cloned maintenance/replacement item rows.")
