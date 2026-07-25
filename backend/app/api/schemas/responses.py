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
    reference_amount: Decimal = Field(
        description="Current amount after applying the latest linked modeled-expense rollover."
    )
    annualized_amount: Decimal = Field(description="Backend-derived yearly equivalent of the reference amount.")
    daily_rate: Decimal = Field(description="Backend-derived per-day rate of the reference amount.")
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
    amount: Decimal = Field(description="Full real-world expense amount; stored positive.")
    bucket_amount: Decimal = Field(description="Portion of the expense covered by the virtual bucket.")
    paid_out_of_pocket: Decimal = Field(description="Derived remainder paid outside the virtual bucket.")
    comment: str | None = Field(description="Free-text note describing the expense, if any.")
    source_type: str | None = Field(description="Source table for a modeled expense, else null.")
    source_id: uuid.UUID | None = Field(description="Id of the linked source row for a modeled expense, else null.")
    metadata_json: dict | None = Field(description="Reserved auditing metadata; unused in this flow.")


class AllocationLineResponse(BaseModel):
    """One previewed allocation (inflow) line for a check-in period."""

    source_type: str = Field(
        description="Accrual source: 'time_based_cost', 'usage_based_cost', or 'manual_extra'."
    )
    source_id: uuid.UUID | None = Field(description="Id of the cost row that produced this line.")
    label: str = Field(description="Human-readable label of the source cost row.", examples=["Vehicle inspection"])
    amount: Decimal = Field(description="Accrual added to the bucket for this line, rounded to currency.")


class ExpenseLineResponse(BaseModel):
    """One previewed expense (outflow) line echoing a submitted draft, with `event_date` resolved."""

    kind: str = Field(description="'modeled' for a cost/maintenance expense or 'other' for a manual entry.")
    amount: Decimal = Field(description="Full real-world expense amount; stored positive.")
    bucket_amount: Decimal = Field(description="Portion covered by the virtual bucket.")
    paid_out_of_pocket: Decimal = Field(description="Derived remainder paid outside the virtual bucket.")
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
    usage_start: int | None = Field(description="Derived usage counter at period start, or null for non-usage assets.")
    usage_end: int | None = Field(description="Requested usage counter at period end, or null for non-usage assets.")
    elapsed_days: int = Field(description="Whole calendar days in the period.")
    usage_amount: int | None = Field(description="Usage counted this period, or null for non-usage assets.")
    active_tire_type: str | None = Field(description="Tire type active during the period, if supplied.")
    allocation_lines: list[AllocationLineResponse] = Field(description="Per-cost allocation lines for the period.")
    expense_lines: list[ExpenseLineResponse] = Field(description="Expense lines recognized for the period.")
    balance_before: Decimal = Field(description="Bucket balance from posted events before this period.")
    total_allocation: Decimal = Field(description="Sum of allocation line amounts.")
    total_expense: Decimal = Field(description="Sum of full real-world expense amounts.")
    total_bucket_expense: Decimal = Field(description="Sum of expense portions covered by the bucket.")
    paid_out_of_pocket: Decimal = Field(description="Sum of expense remainders paid outside the bucket.")
    net_bucket_change: Decimal = Field(description="total_allocation - total_bucket_expense.")
    balance_after: Decimal = Field(description="Non-negative bucket balance after covered expenses.")


class AllocationEventResponse(BaseModel):
    """A posted, immutable allocation event moving value into an asset's bucket."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID = Field(description="Server-generated allocation event id.")
    bucket_id: uuid.UUID = Field(description="Bucket the allocation is added to.")
    check_in_id: uuid.UUID = Field(description="Check-in that posted this allocation.")
    event_date: date = Field(description="Date the allocation is recognized (the period end).")
    source_type: str = Field(
        description="Accrual source: 'time_based_cost', 'usage_based_cost', or 'manual_extra'."
    )
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


class CheckInDetailResponse(BaseModel):
    """One posted check-in's immutable period plus its posted allocation/expense lines, for the edit screen."""

    check_in_id: uuid.UUID = Field(description="The posted check-in this detail describes.")
    period_end: date = Field(description="The check-in's period end date; immutable once posted.")
    usage_end: int | None = Field(description="Usage counter at period end, or null for non-usage assets.")
    active_tire_type: str | None = Field(description="Tire type active during the period, if supplied.")
    elapsed_days: int = Field(description="Whole calendar days covered by this period.")
    usage_amount: int | None = Field(description="Usage counted this period, or null for non-usage assets.")
    allocation_lines: list[AllocationLineResponse] = Field(description="The check-in's posted allocation lines.")
    expense_lines: list[ExpenseLineResponse] = Field(description="The check-in's posted expense lines.")
    notes: str | None = Field(description="The check-in's stored free-text note, if any.")


