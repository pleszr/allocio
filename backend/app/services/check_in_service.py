"""Check-in use cases: preview a period's financial result without writing, then post it transactionally.

Preview and posting derive the period and build calculation inputs identically and share
`app.domain.check_in_calc.compute_check_in`, so posted amounts always equal the immediately preceding
preview for the same stored state. The service owns the transaction boundary; repositories own queries
and flushes. Posting is all-or-none: the check-in and every resulting event commit together or not at all.
"""

import uuid
from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal

from sqlalchemy.orm import Session

from app.common.exceptions import NotFoundError, ValidationError
from app.domain.asset import Asset, Bucket
from app.domain.check_in import AllocationEvent, CheckIn, ExpenseEvent
from app.domain.check_in_calc import (
    CheckInComputation,
    ExpenseDraftInput,
    TimeBasedCostInput,
    UsageBasedCostInput,
    compute_check_in,
)
from app.repository import check_in_repository, cost_repository, expense_repository


@dataclass(frozen=True)
class ExpenseDraft:
    """One expense submitted with a check-in, mapped by the router from the request body."""

    kind: str
    amount: Decimal
    event_date: date | None
    usage_counter_at_event: int | None
    comment: str | None
    source_type: str | None
    source_id: uuid.UUID | None


@dataclass(frozen=True)
class CheckInPreview:
    """A previewed check-in: the derived period plus its computed financial result."""

    asset_id: uuid.UUID
    period_start: date
    period_end: date
    usage_start: int
    usage_end: int
    active_tire_type: str | None
    computation: CheckInComputation


@dataclass(frozen=True)
class _PeriodContext:
    """The server-derived start of the period being reviewed."""

    period_start: date
    usage_start: int
    previous_active_tire_type: str | None


