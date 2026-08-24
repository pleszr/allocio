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
from app.domain.calculator import bucket_balance
from app.domain.check_in import AllocationEvent, CheckIn, ExpenseEvent
from app.domain.check_in_calc import (
    AllocationLine,
    CheckInComputation,
    CheckInEditComputation,
    ExpenseDraftInput,
    ExpenseLine,
    TimeBasedCostInput,
    UsageBasedCostInput,
    compute_check_in,
    compute_check_in_edit,
    first_balance_break,
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
    paid_out_of_pocket_override: Decimal | None
    excluded_from_average: bool = False


@dataclass(frozen=True)
class CheckInPreview:
    """A previewed check-in: the derived period plus its computed financial result."""

    asset_id: uuid.UUID
    period_start: date
    period_end: date
    usage_start: int | None
    usage_end: int | None
    active_tire_type: str | None
    computation: CheckInComputation


@dataclass(frozen=True)
class CheckInDetail:
    """A posted check-in's full stored detail: its immutable period plus its posted lines, for the edit screen."""

    check_in_id: uuid.UUID
    period_end: date
    usage_end: int | None
    active_tire_type: str | None
    elapsed_days: int
    usage_amount: int | None
    allocation_lines: list[AllocationLine]
    expense_lines: list[ExpenseLine]
    notes: str | None


@dataclass(frozen=True)
class CheckInEditPreview:
    """A previewed expense-only edit to a posted check-in, plus whether it is safe to apply.

    Carries the check-in's own immutable period fields and posted allocation lines alongside the
    recomputed expense figures, so the API response can mirror `CheckInPreviewResponse` closely enough
    for the frontend to reuse its existing preview rendering for both a new check-in and an edit.
    """

    period_end: date
    usage_end: int | None
    active_tire_type: str | None
    elapsed_days: int
    usage_amount: int | None
    allocation_lines: list[AllocationLine]
    total_allocation: Decimal
    balance_before: Decimal
    computation: CheckInEditComputation
    is_valid: bool
    first_invalid_check_in_id: uuid.UUID | None
    first_invalid_period_end: date | None


@dataclass(frozen=True)
class _PeriodContext:
    """The server-derived start of the period being reviewed."""

    period_start: date
    usage_start: int
    previous_active_tire_type: str | None
    is_first_check_in: bool


class CheckInService:
    """Orchestrates check-in preview and posting over a request-scoped session; owns the transaction."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def preview_check_in(
        self,
        user_id: uuid.UUID,
        asset_id: uuid.UUID,
        period_end: date,
        usage_end: int | None,
        active_tire_type: str | None,
        expenses: list[ExpenseDraft],
    ) -> CheckInPreview:
        """Compute a period's allocation, expense, and balance figures for an owned asset. Writes nothing."""
        asset = self._require_owned_asset(user_id, asset_id)
        bucket = self._require_bucket(asset_id)
        context = self._derive_period(asset)
        resolved_usage_end, tracks_usage = self._resolve_usage_end(asset_id, context, usage_end)
        self._validate_period(context, period_end, resolved_usage_end)
        resolved_tire_type = active_tire_type if active_tire_type is not None else context.previous_active_tire_type
        computation = self._compute(asset, bucket, context, period_end, resolved_usage_end, expenses)
        return CheckInPreview(
            asset_id=asset_id,
            period_start=context.period_start,
            period_end=period_end,
            usage_start=context.usage_start if tracks_usage else None,
            usage_end=resolved_usage_end if tracks_usage else None,
            active_tire_type=resolved_tire_type,
            computation=computation,
        )

    def post_check_in(
        self,
        user_id: uuid.UUID,
        asset_id: uuid.UUID,
        period_end: date,
        usage_end: int | None,
        active_tire_type: str | None,
        expenses: list[ExpenseDraft],
        notes: str | None,
    ) -> tuple[CheckIn, list[AllocationEvent], list[ExpenseEvent]]:
        """Recompute the period like preview, then persist the check-in and all resulting events in one commit."""
        asset = self._require_owned_asset(user_id, asset_id)
        bucket = self._require_bucket(asset_id)
        context = self._derive_period(asset)
        resolved_usage_end, tracks_usage = self._resolve_usage_end(asset_id, context, usage_end)
        self._validate_period(context, period_end, resolved_usage_end)
        self._require_expense_sources_exist(asset_id, expenses)
        resolved_tire_type = active_tire_type if active_tire_type is not None else context.previous_active_tire_type
        computation = self._compute(asset, bucket, context, period_end, resolved_usage_end, expenses)
        return self._persist(
            bucket,
            context,
            period_end,
            resolved_usage_end if tracks_usage else None,
            resolved_tire_type,
            notes,
            expenses,
            computation,
        )

    def get_check_in_detail(self, user_id: uuid.UUID, asset_id: uuid.UUID, check_in_id: uuid.UUID) -> CheckInDetail:
        """Return one posted check-in's immutable period plus its posted allocation/expense lines. Writes nothing."""
        check_in = self._require_owned_check_in(user_id, asset_id, check_in_id)
        return CheckInDetail(
            check_in_id=check_in.id,
            period_end=check_in.period_end,
            usage_end=check_in.usage_end,
            active_tire_type=check_in.active_tire_type,
            elapsed_days=(check_in.period_end - check_in.period_start).days,
            usage_amount=check_in.usage_amount,
            allocation_lines=self._allocation_lines_for(check_in.id),
            expense_lines=self._expense_lines_for(check_in.id),
            notes=check_in.notes,
        )

    def preview_edit_check_in(
        self, user_id: uuid.UUID, asset_id: uuid.UUID, check_in_id: uuid.UUID, expenses: list[ExpenseDraft]
    ) -> CheckInEditPreview:
        """Recompute a posted check-in's expense split for a proposed edit. Writes nothing."""
        check_in = self._require_owned_check_in(user_id, asset_id, check_in_id)
        bucket = self._require_bucket(asset_id)
        computation, balance_before = self._compute_edit(bucket, check_in, expenses)
        first_break = self._first_balance_break(bucket, check_in, balance_before, computation.net_bucket_change)
        allocation_lines = self._allocation_lines_for(check_in.id)
        return CheckInEditPreview(
            period_end=check_in.period_end,
            usage_end=check_in.usage_end,
            active_tire_type=check_in.active_tire_type,
            elapsed_days=(check_in.period_end - check_in.period_start).days,
            usage_amount=check_in.usage_amount,
            allocation_lines=allocation_lines,
            total_allocation=sum((line.amount for line in allocation_lines), Decimal(0)),
            balance_before=balance_before,
            computation=computation,
            is_valid=first_break is None,
            first_invalid_check_in_id=first_break[0] if first_break else None,
            first_invalid_period_end=first_break[1] if first_break else None,
        )

    def edit_check_in(
        self,
        user_id: uuid.UUID,
        asset_id: uuid.UUID,
        check_in_id: uuid.UUID,
        expenses: list[ExpenseDraft],
        notes: str | None,
    ) -> tuple[CheckIn, list[ExpenseEvent]]:
        """Recompute like preview, reject a balance-breaking edit, then replace the expenses in one commit.

        Independently re-validates the forward-simulation guard rather than trusting a prior preview call.
        """
        check_in = self._require_owned_check_in(user_id, asset_id, check_in_id)
        bucket = self._require_bucket(asset_id)
        self._require_expense_sources_exist(asset_id, expenses)
        computation, balance_before = self._compute_edit(bucket, check_in, expenses)
        first_break = self._first_balance_break(bucket, check_in, balance_before, computation.net_bucket_change)
        if first_break is not None:
            _, broken_period_end = first_break
            raise ValidationError(
                "This edit would leave the check-in posted on "
                f"{broken_period_end.isoformat()} with a negative balance."
            )
        return self._persist_edit(bucket, check_in, expenses, notes, computation)

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

    def _require_owned_check_in(self, user_id: uuid.UUID, asset_id: uuid.UUID, check_in_id: uuid.UUID) -> CheckIn:
        """Return the owned, posted check-in or raise `NotFoundError` so an unowned or missing one never leaks."""
        check_in = check_in_repository.get_owned_check_in(self._session, user_id, asset_id, check_in_id)
        if check_in is None:
            raise NotFoundError("Check-in not found.")
        return check_in

    def _allocation_lines_for(self, check_in_id: uuid.UUID) -> list[AllocationLine]:
        """Map a check-in's posted allocation events into value objects for its detail view."""
        events = check_in_repository.list_allocation_events_for_check_in(self._session, check_in_id)
        return [
            AllocationLine(
                source_type=event.source_type,
                source_id=event.source_id,
                label=(event.metadata_json or {}).get("label", ""),
                amount=event.amount,
            )
            for event in events
        ]

    def _expense_lines_for(self, check_in_id: uuid.UUID) -> list[ExpenseLine]:
        """Map a check-in's posted expense events into value objects for its detail view."""
        events = expense_repository.list_expense_events_for_check_in(self._session, check_in_id)
        return [
            ExpenseLine(
                kind=event.kind,
                amount=event.amount,
                bucket_amount=event.bucket_amount,
                paid_out_of_pocket=event.paid_out_of_pocket,
                excluded_from_average=event.excluded_from_average,
                event_date=event.event_date,
                comment=event.comment,
                source_type=event.source_type,
                source_id=event.source_id,
                usage_counter_at_event=event.usage_counter_at_event,
            )
            for event in events
        ]

    def _compute_edit(
        self, bucket: Bucket, check_in: CheckIn, expenses: list[ExpenseDraft]
    ) -> tuple[CheckInEditComputation, Decimal]:
        """Map stored/submitted state into `compute_check_in_edit`'s inputs and run it.

        Also returns the balance immediately before this check-in's period, independently derived
        the same way `compute_check_in_edit` derives it internally, since `first_balance_break` needs
        that starting point and `CheckInEditComputation` does not expose it.
        """
        total_allocation = sum(
            (event.amount for event in check_in_repository.list_allocation_events_for_check_in(self._session, check_in.id)),
            Decimal(0),
        )
        prior_allocation_amounts = check_in_repository.list_posted_allocation_amounts_before(
            self._session, bucket.id, check_in.period_end
        )
        prior_expense_amounts = expense_repository.list_bucket_covered_amounts_before(
            self._session, bucket.id, check_in.period_end
        )
        computation = compute_check_in_edit(
            total_allocation=total_allocation,
            expense_drafts=self._expense_inputs(expenses),
            prior_allocation_amounts=prior_allocation_amounts,
            prior_expense_amounts=prior_expense_amounts,
        )
        balance_before = max(bucket_balance(prior_allocation_amounts, prior_expense_amounts), Decimal(0))
        return computation, balance_before

    def _first_balance_break(
        self, bucket: Bucket, check_in: CheckIn, balance_before: Decimal, net_bucket_change: Decimal
    ) -> tuple[uuid.UUID, date] | None:
        """Run the forward-simulation walk against every later posted check-in's existing, unchanged totals."""
        later_check_ins = check_in_repository.list_posted_check_ins_after(
            self._session, bucket.asset_id, check_in.period_end
        )
        allocation_totals = check_in_repository.sum_allocation_amounts_by_check_in(self._session, bucket.id)
        expense_totals = expense_repository.sum_expense_funding_by_check_in(self._session, bucket.id)
        empty_funding = expense_repository.ExpenseFundingTotals(Decimal(0), Decimal(0), Decimal(0))
        subsequent_nets = [
            (
                later.id,
                later.period_end,
                allocation_totals.get(later.id, Decimal(0)) - expense_totals.get(later.id, empty_funding).bucket_amount,
            )
            for later in later_check_ins
        ]
        return first_balance_break(balance_before, net_bucket_change, subsequent_nets)

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
                is_first_check_in=False,
            )
        profile = check_in_repository.get_vehicle_profile(self._session, asset.id)
        starting_odometer = profile.starting_odometer if profile is not None else 0
        return _PeriodContext(
            period_start=asset.created_at.date(),
            usage_start=starting_odometer,
            previous_active_tire_type=None,
            is_first_check_in=True,
        )

    def _validate_period(self, context: _PeriodContext, period_end: date, usage_end: int) -> None:
        """Reject a period that ends before it starts, in the future, or whose usage counter moves backward.

        The very first check-in may have `period_end == period_start` (a zero-length baseline that
        records the starting odometer/tire type with no accrual) since `period_start` is fixed to the
        asset's creation date and cannot be moved earlier. Every later check-in must move forward.
        """
        period_start = context.period_start
        is_too_early = period_end < period_start if context.is_first_check_in else period_end <= period_start
        if is_too_early:
            raise ValidationError(
                f"period_end must be on or after the derived period start ({period_start.isoformat()})."
                if context.is_first_check_in
                else f"period_end must be later than the derived period start ({period_start.isoformat()})."
            )
        if period_end > date.today():
            raise ValidationError("period_end cannot be in the future.")
        if usage_end < context.usage_start:
            raise ValidationError("usage_end must be greater than or equal to the derived usage start.")

    def _resolve_usage_end(
        self, asset_id: uuid.UUID, context: _PeriodContext, requested: int | None
    ) -> tuple[int, bool]:
        """Require usage for profiled assets and ignore the input dimension for all other assets."""
        tracks_usage = check_in_repository.get_vehicle_profile(self._session, asset_id) is not None
        if tracks_usage:
            if requested is None:
                raise ValidationError("usage_end is required for an asset that tracks usage.")
            return requested, True
        return context.usage_start, False

    def _compute(
        self,
        asset: Asset,
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
            time_based_costs=self._time_based_inputs(asset.id, posted_expenses),
            usage_based_costs=self._usage_based_inputs(asset.id),
            manual_extra_monthly=asset.manual_extra_monthly,
            expense_drafts=self._expense_inputs(expenses),
            prior_allocation_amounts=check_in_repository.list_posted_allocation_amounts(self._session, bucket.id),
            prior_expense_amounts=[row.bucket_amount for row in posted_expenses],
            currency=bucket.currency,
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
                paid_out_of_pocket_override=draft.paid_out_of_pocket_override,
                excluded_from_average=draft.excluded_from_average,
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

    def _persist_edit(
        self,
        bucket: Bucket,
        check_in: CheckIn,
        expenses: list[ExpenseDraft],
        notes: str | None,
        computation: CheckInEditComputation,
    ) -> tuple[CheckIn, list[ExpenseEvent]]:
        """Replace the check-in's expense events and re-derive affected maintenance baselines in one commit.

        `period_end`/`usage_end`/`active_tire_type`/`allocation_event` rows are never touched here — only
        `expense_event` rows (delete then re-insert) and `notes` change, per this feature's locked scope.
        """
        try:
            affected_item_ids = self._affected_maintenance_item_ids(check_in.id, expenses)
            expense_repository.delete_expense_events_for_check_in(self._session, check_in.id)
            expense_events = self._build_expense_events(bucket, check_in, computation)
            if notes is not None:
                check_in.notes = notes
            # Flush the delete + inserts before re-deriving baselines: the session disables autoflush
            # in some callers (e.g. the test fixture), and the re-derivation query below joins against
            # `expense_events`, so it must see this check-in's replacement rows, not its pre-edit ones.
            self._session.flush()
            self._rederive_maintenance_baselines(bucket.asset_id, affected_item_ids)
            self._session.flush()
            self._session.commit()
        except Exception:
            self._session.rollback()
            raise
        return check_in, expense_events

    def _affected_maintenance_item_ids(self, check_in_id: uuid.UUID, expenses: list[ExpenseDraft]) -> set[uuid.UUID]:
        """Union the maintenance items linked by the check-in's pre-edit expenses and its submitted drafts.

        Read before the delete below removes the pre-edit rows, so both sides of the union are known.
        """
        old_expenses = expense_repository.list_expense_events_for_check_in(self._session, check_in_id)
        old_ids = {e.source_id for e in old_expenses if e.source_type == "maintenance_item" and e.source_id is not None}
        new_ids = {d.source_id for d in expenses if d.source_type == "maintenance_item" and d.source_id is not None}
        return old_ids | new_ids

    def _rederive_maintenance_baselines(self, asset_id: uuid.UUID, item_ids: set[uuid.UUID]) -> None:
        """Reset each affected item's baseline to its now-latest linked check-in, or leave it untouched if none remain.

        Documented limitation (`docs/vehicle-rules.md`, "Future-Only Effect Of Edits"): when the edit
        removes the only check-in that ever linked to an item, its current baseline fields are left as
        they were rather than nulled out — there is no prior value recorded to roll back to.
        """
        for item_id in item_ids:
            latest = check_in_repository.get_latest_check_in_linked_to_maintenance_item(
                self._session, asset_id, item_id
            )
            if latest is None:
                continue
            item = cost_repository.get_maintenance_item(self._session, asset_id, item_id)
            if item is None:
                raise NotFoundError("Maintenance item not found.")
            item.last_serviced_at_date = latest.period_end
            if item.tire_type is None and latest.usage_end is not None:
                item.last_serviced_at_odometer = latest.usage_end

    def _build_check_in(
        self,
        bucket: Bucket,
        context: _PeriodContext,
        period_end: date,
        usage_end: int | None,
        active_tire_type: str | None,
        notes: str | None,
    ) -> CheckIn:
        """Assemble the posted check-in row for the period."""
        return CheckIn(
            asset_id=bucket.asset_id,
            period_start=context.period_start,
            period_end=period_end,
            checked_in_at=datetime.now(timezone.utc),
            usage_start=context.usage_start if usage_end is not None else None,
            usage_end=usage_end,
            usage_amount=usage_end - context.usage_start if usage_end is not None else None,
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
        self, bucket: Bucket, check_in: CheckIn, computation: CheckInComputation | CheckInEditComputation
    ) -> list[ExpenseEvent]:
        """Create one expense event per computed expense line; shared by posting a new check-in and editing one."""
        events = [
            ExpenseEvent(
                bucket_id=bucket.id,
                check_in_id=check_in.id,
                event_date=line.event_date,
                usage_counter_at_event=line.usage_counter_at_event,
                kind=line.kind,
                amount=line.amount,
                paid_out_of_pocket=line.paid_out_of_pocket,
                excluded_from_average=line.excluded_from_average,
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
        self, asset_id: uuid.UUID, expenses: list[ExpenseDraft], period_end: date, usage_end: int | None
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
            if item.tire_type is None and usage_end is not None:
                item.last_serviced_at_odometer = usage_end