class EditCheckInPreviewResponse(BaseModel):
    """Previewed result of an expense-only edit to a posted check-in; computed without writing any records.

    Mirrors `CheckInPreviewResponse` minus `asset_id`/`period_start`/`usage_start` (unchanged and
    already known from the earlier `GET` call), plus the edit-only validity fields, so the frontend
    can reuse its existing preview rendering for both a new check-in and an edit.
    """

    period_end: date = Field(description="The check-in's period end date; immutable once posted.")
    usage_end: int | None = Field(description="Usage counter at period end, or null for non-usage assets.")
    active_tire_type: str | None = Field(description="Tire type active during the period, if supplied.")
    elapsed_days: int = Field(description="Whole calendar days covered by this period.")
    usage_amount: int | None = Field(description="Usage counted this period, or null for non-usage assets.")
    allocation_lines: list[AllocationLineResponse] = Field(
        description="The check-in's posted allocation lines; unchanged by an edit."
    )
    expense_lines: list[ExpenseLineResponse] = Field(description="Recomputed expense lines for the submitted edit.")
    balance_before: Decimal = Field(description="Bucket balance from posted events strictly before this period.")
    total_allocation: Decimal = Field(description="The check-in's own posted allocation total; unchanged by an edit.")
    total_expense: Decimal = Field(description="Sum of full real-world expense amounts.")
    total_bucket_expense: Decimal = Field(description="Sum of expense portions covered by the bucket.")
    paid_out_of_pocket: Decimal = Field(description="Sum of expense remainders paid outside the bucket.")
    net_bucket_change: Decimal = Field(description="total_allocation - total_bucket_expense.")
    balance_after: Decimal = Field(description="Non-negative bucket balance after the edit, for this check-in alone.")
    is_valid: bool = Field(
        description="Whether this edit leaves every later already-posted period's balance non-negative."
    )
    first_invalid_check_in_id: uuid.UUID | None = Field(
        description="The first later check-in whose balance would go negative if this edit were applied, else null."
    )
    first_invalid_period_end: date | None = Field(
        description="That check-in's period_end, or null when the edit is valid."
    )


class EditCheckInResponse(BaseModel):
    """Full record set returned after applying a check-in edit, so a client can render it without a refetch."""

    check_in: CheckInResponse = Field(
        description="The updated check-in record (notes only; period/usage/tire fields are unchanged)."
    )
    expense_events: list[ExpenseEventResponse] = Field(description="The check-in's replacement expense events.")


class AssetSummaryResponse(BaseModel):
    """One owned asset with its derived balance and recommended monthly allocation."""

    id: uuid.UUID = Field(description="Server-generated asset id.")
    type: str = Field(description="Asset type, e.g. 'vehicle' or 'house'.", examples=["vehicle"])
    name: str = Field(description="Human-readable asset name.", examples=["My Car"])
    status: str = Field(description="Lifecycle status of the asset.", examples=["active"])
    currency: str = Field(description="ISO currency code of the asset's bucket.", examples=["HUF"])
    balance: Decimal = Field(
        description="Event-derived balance: sum(allocations) - sum(bucket-covered expense portions)."
    )
    recommended_monthly_allocation: Decimal = Field(
        description="Suggested monthly saving: active time-based monthly accruals plus usage-based monthly, quantized."
    )
class WorkspaceTotalsResponse(BaseModel):
    """Workspace-wide totals the Home header renders."""

    total_balance: Decimal = Field(description="Sum of every asset's balance (single-currency MVP).")
    total_recommended_monthly_allocation: Decimal = Field(
        description="Sum of every asset's recommended monthly allocation (single-currency MVP)."
    )
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
        description="Event-derived balance as of this date: allocations minus covered expense portions."
    )


class BalanceHistoryResponse(BaseModel):
    """An asset's monthly bucket-balance series ordered oldest → newest for the dashboard sparkline."""

    asset_id: uuid.UUID = Field(description="Asset whose bucket balance history this is.")
    currency: str = Field(description="ISO currency code of the asset's bucket.", examples=["HUF"])
    points: list[BalancePointResponse] = Field(description="Monthly balance points ordered oldest → newest.")


