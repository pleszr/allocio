"""Pydantic response models. Shape what the API returns; never imported by services."""
import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class HealthResponse(BaseModel):
    """Liveness response."""

    status: str = Field(description="Service status. Always 'ok' on success.", examples=["ok"])


class CurrentUserResponse(BaseModel):
    """The authenticated user, as returned by `GET /api/auth/me`."""

    id: uuid.UUID = Field(description="Server-generated user id; owner of every asset and bucket.")
    email: str = Field(description="The user's Google account email.", examples=["ada@example.com"])
    name: str = Field(description="The user's Google display name; may be empty.", examples=["Ada Lovelace"])


class UserSettingsResponse(BaseModel):
    """The caller's persisted workspace-wide settings, as returned by the settings read/replace routes."""

    model_config = ConfigDict(from_attributes=True)

    default_currency: str = Field(
        description="Workspace-wide display currency (relabel only, no FX).", examples=["HUF"]
    )
    language: str = Field(
        description="Persisted language preference; stored only for now (no UI translation yet).", examples=["en"]
    )


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
    first_due_date: date | None = Field(description="Stored anchor date of a known occurrence, if set.")
    next_due_date: date | None = Field(
        default=None,
        description="Computed next occurrence on or after today, rolled forward from the anchor; null when no anchor is set.",
    )
    notes: str | None = Field(description="Optional free-text notes for the cost.")
    is_active: bool = Field(description="Whether the cost row drives future calculations.")


class UsageBasedCostResponse(BaseModel):
    """One usage-based cost component of an asset, accruing its amount per unit of usage."""

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
    # Computed read-model fields; set explicitly by the maintenance read/POST/PATCH serializer. They
    # default to null on the asset-creation embed (`CreateAssetResponse`), which carries no live status
    # because a just-created asset has no usage history yet — the client reads status from a list/detail call.
    status: Literal["ok", "soon", "due", "overdue"] | None = Field(
        default=None,
        description="Calculator-derived service status from the greater progress ratio; the earlier "
        "threshold wins. The design renders 'due' as a 'Due soon'-style pill. Null only on the "
        "asset-creation embed.",
        examples=["soon"],
    )
    km_since_service: int | None = Field(
        default=None,
        description="Distance driven since last service (current usage minus last-serviced odometer); "
        "null without both an odometer reading and a last-serviced odometer.",
    )
    months_since_service: int | None = Field(
        default=None,
        description="Whole months since last service; null when the item has no last-serviced date.",
    )
    km_progress: Decimal | None = Field(
        default=None,
        description="Distance progress ratio (km since service / km interval); null when either is missing.",
    )
    month_progress: Decimal | None = Field(
        default=None,
        description="Time progress ratio (months since service / month interval); null when either is missing.",
    )
    remaining_km: int | None = Field(
        default=None,
        description="Kilometers remaining until the next service, floored at 0; null without a km interval and reading.",
    )
    remaining_months: int | None = Field(
        default=None,
        description="Months remaining until the next service, floored at 0; null without a month interval and date.",
    )


