"""Asset detail read use case: compose one asset's dashboard payload from reused figures and events.

Read-only. Reuses `WorkspaceService` for balance/allocation, `CostService` for current usage
and maintenance status, and the check-in/expense repositories for the recent-activity feed. It never
commits or flushes; an unknown or unowned asset raises `NotFoundError`.
"""

import uuid
from calendar import monthrange
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from typing import Literal

from sqlalchemy.orm import Session

from app.common.exceptions import NotFoundError
from app.domain import calculator
from app.repository import check_in_repository, expense_repository
from app.services.cost_service import CostService, MaintenanceItemView
from app.services.workspace_service import WorkspaceService

_ACTIVITY_LIMIT = 20
_UPCOMING_HORIZON_DAYS = 90
_MONTH_DAYS = 30


@dataclass(frozen=True)
class UpcomingExpense:
    """One forecasted cost within the 90-day dashboard window, soonest first."""

    name: str
    category: Literal["time_based", "maintenance"]
    days_until: int
    amount: Decimal
    overdue: bool


@dataclass(frozen=True)
class ActivityItem:
    """One recent bucket movement; `amount` is signed and only covers the bucket-funded portion."""

    date: date
    kind: str
    label: str
    amount: Decimal
    paid_out_of_pocket: Decimal


@dataclass(frozen=True)
class AverageAllocation:
    """Adaptive trailing average of posted check-in allocation totals for the dashboard."""

    months: Literal[3, 6, 12]
    amount: Decimal | None


@dataclass(frozen=True)
class NextMaintenance:
    """Nearest active kilometer-based maintenance item with a comparable usage baseline."""

    label: str
    remaining_km: int


@dataclass(frozen=True)
class AssetDetail:
    """The composed detail payload for one asset's dashboard screen."""

    asset_id: uuid.UUID
    type: str
    name: str
    status: str
    currency: str
    balance: Decimal
    recommended_monthly_allocation: Decimal
    daily_accrual: Decimal
    vehicle_age_years: int | None
    tracked_in_app_months: int
    average_monthly_cost: Decimal
    next_maintenance: NextMaintenance | None
    tracks_usage: bool
    current_usage: int | None
    usage_since_last_check_in: int | None
    last_check_in_date: date | None
    maintenance_items: list[MaintenanceItemView]
    recent_activity: list[ActivityItem]
    upcoming_expenses: list[UpcomingExpense]
    manual_extra_monthly: Decimal
    manual_extra_recommended: Decimal
    average_monthly_usage: Decimal
    average_allocation: AverageAllocation