class CheckInHistoryRowResponse(BaseModel):
    """One posted check-in's ledger row for the History tab, in period order."""

    check_in_id: uuid.UUID = Field(description="The posted check-in this row reports.")
    period_end: date = Field(description="The check-in's period end date.")
    usage_end: int | None = Field(description="Usage counter at period end (e.g. odometer), or null.")
    usage_since_last: int | None = Field(description="Usage counted during this period, or null.")
    elapsed_days: int = Field(description="Whole calendar days covered by this period.")
    allocated: Decimal = Field(description="Total posted allocation amount for this check-in.")
    expense: Decimal = Field(description="Full real-world expense total for this check-in.")
    bucket_expense: Decimal = Field(description="Expense total covered by the virtual bucket.")
    paid_out_of_pocket: Decimal = Field(description="Expense total paid outside the virtual bucket.")
    net: Decimal = Field(description="allocated - bucket_expense for this check-in.")
    balance: Decimal = Field(description="Running bucket balance after this check-in.")
    expenses: list[ExpenseLineResponse] = Field(
        description="Individual expense line items funded during this check-in, oldest first."
    )


class CheckInHistoryResponse(BaseModel):
    """An asset's posted check-in ledger ordered oldest → newest for the History tab."""

    asset_id: uuid.UUID = Field(description="Asset whose check-in ledger this is.")
    currency: str = Field(description="ISO currency code of the asset's bucket.", examples=["HUF"])
    rows: list[CheckInHistoryRowResponse] = Field(description="Ledger rows ordered oldest → newest.")


class ActivityItemResponse(BaseModel):
    """One recent bucket movement for the dashboard activity feed."""

    event_date: date = Field(description="Date the movement was recognized.")
    kind: Literal["allocation", "expense"] = Field(
        description="'allocation' for an inflow into the bucket, 'expense' for an outflow."
    )
    label: str = Field(description="Human-readable label: allocation source or expense comment.")
    amount: Decimal = Field(description="Signed covered bucket movement.")
    paid_out_of_pocket: Decimal = Field(description="Expense remainder paid outside the bucket; zero for allocations.")


class UpcomingExpenseResponse(BaseModel):
    """One forecasted cost within the dashboard's 90-day upcoming-expenses window."""

    name: str = Field(description="Human-readable label of the cost or maintenance item.")
    category: Literal["time_based", "maintenance"] = Field(description="What kind of cost this forecast row is.")
    days_until: int = Field(description="Days until due; 0 means due now or already overdue.")
    amount: Decimal = Field(description="Forecasted cost amount.")
    overdue: bool = Field(description="True for an already-overdue maintenance item.")


class ManualExtraResponse(BaseModel):
    """The updated manual extra monthly buffer, returned by the manual-extra write route."""

    manual_extra_monthly: Decimal = Field(description="The updated manual extra monthly buffer.")


class AverageAllocationResponse(BaseModel):
    """Adaptive trailing average of posted allocation totals for the dashboard."""

    months: Literal[3, 6, 12] = Field(description="Selected trailing history window in months.")
    amount: Decimal | None = Field(
        description="Arithmetic mean of posted check-in allocation totals inside the selected window; null when empty."
    )