class ExpenseEventResponse(BaseModel):
    """A posted, immutable expense event drawn against an asset's bucket."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID = Field(description="Server-generated expense event id.")
    bucket_id: uuid.UUID = Field(description="Bucket the expense is drawn against.")
    check_in_id: uuid.UUID | None = Field(description="Owning check-in, if the event was posted by one.")
    event_date: date = Field(description="Date the expense occurred.")
    usage_counter_at_event: int | None = Field(description="Usage reading at the time of the expense, if supplied.")
    kind: str = Field(description="'modeled' for a cost/maintenance expense or 'other' for a manual entry.")
    amount: Decimal = Field(description="Outflow amount; stored positive.")
    comment: str | None = Field(description="Free-text note describing the expense, if any.")
    source_type: str | None = Field(description="Source table for a modeled expense, else null.")
    source_id: uuid.UUID | None = Field(description="Id of the linked source row for a modeled expense, else null.")
    metadata_json: dict | None = Field(description="Reserved auditing metadata; unused in this flow.")


class AllocationLineResponse(BaseModel):
    """One previewed allocation (inflow) line for a check-in period."""

    source_type: str = Field(description="Source table of the accrual: 'time_based_cost' or 'usage_based_cost'.")
    source_id: uuid.UUID | None = Field(description="Id of the cost row that produced this line.")
    label: str = Field(description="Human-readable label of the source cost row.", examples=["Vehicle inspection"])
    amount: Decimal = Field(description="Accrual added to the bucket for this line, rounded to currency.")


class ExpenseLineResponse(BaseModel):
    """One previewed expense (outflow) line echoing a submitted draft, with `event_date` resolved."""

    kind: str = Field(description="'modeled' for a cost/maintenance expense or 'other' for a manual entry.")
    amount: Decimal = Field(description="Outflow amount; stored positive.")
    event_date: date = Field(description="Date the expense occurred; resolved to today when the draft omitted it.")
    comment: str | None = Field(description="Free-text note describing the expense, if any.")
    source_type: str | None = Field(description="Source table for a modeled expense, else null.")
    source_id: uuid.UUID | None = Field(description="Id of the linked source row for a modeled expense, else null.")
    usage_counter_at_event: int | None = Field(description="Usage reading at the time of the expense, if supplied.")


class CheckInPreviewResponse(BaseModel):
    """Deterministic financial result of a check-in period; computed without writing any records."""

    asset_id: uuid.UUID = Field(description="Asset the check-in is for.")
    period_start: date = Field(description="Derived start of the period (previous period end, or first-check-in start).")
    period_end: date = Field(description="Requested end of the period.")
    usage_start: int = Field(description="Derived usage counter at period start.")
    usage_end: int = Field(description="Requested usage counter at period end.")
    elapsed_days: int = Field(description="Whole calendar days in the period.")
    usage_amount: int = Field(description="Usage counted this period (usage_end - usage_start).")
    active_tire_type: str | None = Field(description="Tire type active during the period, if supplied.")
    allocation_lines: list[AllocationLineResponse] = Field(description="Per-cost allocation lines for the period.")
    expense_lines: list[ExpenseLineResponse] = Field(description="Expense lines recognized for the period.")
    balance_before: Decimal = Field(description="Bucket balance from posted events before this period.")
    total_allocation: Decimal = Field(description="Sum of allocation line amounts.")
    total_expense: Decimal = Field(description="Sum of expense line amounts.")
    net_bucket_change: Decimal = Field(description="total_allocation - total_expense.")
    balance_after: Decimal = Field(description="balance_before + net_bucket_change.")


class AllocationEventResponse(BaseModel):
    """A posted, immutable allocation event moving value into an asset's bucket."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID = Field(description="Server-generated allocation event id.")
    bucket_id: uuid.UUID = Field(description="Bucket the allocation is added to.")
    check_in_id: uuid.UUID = Field(description="Check-in that posted this allocation.")
    event_date: date = Field(description="Date the allocation is recognized (the period end).")
    source_type: str = Field(description="Source table of the accrual: 'time_based_cost' or 'usage_based_cost'.")
    source_id: uuid.UUID | None = Field(description="Id of the cost row that produced this allocation.")
    amount: Decimal = Field(description="Allocation amount added to the bucket.")
    metadata_json: dict | None = Field(description="Auditing metadata explaining the source row, e.g. its label.")