class AssetDetailService:
    """Assembles the read-only asset detail payload over a request-scoped session; never mutates."""

    def __init__(self, session: Session) -> None:
        self._session = session
        self._workspace = WorkspaceService(session)
        self._costs = CostService(session)

    def get_detail(self, user_id: uuid.UUID, asset_id: uuid.UUID, as_of: date | None = None) -> AssetDetail:
        """Compose one owned asset's detail payload; raises `NotFoundError` when unknown or unowned."""
        today = as_of or date.today()
        summary = self._workspace.summarize_asset(user_id, asset_id)
        asset = check_in_repository.get_owned_asset(self._session, user_id, asset_id)
        if asset is None:
            raise NotFoundError("Asset not found.")
        latest = check_in_repository.get_latest_posted_check_in(self._session, asset_id)
        vehicle_profile = check_in_repository.get_vehicle_profile(self._session, asset_id)
        maintenance_items = self._costs.list_maintenance_item_views(user_id, asset_id)
        return AssetDetail(
            asset_id=asset.id,
            type=summary.type,
            name=summary.name,
            status=summary.status,
            currency=summary.currency,
            balance=summary.balance,
            recommended_monthly_allocation=summary.recommended_monthly_allocation,
            daily_accrual=calculator.quantize_currency(summary.recommended_monthly_allocation * 12 / 365),
            vehicle_age_years=(
                today.year - vehicle_profile.manufacture_year
                if vehicle_profile is not None and vehicle_profile.manufacture_year is not None
                else None
            ),
            tracked_in_app_months=calculator.whole_months(asset.created_at.date(), today),
            average_monthly_cost=self._average_monthly_cost(asset_id, today),
            next_maintenance=self._next_maintenance(maintenance_items),
            tracks_usage=vehicle_profile is not None,
            current_usage=self._costs.current_asset_usage(user_id, asset_id),
            usage_since_last_check_in=latest.usage_amount if latest is not None else None,
            last_check_in_date=latest.period_end if latest is not None else None,
            maintenance_items=maintenance_items,
            recent_activity=self._recent_activity(asset_id),
            upcoming_expenses=self._upcoming_expenses(user_id, asset_id, maintenance_items),
            manual_extra_monthly=asset.manual_extra_monthly,
            manual_extra_recommended=self._manual_extra_recommendation(asset_id),
            average_monthly_usage=self._workspace.monthly_usage_rate(asset_id),
            average_allocation=self._average_allocation(asset_id, today),
        )

    def _average_monthly_cost(self, asset_id: uuid.UUID, as_of: date) -> Decimal:
        """Average trailing annual allocations plus out-of-pocket expense funding over 12 months."""
        bucket = expense_repository.get_bucket_for_asset(self._session, asset_id)
        if bucket is None:
            return Decimal("0.00")
        window_start = _subtract_months_clamped(as_of, 12)
        allocations = check_in_repository.list_posted_allocation_events(self._session, bucket.id)
        expenses = expense_repository.list_expenses_for_bucket(self._session, bucket.id)
        allocated = sum(
            (amount for event_date, amount in allocations if window_start <= event_date <= as_of),
            Decimal(0),
        )
        out_of_pocket = sum(
            (
                expense.paid_out_of_pocket
                for expense in expenses
                if window_start <= expense.event_date <= as_of
            ),
            Decimal(0),
        )
        return calculator.quantize_currency((allocated + out_of_pocket) / Decimal(12))

    def _next_maintenance(
        self, maintenance_items: list[MaintenanceItemView]
    ) -> NextMaintenance | None:
        """Return the nearest active kilometer-comparable item with deterministic tie-breaking."""
        candidates = [
            view
            for view in maintenance_items
            if view.row.is_active and view.remaining_km is not None
        ]
        if not candidates:
            return None
        nearest = min(
            candidates,
            key=lambda view: (
                view.remaining_km,
                view.row.label.casefold(),
                str(view.row.id),
            ),
        )
        return NextMaintenance(label=nearest.row.label, remaining_km=nearest.remaining_km)

    def _average_allocation(self, asset_id: uuid.UUID, as_of: date) -> AverageAllocation:
        """Average posted check-in allocation totals over the longest eligible 3/6/12-month window."""
        check_ins = check_in_repository.list_posted_check_ins(self._session, asset_id)
        if not check_ins:
            return AverageAllocation(months=3, amount=None)

        cutoffs = {months: _subtract_months_clamped(as_of, months) for months in (3, 6, 12)}
        oldest_period_end = check_ins[0].period_end
        months: Literal[3, 6, 12] = (
            12 if oldest_period_end <= cutoffs[12] else 6 if oldest_period_end <= cutoffs[6] else 3
        )
        selected = [
            check_in for check_in in check_ins if cutoffs[months] <= check_in.period_end <= as_of
        ]
        if not selected:
            return AverageAllocation(months=months, amount=None)

        bucket = expense_repository.get_bucket_for_asset(self._session, asset_id)
        if bucket is None:
            return AverageAllocation(months=months, amount=None)
        totals = check_in_repository.sum_allocation_amounts_by_check_in(self._session, bucket.id)
        total = sum((totals.get(check_in.id, Decimal(0)) for check_in in selected), Decimal(0))
        return AverageAllocation(
            months=months,
            amount=calculator.quantize_currency(total / Decimal(len(selected))),
        )

    def _manual_extra_recommendation(self, asset_id: uuid.UUID) -> Decimal:
        """Derive a recommended manual-extra buffer from the last 12 months' expense/allocation gap.

        Floored at zero; derived guidance only, per docs/domain-model.md — never overwrites the
        stored `manual_extra_monthly` value on its own.
        """
        bucket = expense_repository.get_bucket_for_asset(self._session, asset_id)
        if bucket is None:
            return Decimal(0)
        window_start = date.today() - timedelta(days=365)
        allocations = check_in_repository.list_posted_allocation_events(self._session, bucket.id)
        expenses = expense_repository.list_expenses_for_bucket(self._session, bucket.id)
        total_allocated = sum((amount for event_date, amount in allocations if event_date >= window_start), Decimal(0))
        total_expense = sum((expense.amount for expense in expenses if expense.event_date >= window_start), Decimal(0))
        return max(Decimal(0), total_expense - total_allocated)

    def _recent_activity(self, asset_id: uuid.UUID) -> list[ActivityItem]:
        """Merge posted allocations (inflow) and expenses (outflow) into a newest-first, capped feed."""
        bucket = expense_repository.get_bucket_for_asset(self._session, asset_id)
        if bucket is None:
            return []
        items = self._allocation_items(bucket.id) + self._expense_items(bucket.id)
        items.sort(key=lambda item: item.date, reverse=True)
        return items[:_ACTIVITY_LIMIT]

    def _allocation_items(self, bucket_id: uuid.UUID) -> list[ActivityItem]:
        """Build positive-amount activity items from posted allocation events."""
        events = check_in_repository.list_allocation_events_for_bucket(self._session, bucket_id)
        return [
            ActivityItem(
                date=event.event_date,
                kind="allocation",
                label=self._allocation_label(event),
                amount=event.amount,
                paid_out_of_pocket=Decimal(0),
            )
            for event in events
        ]

    def _expense_items(self, bucket_id: uuid.UUID) -> list[ActivityItem]:
        """Build negative-amount activity items from posted expense events."""
        expenses = expense_repository.list_expenses_for_bucket(self._session, bucket_id)
        return [
            ActivityItem(
                date=expense.event_date,
                kind="expense",
                label=self._expense_label(expense),
                amount=-expense.bucket_amount,
                paid_out_of_pocket=expense.paid_out_of_pocket,
            )
            for expense in expenses
        ]

    def _allocation_label(self, event: object) -> str:
        """Prefer the allocation's stored metadata label, else fall back to its source table."""
        metadata = getattr(event, "metadata_json", None)
        if isinstance(metadata, dict):
            label = metadata.get("label")
            if isinstance(label, str) and label:
                return label
        source_type = getattr(event, "source_type", None)
        return "Allocation" if not source_type else str(source_type).replace("_", " ").capitalize()

    def _expense_label(self, expense: object) -> str:
        """Prefer the expense comment, else fall back to a source-derived label."""
        comment = getattr(expense, "comment", None)
        if isinstance(comment, str) and comment:
            return comment
        source_type = getattr(expense, "source_type", None)
        return "Expense" if not source_type else str(source_type).replace("_", " ").capitalize()

    def _upcoming_expenses(
        self, user_id: uuid.UUID, asset_id: uuid.UUID, maintenance_items: list[MaintenanceItemView]
    ) -> list[UpcomingExpense]:
        """Forecast active time-based costs due soon plus overdue/soon maintenance, within the 90-day window."""
        today = date.today()
        items = self._upcoming_time_based(user_id, asset_id, today)
        items += self._upcoming_maintenance(asset_id, maintenance_items)
        return sorted(items, key=lambda item: item.days_until)

    def _upcoming_time_based(
        self, user_id: uuid.UUID, asset_id: uuid.UUID, today: date
    ) -> list[UpcomingExpense]:
        """Active time-based costs whose next-due date falls within the forecast window."""
        items: list[UpcomingExpense] = []
        for cost in self._costs.list_time_based_costs(user_id, asset_id):
            if not cost.is_active:
                continue
            next_due = self._costs.next_due_for(cost)
            if next_due is None:
                continue
            days = (next_due - today).days
            if 0 <= days <= _UPCOMING_HORIZON_DAYS:
                items.append(
                    UpcomingExpense(name=cost.label, category="time_based", days_until=days, amount=cost.amount, overdue=False)
                )
        return items

    def _upcoming_maintenance(
        self, asset_id: uuid.UUID, maintenance_items: list[MaintenanceItemView]
    ) -> list[UpcomingExpense]:
        """Active maintenance items that are overdue (now) or due/soon (projected) within the forecast window."""
        items: list[UpcomingExpense] = []
        daily_rate: Decimal | None = None
        for view in maintenance_items:
            if not view.row.is_active:
                continue
            cost = view.row.estimated_cost or Decimal(0)
            if view.status == "overdue":
                items.append(UpcomingExpense(name=view.row.label, category="maintenance", days_until=0, amount=cost, overdue=True))
            elif view.status in ("due", "soon"):
                if daily_rate is None:
                    daily_rate = self._daily_usage_rate(asset_id)
                days = self._estimated_days_until(view, daily_rate)
                if days is not None and days <= _UPCOMING_HORIZON_DAYS:
                    items.append(
                        UpcomingExpense(name=view.row.label, category="maintenance", days_until=days, amount=cost, overdue=False)
                    )
        return items

    def _daily_usage_rate(self, asset_id: uuid.UUID) -> Decimal:
        """Average usage per day across all posted check-ins, or zero without enough data to estimate.

        Day-granular counterpart of `workspace_service._usage_based_monthly`'s whole-months-based rate —
        this forecast window is measured in days, not months. Reuses the same repository totals query.
        """
        total_usage, first_start, last_end = check_in_repository.get_posted_usage_totals(self._session, asset_id)
        if first_start is None or last_end is None or total_usage <= 0:
            return Decimal(0)
        span_days = (last_end - first_start).days
        if span_days <= 0:
            return Decimal(0)
        return Decimal(total_usage) / Decimal(span_days)

    def _estimated_days_until(self, view: MaintenanceItemView, daily_rate: Decimal) -> int | None:
        """Project a days-until-due estimate for a due/soon item, or `None` when there's no data to project from.

        Prefers a usage-rate-based estimate from `remaining_km`; falls back to a coarse 30-days-per-month
        approximation from `remaining_months`. Never fabricates a default usage rate when none is posted yet.
        """
        if view.remaining_km is not None and daily_rate > 0:
            return round(view.remaining_km / daily_rate)
        if view.remaining_months is not None:
            return view.remaining_months * _MONTH_DAYS
        return None


def _subtract_months_clamped(value: date, months: int) -> date:
    """Move a date back by whole calendar months, clamping its day to the target month's final day."""
    target_month_index = value.year * 12 + value.month - 1 - months
    target_year, zero_based_month = divmod(target_month_index, 12)
    target_month = zero_based_month + 1
    return date(target_year, target_month, min(value.day, monthrange(target_year, target_month)[1]))
