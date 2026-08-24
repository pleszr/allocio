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
from app.domain.asset import Asset
from app.repository import check_in_repository, expense_repository
from app.services.cost_service import CostService, MaintenanceItemView
from app.services.workspace_service import WorkspaceService

_ACTIVITY_LIMIT = 20
_UPCOMING_HORIZON_DAYS = 90
_MONTH_DAYS = 30
# Below this per-currency gap, manual_extra_recommended is suppressed to zero rather than nagging
# the user over noise. HUF/EUR/USD are the app's three supported currencies (see
# app/api/schemas/requests.py's CurrencyCode); the fallback covers any other value defensively.
_RECOMMENDATION_VISIBILITY_THRESHOLD: dict[str, Decimal] = {
    "HUF": Decimal("5000"),
    "USD": Decimal("15"),
    "EUR": Decimal("13"),
}
_DEFAULT_RECOMMENDATION_VISIBILITY_THRESHOLD = Decimal("15")


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
    avg_monthly_paid_out_of_pocket: Decimal
    average_actual_monthly_cost: Decimal
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
    manual_extra_recommended_months: int
    average_monthly_usage: Decimal
    average_allocation: Decimal


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
        manual_extra_recommended_months = max(
            1, min(12, calculator.whole_months(asset.created_at.date(), today))
        )
        total_expense_365d = self._trailing_expense_total(asset_id, today)
        average_actual_monthly_cost = calculator.quantize_currency(
            total_expense_365d / Decimal(manual_extra_recommended_months), summary.currency
        )
        average_allocation = self._average_allocation(asset)
        return AssetDetail(
            asset_id=asset.id,
            type=summary.type,
            name=summary.name,
            status=summary.status,
            currency=summary.currency,
            balance=summary.balance,
            recommended_monthly_allocation=summary.recommended_monthly_allocation,
            daily_accrual=calculator.quantize_currency(
                summary.recommended_monthly_allocation * 12 / 365, summary.currency
            ),
            vehicle_age_years=(
                today.year - vehicle_profile.manufacture_year
                if vehicle_profile is not None and vehicle_profile.manufacture_year is not None
                else None
            ),
            tracked_in_app_months=calculator.whole_months(asset.created_at.date(), today),
            average_monthly_cost=self._average_monthly_cost(asset_id, today),
            avg_monthly_paid_out_of_pocket=self._avg_monthly_paid_out_of_pocket(asset_id, today),
            average_actual_monthly_cost=average_actual_monthly_cost,
            next_maintenance=self._next_maintenance(maintenance_items),
            tracks_usage=vehicle_profile is not None,
            current_usage=self._costs.current_asset_usage(user_id, asset_id),
            usage_since_last_check_in=latest.usage_amount if latest is not None else None,
            last_check_in_date=latest.period_end if latest is not None else None,
            maintenance_items=maintenance_items,
            recent_activity=self._recent_activity(asset_id),
            upcoming_expenses=self._upcoming_expenses(user_id, asset_id, maintenance_items),
            manual_extra_monthly=asset.manual_extra_monthly,
            manual_extra_recommended=self._manual_extra_recommendation(
                average_actual_monthly_cost, average_allocation, summary.currency
            ),
            manual_extra_recommended_months=manual_extra_recommended_months,
            average_monthly_usage=self._workspace.monthly_usage_rate(asset_id, today),
            average_allocation=average_allocation,
        )

    def _average_monthly_cost(self, asset_id: uuid.UUID, as_of: date) -> Decimal:
        """Average trailing annual allocations plus out-of-pocket expense funding over 12 months.

        Skips any expense flagged `excluded_from_average` (a known one-time cost, e.g. a post-purchase
        catch-up service) so it doesn't inflate this forward-looking guidance figure.
        """
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
                if not expense.excluded_from_average and window_start <= expense.event_date <= as_of
            ),
            Decimal(0),
        )
        return calculator.quantize_currency((allocated + out_of_pocket) / Decimal(12), bucket.currency)

    def _avg_monthly_paid_out_of_pocket(self, asset_id: uuid.UUID, as_of: date) -> Decimal:
        """Average trailing 12-month out-of-pocket expense funding, excluding bucket-covered allocations.

        Skips any expense flagged `excluded_from_average`, same as `_average_monthly_cost`.
        """
        bucket = expense_repository.get_bucket_for_asset(self._session, asset_id)
        if bucket is None:
            return Decimal("0.00")
        window_start = _subtract_months_clamped(as_of, 12)
        expenses = expense_repository.list_expenses_for_bucket(self._session, bucket.id)
        out_of_pocket = sum(
            (
                expense.paid_out_of_pocket
                for expense in expenses
                if not expense.excluded_from_average and window_start <= expense.event_date <= as_of
            ),
            Decimal(0),
        )
        return calculator.quantize_currency(out_of_pocket / Decimal(12), bucket.currency)

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

    def _average_allocation(self, asset: Asset) -> Decimal:
        """Today's base required funding: active time-based + usage-based monthly accrual.

        Forward-looking, not historical: unlike the retired adaptive 3/6/12-month average of posted
        check-in totals, this doesn't depend on check-in history at all and updates immediately when a
        cost rule or usage rate changes. Equal to `WorkspaceService.recommended_monthly_allocation`
        minus `manual_extra_monthly`, computed directly rather than by subtraction so it never
        round-trips through the already-quantized combined total.
        """
        bucket = expense_repository.get_bucket_for_asset(self._session, asset.id)
        if bucket is None:
            return Decimal("0.00")
        return calculator.quantize_currency(
            self._workspace.base_required_allocation(asset, bucket), bucket.currency
        )

    def _trailing_expense_total(self, asset_id: uuid.UUID, today: date) -> Decimal:
        """Sum posted expense `amount` over the trailing 365 days, skipping `excluded_from_average` rows.

        Feeds `average_actual_monthly_cost`, the real-spend figure compared against `average_allocation`
        to derive `manual_extra_recommended`.
        """
        bucket = expense_repository.get_bucket_for_asset(self._session, asset_id)
        if bucket is None:
            return Decimal(0)
        window_start = today - timedelta(days=365)
        expenses = expense_repository.list_expenses_for_bucket(self._session, bucket.id)
        return sum(
            (
                expense.amount
                for expense in expenses
                if not expense.excluded_from_average and expense.event_date >= window_start
            ),
            Decimal(0),
        )

    def _manual_extra_recommendation(
        self, average_actual_monthly_cost: Decimal, average_allocation: Decimal, currency: str
    ) -> Decimal:
        """Derive a recommended monthly manual-extra buffer from real spend minus base required funding.

        Compares real spend (`average_actual_monthly_cost`) against today's base required allocation
        (`average_allocation`, itself time-based + usage-based, excluding manual extra) rather than
        against trailing posted allocations, so a manual extra the user already applied is never
        double-counted into the gap. Floored at zero (never suggests a negative top-up) and suppressed
        entirely below a small per-currency noise threshold (see `_RECOMMENDATION_VISIBILITY_THRESHOLD`)
        so a trivial gap doesn't nag the user. Derived guidance only, per docs/domain-model.md — never
        overwrites the stored `manual_extra_monthly` value on its own.
        """
        shortfall = max(Decimal(0), average_actual_monthly_cost - average_allocation)
        threshold = _RECOMMENDATION_VISIBILITY_THRESHOLD.get(currency, _DEFAULT_RECOMMENDATION_VISIBILITY_THRESHOLD)
        return calculator.quantize_currency(shortfall, currency) if shortfall >= threshold else Decimal("0.00")

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
        source_labels = expense_repository.resolve_source_labels(self._session, expenses)
        return [
            ActivityItem(
                date=expense.event_date,
                kind="expense",
                label=expense.resolved_label(source_labels.get((expense.source_type, expense.source_id))),
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

    def _upcoming_expenses(
        self, user_id: uuid.UUID, asset_id: uuid.UUID, maintenance_items: list[MaintenanceItemView]
    ) -> list[UpcomingExpense]:
        """Forecast active time-based costs and maintenance within the 90-day window."""
        today = date.today()
        items = self._upcoming_time_based(user_id, asset_id, today)
        items += self._upcoming_maintenance(asset_id, maintenance_items)
        return sorted(
            items,
            key=lambda item: (item.days_until, item.name.casefold(), item.category),
        )

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
        """Return each active row whose earliest valid trigger is inside the forecast window."""
        average_monthly_usage = self._forecast_average_monthly_usage(asset_id)
        candidates: list[UpcomingExpense] = []
        for view in maintenance_items:
            if not view.row.is_active:
                continue
            candidate = self._upcoming_maintenance_candidate(view, average_monthly_usage)
            if candidate is not None:
                candidates.append(candidate)
        return candidates

    def _upcoming_maintenance_candidate(
        self, view: MaintenanceItemView, average_monthly_usage: Decimal | None
    ) -> UpcomingExpense | None:
        """Build one maintenance forecast from the earliest valid kilometer or time trigger."""
        cost = view.row.estimated_cost or Decimal(0)
        if view.status == "overdue":
            return UpcomingExpense(
                name=view.row.label,
                category="maintenance",
                days_until=0,
                amount=cost,
                overdue=True,
            )

        trigger_days = self._maintenance_trigger_days(view, average_monthly_usage)
        if not trigger_days:
            return None
        days_until = min(trigger_days)
        if days_until > _UPCOMING_HORIZON_DAYS:
            return None
        return UpcomingExpense(
            name=view.row.label,
            category="maintenance",
            days_until=days_until,
            amount=cost,
            overdue=False,
        )

    def _maintenance_trigger_days(
        self, view: MaintenanceItemView, average_monthly_usage: Decimal | None
    ) -> list[int]:
        """Return independently valid kilometer and time trigger estimates."""
        trigger_days: list[int] = []
        if (
            view.remaining_km is not None
            and average_monthly_usage is not None
            and view.remaining_km <= average_monthly_usage * 3
        ):
            daily_usage = average_monthly_usage / _MONTH_DAYS
            trigger_days.append(round(Decimal(view.remaining_km) / daily_usage))
        if view.remaining_months is not None:
            trigger_days.append(view.remaining_months * _MONTH_DAYS)
        return trigger_days

    def _forecast_average_monthly_usage(self, asset_id: uuid.UUID) -> Decimal | None:
        """Return a 30-day usage rate from at most 12 calendar months of posted history."""
        check_ins = check_in_repository.list_posted_check_ins(self._session, asset_id)
        if not check_ins:
            return None

        window_end = check_ins[-1].period_end
        window_start = _subtract_months_clamped(window_end, 12)
        usage_in_window = Decimal(0)
        covered_days = 0
        for check_in in check_ins:
            period_days = (check_in.period_end - check_in.period_start).days
            overlap_start = max(check_in.period_start, window_start)
            overlap_end = min(check_in.period_end, window_end)
            overlap_days = (overlap_end - overlap_start).days
            if period_days <= 0 or overlap_days <= 0:
                continue
            covered_days += overlap_days
            usage_amount = check_in.usage_amount
            if usage_amount is None:
                return None
            usage_in_window += (
                Decimal(usage_amount) * Decimal(overlap_days) / Decimal(period_days)
            )

        if usage_in_window <= 0 or covered_days <= 0:
            return None
        return usage_in_window / Decimal(covered_days) * _MONTH_DAYS


def _subtract_months_clamped(value: date, months: int) -> date:
    """Move a date back by whole calendar months, clamping its day to the target month's final day."""
    target_month_index = value.year * 12 + value.month - 1 - months
    target_year, zero_based_month = divmod(target_month_index, 12)
    target_month = zero_based_month + 1
    return date(target_year, target_month, min(value.day, monthrange(target_year, target_month)[1]))