class AssetDetailResponse(BaseModel):
    """One asset's composed dashboard payload: derived figures, usage, maintenance, and recent activity."""

    id: uuid.UUID = Field(description="Server-generated asset id.")
    type: str = Field(description="Asset type, e.g. 'vehicle' or 'house'.", examples=["vehicle"])
    name: str = Field(description="Human-readable asset name.", examples=["My Car"])
    status: str = Field(description="Lifecycle status of the asset.", examples=["active"])
    currency: str = Field(description="ISO currency code of the asset's bucket.", examples=["HUF"])
    balance: Decimal = Field(
        description="Event-derived balance: sum(allocations) - sum(bucket-covered expense portions)."
    )
    recommended_monthly_allocation: Decimal = Field(
        description="Suggested monthly saving; also the 'next allocation' amount the dashboard shows. Includes "
        "the active time-based and usage-based accruals plus manual_extra_monthly. The next-allocation date and "
        "pending accrual are intentionally omitted pending a product decision on cadence."
    )
    manual_extra_monthly: Decimal = Field(
        description="User-set flat monthly buffer added on top of the modeled time- and usage-based accruals."
    )
    manual_extra_recommended: Decimal = Field(
        description="Derived guidance for manual_extra_monthly from the last 12 months' expense/allocation gap, "
        "floored at zero. Informational only — never overwrites the stored value."
    )
    average_monthly_usage: Decimal = Field(
        description="Trailing average usage per month across all posted check-ins; zero without enough data."
    )
    average_allocation: AverageAllocationResponse = Field(
        description="Backend-derived adaptive 3/6/12-month average of posted check-in allocation totals."
    )
    daily_accrual: Decimal = Field(
        description="Per-day accrual derived as recommended_monthly_allocation * 12 / 365, quantized to currency."
    )
    tracks_usage: bool = Field(
        description="Whether this asset has a usage-tracking profile and should collect a usage counter."
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
    upcoming_expenses: list[UpcomingExpenseResponse] = Field(
        description="Forecasted costs due within 90 days, ordered soonest first."
    )


class TemplateTimeBasedCostItem(BaseModel):
    """One pickable time-based cost row in a template catalog."""

    technical_key: str = Field(description="Stable template key identifying this cost.", examples=["comprehensive_insurance"])
    label: str = Field(description="Human-readable cost label.", examples=["Comprehensive insurance"])
    amounts: dict[str, Decimal] = Field(
        description="Default amount per interval, keyed by currency code (HUF/EUR/USD).",
        examples=[{"HUF": "11650", "EUR": "29", "USD": "32"}],
    )
    interval_value: int = Field(description="Number of interval units between occurrences.", examples=[12])
    interval_unit: str = Field(description="Unit of the recurrence interval.", examples=["months"])


class TemplateUsageBasedCostItem(BaseModel):
    """The pickable usage-based reserve row in a template catalog."""

    technical_key: str = Field(description="Stable template key identifying this reserve.", examples=["usage_based_reserve"])
    label: str = Field(description="Human-readable reserve label.", examples=["Usage-based reserve"])
    amounts_per_unit: dict[str, Decimal] = Field(
        description="Default reserve amount accrued per usage unit, keyed by currency code (HUF/EUR/USD).",
        examples=[{"HUF": "10", "EUR": "0.025", "USD": "0.03"}],
    )
    usage_unit: str = Field(description="Unit the reserve accrues per (e.g. km).", examples=["km"])


class TemplateMaintenanceItem(BaseModel):
    """One pickable maintenance/replacement item in a template catalog."""

    technical_key: str = Field(description="Stable template key identifying this item.", examples=["all_season_tires"])
    label: str = Field(description="Human-readable item label.", examples=["All-season tires"])
    interval_km: int | None = Field(description="Kilometer interval between services, if any.", examples=[50000])
    interval_months: int | None = Field(description="Month interval between services, if any.", examples=[36])
    tire_type: str | None = Field(description="Tire type for tire items, if applicable.", examples=["all_season"])
    estimated_costs: dict[str, Decimal] | None = Field(
        description="Estimated cost per currency code (HUF/EUR/USD), if curated; null when none exists yet."
    )


class AssetTemplateCatalogResponse(BaseModel):
    """The complete pickable default cost set for a creation template, grouped for the picker UI."""

    template_key: str = Field(description="The template whose catalog this is.", examples=["vehicle"])
    time_based_costs: list[TemplateTimeBasedCostItem] = Field(description="Pickable recurring time-based cost rows.")
    usage_based_costs: list[TemplateUsageBasedCostItem] = Field(
        description="Pickable per-usage-unit reserve rows (a list for a uniform client shape; vehicle has one)."
    )
    maintenance_items: list[TemplateMaintenanceItem] = Field(description="Pickable maintenance/replacement item rows.")


class AllocationEstimateLineResponse(BaseModel):
    """Canonical monetary rates for one selected or custom recurring row."""

    key: str
    label: str
    reference_amount: Decimal
    annualized_amount: Decimal
    monthly_amount: Decimal
    daily_rate: Decimal


class AllocationEstimateResponse(BaseModel):
    """Non-persisted allocation estimate for the asset-creation review."""

    currency: str
    lines: list[AllocationEstimateLineResponse]
    daily_total: Decimal
    monthly_total: Decimal
    yearly_total: Decimal


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