class CheckInService:
    """Orchestrates check-in preview and posting over a request-scoped session; owns the transaction."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def preview_check_in(
        self,
        user_id: uuid.UUID,
        asset_id: uuid.UUID,
        period_end: date,
        usage_end: int,
        active_tire_type: str | None,
        expenses: list[ExpenseDraft],
    ) -> CheckInPreview:
        """Compute a period's allocation, expense, and balance figures for an owned asset. Writes nothing."""
        asset = self._require_owned_asset(user_id, asset_id)
        bucket = self._require_bucket(asset_id)
        context = self._derive_period(asset)
        self._validate_period(context, period_end, usage_end)
        resolved_tire_type = active_tire_type if active_tire_type is not None else context.previous_active_tire_type
        computation = self._compute(asset_id, bucket, context, period_end, usage_end, expenses)
        return CheckInPreview(
            asset_id=asset_id,
            period_start=context.period_start,
            period_end=period_end,
            usage_start=context.usage_start,
            usage_end=usage_end,
            active_tire_type=resolved_tire_type,
            computation=computation,
        )

    def post_check_in(
        self,
        user_id: uuid.UUID,
        asset_id: uuid.UUID,
        period_end: date,
        usage_end: int,
        active_tire_type: str | None,
        expenses: list[ExpenseDraft],
        notes: str | None,
    ) -> tuple[CheckIn, list[AllocationEvent], list[ExpenseEvent]]:
        """Recompute the period like preview, then persist the check-in and all resulting events in one commit."""
        asset = self._require_owned_asset(user_id, asset_id)
        bucket = self._require_bucket(asset_id)
        context = self._derive_period(asset)
        self._validate_period(context, period_end, usage_end)
        self._require_expense_sources_exist(asset_id, expenses)
        resolved_tire_type = active_tire_type if active_tire_type is not None else context.previous_active_tire_type
        computation = self._compute(asset_id, bucket, context, period_end, usage_end, expenses)
        return self._persist(bucket, context, period_end, usage_end, resolved_tire_type, notes, expenses, computation)

    def _require_owned_asset(self, user_id: uuid.UUID, asset_id: uuid.UUID) -> Asset:
        """Return the owned asset or raise `NotFoundError` so unowned assets never leak."""
        asset = check_in_repository.get_owned_asset(self._session, user_id, asset_id)
        if asset is None:
            raise NotFoundError("Asset not found.")
        return asset

    def _require_bucket(self, asset_id: uuid.UUID) -> Bucket:
        """Return the asset's savings bucket or raise `NotFoundError`."""
        bucket = expense_repository.get_bucket_for_asset(self._session, asset_id)
        if bucket is None:
            raise NotFoundError("Bucket not found for asset.")
        return bucket

    def _derive_period(self, asset: Asset) -> _PeriodContext:
        """Derive the period start, usage start, and default tire type from the last posted check-in.

        Falls back to the first-check-in rule (asset creation date and starting odometer) when no
        check-in has been posted yet; there is nothing to default the tire type from in that case.
        """
        previous = check_in_repository.get_latest_posted_check_in(self._session, asset.id)
        if previous is not None:
            return _PeriodContext(
                period_start=previous.period_end,
                usage_start=previous.usage_end or 0,
                previous_active_tire_type=previous.active_tire_type,
            )
        profile = check_in_repository.get_vehicle_profile(self._session, asset.id)
        starting_odometer = profile.starting_odometer if profile is not None else 0
        return _PeriodContext(
            period_start=asset.created_at.date(), usage_start=starting_odometer, previous_active_tire_type=None
        )

    def _validate_period(self, context: _PeriodContext, period_end: date, usage_end: int) -> None:
        """Reject a period that ends before it starts, in the future, or whose usage counter moves backward."""
        if period_end <= context.period_start:
            raise ValidationError("period_end must be later than the derived period start.")
        if period_end > date.today():
            raise ValidationError("period_end cannot be in the future.")
        if usage_end < context.usage_start:
            raise ValidationError("usage_end must be greater than or equal to the derived usage start.")

    def _compute(
        self,
        asset_id: uuid.UUID,
        bucket: Bucket,
        context: _PeriodContext,
        period_end: date,
        usage_end: int,
        expenses: list[ExpenseDraft],
    ) -> CheckInComputation:
        """Map stored rows into calculation inputs and run the shared, deterministic computation."""
        posted_expenses = expense_repository.list_expenses_for_bucket(self._session, bucket.id)
        return compute_check_in(
            period_start=context.period_start,
            period_end=period_end,
            usage_start=context.usage_start,
            usage_end=usage_end,
            time_based_costs=self._time_based_inputs(asset_id, posted_expenses),
            usage_based_costs=self._usage_based_inputs(asset_id),
            expense_drafts=self._expense_inputs(expenses),
            prior_allocation_amounts=check_in_repository.list_posted_allocation_amounts(self._session, bucket.id),
            prior_expense_amounts=[row.amount for row in posted_expenses],
        )

    def _time_based_inputs(
        self, asset_id: uuid.UUID, posted_expenses: list[ExpenseEvent]
    ) -> list[TimeBasedCostInput]:
        """Build a calc input per active time-based cost, attaching its posted modeled expenses for rollover."""
        inputs: list[TimeBasedCostInput] = []
        for cost in cost_repository.list_time_based_costs(self._session, asset_id):
            if not cost.is_active:
                continue
            linked = [
                (row.event_date, row.amount)
                for row in posted_expenses
                if row.source_type == "time_based_cost" and row.source_id == cost.id
            ]
            inputs.append(
                TimeBasedCostInput(
                    source_id=cost.id,
                    label=cost.label,
                    baseline_amount=cost.amount,
                    interval_value=cost.interval_value,
                    interval_unit=cost.interval_unit,
                    linked_expenses=linked,
                )
            )
        return inputs

    def _usage_based_inputs(self, asset_id: uuid.UUID) -> list[UsageBasedCostInput]:
        """Build a calc input per active usage-based cost component, in deterministic repo order."""
        return [
            UsageBasedCostInput(source_id=cost.id, label=cost.label, amount_per_unit=cost.amount_per_unit)
            for cost in cost_repository.list_active_usage_based_costs(self._session, asset_id)
        ]

    def _expense_inputs(self, expenses: list[ExpenseDraft]) -> list[ExpenseDraftInput]:
        """Resolve each draft's `event_date` to today when omitted and map it to a calc input."""
        return [
            ExpenseDraftInput(
                kind=draft.kind,
                amount=draft.amount,
                event_date=draft.event_date or date.today(),
                comment=draft.comment,
                source_type=draft.source_type,
                source_id=draft.source_id,
                usage_counter_at_event=draft.usage_counter_at_event,
            )
            for draft in expenses
        ]

    def _require_expense_sources_exist(self, asset_id: uuid.UUID, expenses: list[ExpenseDraft]) -> None:
        """Reject a modeled draft whose source row does not exist under the asset, matching expense logging."""
        for draft in expenses:
            if draft.kind == "modeled" and not expense_repository.source_row_exists(
                self._session, asset_id, draft.source_type, draft.source_id
            ):
                raise ValidationError("Source row not found for this asset.")

    def _persist(
        self,
        bucket: Bucket,
        context: _PeriodContext,
        period_end: date,
        usage_end: int,
        active_tire_type: str | None,
        notes: str | None,
        expenses: list[ExpenseDraft],
        computation: CheckInComputation,
    ) -> tuple[CheckIn, list[AllocationEvent], list[ExpenseEvent]]:
        """Write the posted check-in, its allocation/expense events, and any maintenance resets in one commit."""
        try:
            check_in = self._build_check_in(bucket, context, period_end, usage_end, active_tire_type, notes)
            check_in_repository.add_and_flush(self._session, check_in)
            allocation_events = self._build_allocation_events(bucket, check_in, period_end, computation)
            expense_events = self._build_expense_events(bucket, check_in, computation)
            self._reset_maintenance_baselines(bucket.asset_id, expenses, period_end, usage_end)
            self._session.flush()
            self._session.commit()
        except Exception:
            self._session.rollback()
            raise
        return check_in, allocation_events, expense_events

    def _build_check_in(
        self,
        bucket: Bucket,
        context: _PeriodContext,
        period_end: date,
        usage_end: int,
        active_tire_type: str | None,
        notes: str | None,
    ) -> CheckIn:
        """Assemble the posted check-in row for the period."""
        return CheckIn(
            asset_id=bucket.asset_id,
            period_start=context.period_start,
            period_end=period_end,
            checked_in_at=datetime.now(timezone.utc),
            usage_start=context.usage_start,
            usage_end=usage_end,
            usage_amount=usage_end - context.usage_start,
            active_tire_type=active_tire_type,
            notes=notes,
            status="posted",
        )

    def _build_allocation_events(
        self, bucket: Bucket, check_in: CheckIn, period_end: date, computation: CheckInComputation
    ) -> list[AllocationEvent]:
        """Create one allocation event per computed line, keeping the source label for later explanation."""
        events = [
            AllocationEvent(
                bucket_id=bucket.id,
                check_in_id=check_in.id,
                event_date=period_end,
                source_type=line.source_type,
                source_id=line.source_id,
                amount=line.amount,
                metadata_json={"label": line.label},
            )
            for line in computation.allocation_lines
        ]
        for event in events:
            self._session.add(event)
        return events

    def _build_expense_events(
        self, bucket: Bucket, check_in: CheckIn, computation: CheckInComputation
    ) -> list[ExpenseEvent]:
        """Create one expense event per computed expense line."""
        events = [
            ExpenseEvent(
                bucket_id=bucket.id,
                check_in_id=check_in.id,
                event_date=line.event_date,
                usage_counter_at_event=line.usage_counter_at_event,
                kind=line.kind,
                amount=line.amount,
                comment=line.comment,
                source_type=line.source_type,
                source_id=line.source_id,
                metadata_json=None,
            )
            for line in computation.expense_lines
        ]
        for event in events:
            self._session.add(event)
        return events

    def _reset_maintenance_baselines(
        self, asset_id: uuid.UUID, expenses: list[ExpenseDraft], period_end: date, usage_end: int
    ) -> None:
        """Reset each maintenance-linked expense's item to the check-in's period_end/usage_end.

        Any maintenance-linked expense resets its item's baseline (MVP: no separate "was this a
        service?" flag). Tire items reset by date only — their km-since-service re-sums from that
        date across matching-tire-type check-ins, so mutating the odometer field would double-count.
        """
        seen: set[uuid.UUID] = set()
        for draft in expenses:
            if draft.source_type != "maintenance_item" or draft.source_id is None or draft.source_id in seen:
                continue
            seen.add(draft.source_id)
            item = cost_repository.get_maintenance_item(self._session, asset_id, draft.source_id)
            if item is None:
                raise NotFoundError("Maintenance item not found.")
            item.last_serviced_at_date = period_end
            if item.tire_type is None:
                item.last_serviced_at_odometer = usage_end