class CheckInResponse(BaseModel):
    """A posted check-in record for one asset period."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID = Field(description="Server-generated check-in id.")
    asset_id: uuid.UUID = Field(description="Asset the check-in is for.")
    period_start: date = Field(description="Start of the covered period.")
    period_end: date = Field(description="End of the covered period.")
    checked_in_at: datetime | None = Field(description="Server timestamp when the check-in was posted.")
    usage_start: int | None = Field(description="Usage counter at period start.")
    usage_end: int | None = Field(description="Usage counter at period end.")
    usage_amount: int | None = Field(description="Usage counted this period.")
    active_tire_type: str | None = Field(description="Tire type active during the period, if supplied.")
    notes: str | None = Field(description="Optional free-text note stored on the check-in.")
    status: str = Field(description="Lifecycle status; 'posted' once persisted.", examples=["posted"])


class CheckInPostResponse(BaseModel):
    """Full record set created by posting a check-in, so a client can render it without a refetch."""

    check_in: CheckInResponse = Field(description="The posted check-in record.")
    allocation_events: list[AllocationEventResponse] = Field(description="Posted allocation events for the period.")
    expense_events: list[ExpenseEventResponse] = Field(description="Posted expense events for the period.")


class AssetSummaryResponse(BaseModel):
    """One owned asset with its derived balance, recommended monthly allocation, and health status."""

    id: uuid.UUID = Field(description="Server-generated asset id.")
    type: str = Field(description="Asset type, e.g. 'vehicle' or 'house'.", examples=["vehicle"])
    name: str = Field(description="Human-readable asset name.", examples=["My Car"])
    status: str = Field(description="Lifecycle status of the asset.", examples=["active"])
    currency: str = Field(description="ISO currency code of the asset's bucket.", examples=["HUF"])
    balance: Decimal = Field(description="Event-derived bucket balance: sum(allocations) - sum(expenses).")
    recommended_monthly_allocation: Decimal = Field(
        description="Suggested monthly saving: active time-based monthly accruals plus usage-based monthly, quantized."
    )
    health: str = Field(
        description="Funding health versus one recommended monthly allocation: 'underfunded', 'healthy', or 'overflowing'.",
        examples=["healthy"],
    )


class WorkspaceTotalsResponse(BaseModel):
    """Workspace-wide totals the Home header renders."""

    total_balance: Decimal = Field(description="Sum of every asset's balance (single-currency MVP).")
    total_recommended_monthly_allocation: Decimal = Field(
        description="Sum of every asset's recommended monthly allocation (single-currency MVP)."
    )
    alert_count: int = Field(description="Number of assets whose health is 'underfunded'.", examples=[1])


class WorkspaceOverviewResponse(BaseModel):
    """Every owned asset summary plus workspace totals, returned in one workspace read."""

    assets: list[AssetSummaryResponse] = Field(description="Every owned, active asset with its derived figures.")
    totals: WorkspaceTotalsResponse = Field(description="Workspace-wide balance, monthly allocation, and alert totals.")


class BalancePointResponse(BaseModel):
    """One monthly point of the reconstructed bucket-balance series."""

    month: str = Field(description="Calendar month of the point, 'YYYY-MM'.", examples=["2026-07"])
    as_of: date = Field(
        description="Date the balance was evaluated at; the newest point is today (partial current month)."
    )
    balance: Decimal = Field(
        description="Event-derived bucket balance as of this date: sum(allocations) - sum(expenses)."
    )


class BalanceHistoryResponse(BaseModel):
    """An asset's monthly bucket-balance series ordered oldest → newest for the dashboard sparkline."""

    asset_id: uuid.UUID = Field(description="Asset whose bucket balance history this is.")
    currency: str = Field(description="ISO currency code of the asset's bucket.", examples=["HUF"])
    points: list[BalancePointResponse] = Field(description="Monthly balance points ordered oldest → newest.")


class ActivityItemResponse(BaseModel):
    """One recent bucket movement for the dashboard activity feed."""

    event_date: date = Field(description="Date the movement was recognized.")
    kind: Literal["allocation", "expense"] = Field(
        description="'allocation' for an inflow into the bucket, 'expense' for an outflow."
    )
    label: str = Field(description="Human-readable label: allocation source or expense comment.")
    amount: Decimal = Field(description="Signed amount: positive for allocations, negative for expenses.")


