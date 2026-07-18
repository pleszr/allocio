"""Pydantic request models. Validate what the API accepts; never imported by services."""
import uuid
from datetime import date
from decimal import Decimal
from typing import Literal, TypeAlias

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

IntervalUnit: TypeAlias = Literal["months", "years"]
TireType: TypeAlias = Literal["summer", "winter", "all_season"]
AssetTemplateKey: TypeAlias = Literal["vehicle"]
ExpenseKind: TypeAlias = Literal["modeled", "other"]
ExpenseSourceType: TypeAlias = Literal["time_based_cost", "usage_based_cost", "maintenance_item"]


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
    subtitle: str | None = Field(
        default=None,
        max_length=200,
        description="Opaque display subtitle the client composes (e.g. '2-bed · Built 1978'); stored verbatim.",
        examples=["2-bed · Built 1978"],
    )
    attributes: dict | None = Field(
        default=None,
        description="Opaque free-form detail object for non-vehicle assets; the backend never interprets its keys.",
        examples=[{"built": "1978", "size": "85"}],
    )

    @field_validator("attributes")
    @classmethod
    def _bound_attributes(cls, value: dict | None) -> dict | None:
        """Reject an oversized opaque blob (DoS guard): cap key count and require scalar values."""
        if value is None:
            return value
        if len(value) > 30:
            raise ValueError("attributes may hold at most 30 keys.")
        for key, item in value.items():
            if not isinstance(item, (str, int, float, bool)) and item is not None:
                raise ValueError(f"attributes['{key}'] must be a scalar value.")
            if isinstance(item, str) and len(item) > 500:
                raise ValueError(f"attributes['{key}'] is too long.")
        return value

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
    first_due_date: date | None = Field(
        default=None,
        description="Anchor date of a known occurrence; the next-due date is rolled forward from it. Optional.",
        examples=["2026-09-01"],
    )
    notes: str | None = Field(default=None, max_length=2000, description="Optional free-text notes for the cost.")


class UpdateTimeBasedCostRequest(BaseModel):
    """Partial update for a time-based cost. Only fields the client sends are applied."""

    label: str | None = Field(default=None, max_length=120, description="Human-readable cost label.")
    amount: Decimal | None = Field(default=None, ge=0, description="Cost amount per interval.")
    interval_value: int | None = Field(default=None, gt=0, description="Number of interval units between occurrences.")
    interval_unit: IntervalUnit | None = Field(default=None, description="Unit of the recurrence interval.")
    first_due_date: date | None = Field(
        default=None,
        description="Anchor date of a known occurrence. Send null to clear it; omit to leave it unchanged.",
        examples=["2026-09-01"],
    )
    notes: str | None = Field(default=None, max_length=2000, description="Optional free-text notes for the cost.")
    is_active: bool | None = Field(default=None, description="Whether the cost row drives future calculations.")


class CreateUsageBasedCostRequest(BaseModel):
    """Body for adding a usage-based cost component. Currency is derived from the bucket, not accepted here."""

    label: str = Field(description="Human-readable component label.", max_length=120, examples=["Fuel"])
    amount_per_unit: Decimal = Field(ge=0, description="Amount accrued per unit of usage.", examples=[10])
    usage_unit: str = Field(default="km", max_length=20, description="Unit the component accrues per (e.g. km).")
    notes: str | None = Field(default=None, max_length=2000, description="Optional free-text notes for the component.")


class UpdateUsageBasedCostRequest(BaseModel):
    """Partial update for a usage-based cost component, addressed by id. Only fields the client sends are applied.

    The row can be toggled active/inactive; `technical_key` and `currency` are never editable. Extra keys
    are accepted here so the service-layer whitelist (`_apply_changes`) rejects non-editable fields such
    as `currency`/`technical_key` with a 422, rather than pydantic silently dropping them.
    """

    model_config = ConfigDict(extra="allow")

    label: str | None = Field(default=None, max_length=120, description="Human-readable component label.")
    amount_per_unit: Decimal | None = Field(default=None, ge=0, description="Amount accrued per unit of usage.")
    usage_unit: str | None = Field(default=None, max_length=20, description="Unit the component accrues per (e.g. km).")
    notes: str | None = Field(default=None, max_length=2000, description="Optional free-text notes for the component.")
    is_active: bool | None = Field(default=None, description="Whether the component drives future calculations.")


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


class LogExpenseRequest(BaseModel):
    """Body for logging an auditable expense against an asset's bucket.

    A `modeled` expense links a cost/maintenance source row; an `other` expense is a manual entry
    described by its `comment` and must carry no source reference.
    """

    kind: ExpenseKind = Field(
        description="Whether this is a modeled cost/maintenance expense or a manual 'other' entry.",
        examples=["other"],
    )
    amount: Decimal = Field(
        gt=0, description="Outflow amount; stored positive (balance math subtracts it).", examples=[15000]
    )
    event_date: date | None = Field(
        default=None,
        description="When the expense occurred; defaults to today when omitted, allowing backdated events.",
        examples=["2026-07-01"],
    )
    usage_counter_at_event: int | None = Field(
        default=None, ge=0, description="Optional usage reading (e.g. odometer km) at the time of the expense.",
        examples=[123456],
    )
    comment: str | None = Field(
        default=None,
        max_length=2000,
        description="Free-text note; primary descriptor for a manual 'other' expense.",
        examples=["car wash"],
    )
    source_type: ExpenseSourceType | None = Field(
        default=None,
        description="Which cost/maintenance table the source row lives in; required for 'modeled'.",
        examples=["time_based_cost"],
    )
    source_id: uuid.UUID | None = Field(
        default=None, description="Id of the source row; required for 'modeled'."
    )

    @model_validator(mode="after")
    def _check_source_matches_kind(self) -> "LogExpenseRequest":
        """Enforce that a source reference is present for 'modeled' and absent for 'other'."""
        has_source = self.source_type is not None and self.source_id is not None
        if self.kind == "modeled" and not has_source:
            raise ValueError("A modeled expense requires both source_type and source_id.")
        if self.kind == "other" and (self.source_type is not None or self.source_id is not None):
            raise ValueError("An 'other' expense must not carry a source reference.")
        return self


class PreviewCheckInRequest(BaseModel):
    """Body for previewing a check-in period. `period_start`, `usage_start`, and `usage_amount` are server-derived.

    Each item in `expenses` reuses the standalone expense contract (`LogExpenseRequest`): a `modeled`
    entry links a source row, an `other` entry carries no source. Preview writes nothing.
    """

    period_end: date = Field(
        description="End of the period being reviewed; must be later than the derived period start.",
        examples=["2026-05-01"],
    )
    usage_end: int = Field(
        ge=0, description="Usage counter (e.g. odometer km) at period end; must be >= the derived usage start.",
        examples=[345814],
    )
    active_tire_type: TireType | None = Field(
        default=None, description="Tire type active during the period, for tire-aware maintenance tracking."
    )
    expenses: list[LogExpenseRequest] = Field(
        default_factory=list, description="Expenses to recognize against the bucket for this period."
    )


class PostCheckInRequest(PreviewCheckInRequest):
    """Body for posting a check-in. Same fields as the preview plus optional `notes`; persists the result."""

    notes: str | None = Field(
        default=None, max_length=2000, description="Optional free-text note stored on the posted check-in."
    )


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