class AssetDetailResponse(BaseModel):
    """One asset's composed dashboard payload: derived figures, usage, maintenance, and recent activity."""

    id: uuid.UUID = Field(description="Server-generated asset id.")
    type: str = Field(description="Asset type, e.g. 'vehicle' or 'house'.", examples=["vehicle"])
    name: str = Field(description="Human-readable asset name.", examples=["My Car"])
    status: str = Field(description="Lifecycle status of the asset.", examples=["active"])
    currency: str = Field(description="ISO currency code of the asset's bucket.", examples=["HUF"])
    balance: Decimal = Field(description="Event-derived bucket balance: sum(allocations) - sum(expenses).")
    recommended_monthly_allocation: Decimal = Field(
        description="Suggested monthly saving; also the 'next allocation' amount the dashboard shows. The "
        "next-allocation date and pending accrual are intentionally omitted pending a product decision on cadence."
    )
    daily_accrual: Decimal = Field(
        description="Per-day accrual derived as recommended_monthly_allocation * 12 / 365, quantized to currency."
    )
    health: str = Field(
        description="Funding health versus one recommended monthly allocation: 'underfunded', 'healthy', or 'overflowing'.",
        examples=["healthy"],
    )
    current_usage: int | None = Field(
        description="Current usage counter (latest posted check-in usage_end, else vehicle starting odometer); "
        "null for a non-vehicle asset with no usage counter."
    )
    usage_since_last_check_in: int | None = Field(
        description="Usage counted in the most recent posted check-in; null when no check-in is posted."
    )
    last_check_in_date: date | None = Field(
        description="Period end of the most recent posted check-in; null when none is posted."
    )
    maintenance_items: list[MaintenanceItemResponse] = Field(
        description="Every maintenance item with its computed status and progress figures."
    )
    recent_activity: list[ActivityItemResponse] = Field(
        description="Merged allocation and expense movements, newest first, capped for the activity feed."
    )


class TemplateTimeBasedCostItem(BaseModel):
    """One pickable time-based cost row in a template catalog."""

    technical_key: str = Field(description="Stable template key identifying this cost.", examples=["comprehensive_insurance"])
    label: str = Field(description="Human-readable cost label.", examples=["Comprehensive insurance"])
    amount: Decimal = Field(description="Default cost amount per interval.")
    interval_value: int = Field(description="Number of interval units between occurrences.", examples=[12])
    interval_unit: str = Field(description="Unit of the recurrence interval.", examples=["months"])


class TemplateUsageBasedCostItem(BaseModel):
    """The pickable usage-based reserve row in a template catalog."""

    technical_key: str = Field(description="Stable template key identifying this reserve.", examples=["usage_based_reserve"])
    label: str = Field(description="Human-readable reserve label.", examples=["Usage-based reserve"])
    amount_per_unit: Decimal = Field(description="Default reserve amount accrued per usage unit.")
    usage_unit: str = Field(description="Unit the reserve accrues per (e.g. km).", examples=["km"])
    currency: str = Field(description="ISO currency code for the reserve.", examples=["HUF"])


class TemplateMaintenanceItem(BaseModel):
    """One pickable maintenance/replacement item in a template catalog."""

    technical_key: str = Field(description="Stable template key identifying this item.", examples=["all_season_tires"])
    label: str = Field(description="Human-readable item label.", examples=["All-season tires"])
    interval_km: int | None = Field(description="Kilometer interval between services, if any.", examples=[50000])
    interval_months: int | None = Field(description="Month interval between services, if any.", examples=[36])
    tire_type: str | None = Field(description="Tire type for tire items, if applicable.", examples=["all_season"])
    estimated_cost: Decimal | None = Field(description="Estimated cost of the item, if known.")


class AssetTemplateCatalogResponse(BaseModel):
    """The complete pickable default cost set for a creation template, grouped for the picker UI."""

    template_key: str = Field(description="The template whose catalog this is.", examples=["vehicle"])
    time_based_costs: list[TemplateTimeBasedCostItem] = Field(description="Pickable recurring time-based cost rows.")
    usage_based_costs: list[TemplateUsageBasedCostItem] = Field(
        description="Pickable per-usage-unit reserve rows (a list for a uniform client shape; vehicle has one)."
    )
    maintenance_items: list[TemplateMaintenanceItem] = Field(description="Pickable maintenance/replacement item rows.")


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
