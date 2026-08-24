"""Cost-management use cases: list, create, edit, and deactivate asset-owned cost rows.

Every method is ownership-scoped and never touches posted history, so edits only affect future
accruals. The service owns the transaction boundary; the repository owns queries and flushes.
"""

import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import TypeVar

from sqlalchemy.orm import Session

from app.common.exceptions import NotFoundError, ValidationError
from app.domain import calculator
from app.domain.asset import Asset
from app.domain.cost import MaintenanceItem, TimeBasedCost, UsageBasedCost
from app.repository import check_in_repository, cost_repository, expense_repository

_TIME_BASED_EDITABLE_KEYS = frozenset(
    {"label", "amount", "interval_value", "interval_unit", "first_due_date", "notes", "is_active"}
)
_USAGE_BASED_EDITABLE_KEYS = frozenset({"label", "amount_per_unit", "usage_unit", "notes", "is_active"})
_MAINTENANCE_EDITABLE_KEYS = frozenset(
    {
        "label",
        "interval_km",
        "interval_months",
        "last_serviced_at_date",
        "last_serviced_at_odometer",
        "estimated_cost",
        "tire_type",
        "notes",
        "is_active",
    }
)

_Row = TypeVar("_Row")


@dataclass(frozen=True)
class TimeBasedCostView:
    """A recurring cost row plus its current backend-derived monetary rates."""

    row: TimeBasedCost
    reference_amount: Decimal
    annualized_amount: Decimal
    daily_rate: Decimal
    next_due_date: date | None


@dataclass(frozen=True)
class MaintenanceItemView:
    """A maintenance row plus its calculator-derived status and progress figures for a read."""

    row: MaintenanceItem
    status: str
    km_since_service: int | None
    months_since_service: int | None
    km_progress: Decimal | None
    month_progress: Decimal | None
    remaining_km: int | None
    remaining_months: int | None


class CostService:
    """Orchestrates cost-row management over a request-scoped session; owns the transaction."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def list_time_based_costs(self, user_id: uuid.UUID, asset_id: uuid.UUID) -> list[TimeBasedCost]:
        """Return all time-based cost rows for an owned asset. Read-only."""
        self._require_owned_asset(user_id, asset_id)
        return cost_repository.list_time_based_costs(self._session, asset_id)

    def list_time_based_cost_views(
        self, user_id: uuid.UUID, asset_id: uuid.UUID
    ) -> list[TimeBasedCostView]:
        """Return recurring rows with rollover-aware reference, yearly, and daily amounts."""
        self._require_owned_asset(user_id, asset_id)
        rows = cost_repository.list_time_based_costs(self._session, asset_id)
        return self._time_based_views(rows, date.today())

    def create_time_based_cost(
        self,
        user_id: uuid.UUID,
        asset_id: uuid.UUID,
        label: str,
        amount: Decimal,
        interval_value: int,
        interval_unit: str,
        first_due_date: date | None,
        notes: str | None,
    ) -> TimeBasedCost:
        """Add a custom time-based cost row to an owned asset and commit."""
        self._require_owned_asset(user_id, asset_id)
        row = TimeBasedCost(
            asset_id=asset_id,
            technical_key=None,
            label=label,
            amount=amount,
            interval_value=interval_value,
            interval_unit=interval_unit,
            first_due_date=first_due_date,
            notes=notes,
            is_active=True,
        )
        return self._add_and_commit(row)

    def update_time_based_cost(
        self, user_id: uuid.UUID, asset_id: uuid.UUID, cost_id: uuid.UUID, changes: dict[str, object]
    ) -> TimeBasedCost:
        """Apply the sent fields to a time-based cost row on an owned asset and commit."""
        self._require_owned_asset(user_id, asset_id)
        row = cost_repository.get_time_based_cost(self._session, asset_id, cost_id)
        if row is None:
            raise NotFoundError("Time-based cost not found.")
        return self._apply_and_commit(row, changes, _TIME_BASED_EDITABLE_KEYS)

    def next_due_for(self, cost: TimeBasedCost) -> date | None:
        """Compute a time-based cost's informational next-due date as of today."""
        linked_dates = expense_repository.list_linked_time_based_event_dates(self._session, cost.id)
        return self._resolve_next_due(cost, linked_dates, date.today())

    def _resolve_next_due(self, cost: TimeBasedCost, linked_dates: list[date], as_of: date) -> date | None:
        """Resolve a cost's next-due date from the best available anchor.

        Anchor priority: an explicit ``first_due_date`` wins; otherwise the latest linked payment's
        ``event_date`` — the most recent month the cost actually occurred, recorded as a modeled
        expense — is a real occurrence rolled forward to today, so a fresh payment moves the next-due
        one interval past it; failing that, the cost's ``created_at`` is treated as the cycle start
        (next occurrence one interval past creation). Returns ``None`` only for an unsaved row with no
        anchor, no payment, and no creation timestamp.
        """
        if cost.first_due_date is not None:
            return calculator.next_due_date(cost.first_due_date, cost.interval_value, cost.interval_unit, as_of)
        if linked_dates:
            return calculator.next_due_date(max(linked_dates), cost.interval_value, cost.interval_unit, as_of)
        if cost.created_at is None:
            return None
        return calculator.next_due_from_start(cost.created_at.date(), cost.interval_value, cost.interval_unit, as_of)

    def time_based_cost_view(self, row: TimeBasedCost) -> TimeBasedCostView:
        """Enrich one already-owned recurring row for create/update responses."""
        return self._time_based_views([row], date.today())[0]

    def list_usage_based_costs(self, user_id: uuid.UUID, asset_id: uuid.UUID) -> list[UsageBasedCost]:
        """Return all usage-based cost rows for an owned asset. Read-only."""
        self._require_owned_asset(user_id, asset_id)
        return cost_repository.list_usage_based_costs(self._session, asset_id)

    def create_usage_based_cost(
        self,
        user_id: uuid.UUID,
        asset_id: uuid.UUID,
        label: str,
        amount_per_unit: Decimal,
        usage_unit: str,
        notes: str | None,
    ) -> UsageBasedCost:
        """Add a usage-based cost component to an owned asset, deriving currency from its bucket, and commit."""
        self._require_owned_asset(user_id, asset_id)
        bucket = expense_repository.get_bucket_for_asset(self._session, asset_id)
        if bucket is None:
            raise NotFoundError("Bucket not found for asset.")
        row = UsageBasedCost(
            asset_id=asset_id,
            technical_key=None,
            label=label,
            amount_per_unit=amount_per_unit,
            usage_unit=usage_unit,
            currency=bucket.currency,
            notes=notes,
            is_active=True,
        )
        return self._add_and_commit(row)

    def update_usage_based_cost(
        self, user_id: uuid.UUID, asset_id: uuid.UUID, cost_id: uuid.UUID, changes: dict[str, object]
    ) -> UsageBasedCost:
        """Apply the sent fields to a usage-based cost row on an owned asset and commit."""
        self._require_owned_asset(user_id, asset_id)
        row = cost_repository.get_usage_based_cost(self._session, asset_id, cost_id)
        if row is None:
            raise NotFoundError("Usage-based cost not found.")
        return self._apply_and_commit(row, changes, _USAGE_BASED_EDITABLE_KEYS)

    def list_maintenance_items(self, user_id: uuid.UUID, asset_id: uuid.UUID) -> list[MaintenanceItem]:
        """Return all maintenance item rows for an owned asset. Read-only."""
        self._require_owned_asset(user_id, asset_id)
        return cost_repository.list_maintenance_items(self._session, asset_id)

    def list_maintenance_item_views(self, user_id: uuid.UUID, asset_id: uuid.UUID) -> list[MaintenanceItemView]:
        """Return each maintenance row enriched with derived status and progress. Read-only."""
        self._require_owned_asset(user_id, asset_id)
        rows = cost_repository.list_maintenance_items(self._session, asset_id)
        current_usage = self._current_asset_usage(asset_id)
        today = date.today()
        return [self._maintenance_view(row, current_usage, today) for row in rows]

    def current_asset_usage(self, user_id: uuid.UUID, asset_id: uuid.UUID) -> int | None:
        """Return an owned asset's current usage counter for reuse by the asset-detail read. Read-only."""
        self._require_owned_asset(user_id, asset_id)
        return self._current_asset_usage(asset_id)

    def maintenance_item_view(self, row: MaintenanceItem) -> MaintenanceItemView:
        """Enrich a single already-owned maintenance row with derived status and progress.

        Used to serialize a just-created or just-updated row without re-checking ownership.
        """
        current_usage = self._current_asset_usage(row.asset_id)
        return self._maintenance_view(row, current_usage, date.today())

    def create_maintenance_item(
        self,
        user_id: uuid.UUID,
        asset_id: uuid.UUID,
        label: str,
        interval_km: int | None,
        interval_months: int | None,
        last_serviced_at_date: date | None,
        last_serviced_at_odometer: int | None,
        estimated_cost: Decimal | None,
        tire_type: str | None,
        notes: str | None,
    ) -> MaintenanceItem:
        """Add a custom maintenance item to an owned asset and commit.

        The request schema already guarantees at least one interval, so no catch-all row is created here.
        """
        self._require_owned_asset(user_id, asset_id)
        row = MaintenanceItem(
            asset_id=asset_id,
            technical_key=None,
            label=label,
            interval_km=interval_km,
            interval_months=interval_months,
            last_serviced_at_date=last_serviced_at_date,
            last_serviced_at_odometer=last_serviced_at_odometer,
            estimated_cost=estimated_cost,
            tire_type=tire_type,
            notes=notes,
            is_active=True,
        )
        return self._add_and_commit(row)

    def update_maintenance_item(
        self, user_id: uuid.UUID, asset_id: uuid.UUID, item_id: uuid.UUID, changes: dict[str, object]
    ) -> MaintenanceItem:
        """Apply the sent fields to a maintenance item, enforce the interval rule, and commit."""
        self._require_owned_asset(user_id, asset_id)
        row = cost_repository.get_maintenance_item(self._session, asset_id, item_id)
        if row is None:
            raise NotFoundError("Maintenance item not found.")
        return self._apply_and_commit(row, changes, _MAINTENANCE_EDITABLE_KEYS, self._require_interval_unless_other)

    def _require_owned_asset(self, user_id: uuid.UUID, asset_id: uuid.UUID) -> Asset:
        """Return the owned asset or raise `NotFoundError` so unowned rows never leak."""
        asset = cost_repository.get_owned_asset(self._session, user_id, asset_id)
        if asset is None:
            raise NotFoundError("Asset not found.")
        return asset

    def _time_based_views(self, rows: list[TimeBasedCost], as_of: date) -> list[TimeBasedCostView]:
        """Compute current recurring-cost figures with one bucket-expense read for the row set."""
        if not rows:
            return []
        bucket = expense_repository.get_bucket_for_asset(self._session, rows[0].asset_id)
        if bucket is None:
            raise NotFoundError("Bucket not found for asset.")
        expenses = expense_repository.list_expenses_for_bucket(self._session, bucket.id)
        linked_by_source: dict[uuid.UUID, list[tuple[date, Decimal]]] = {}
        for expense in expenses:
            if (
                expense.kind == "modeled"
                and expense.source_type == "time_based_cost"
                and expense.source_id is not None
            ):
                linked_by_source.setdefault(expense.source_id, []).append((expense.event_date, expense.amount))

        views: list[TimeBasedCostView] = []
        for row in rows:
            reference = calculator.reference_amount(row.amount, linked_by_source.get(row.id, []), as_of)
            annualized = calculator.time_based_annualized_amount(
                reference, row.interval_value, row.interval_unit
            )
            daily = calculator.time_based_daily_rate(reference, row.interval_value, row.interval_unit)
            views.append(
                TimeBasedCostView(
                    row=row,
                    reference_amount=calculator.quantize_currency(reference, bucket.currency),
                    annualized_amount=calculator.quantize_currency(annualized, bucket.currency),
                    daily_rate=calculator.quantize_currency(daily, bucket.currency),
                    next_due_date=self._resolve_next_due(
                        row, [event_date for event_date, _ in linked_by_source.get(row.id, [])], as_of
                    ),
                )
            )
        return views

    def _current_asset_usage(self, asset_id: uuid.UUID) -> int | None:
        """Derive the asset's current usage counter: latest posted `usage_end`, else starting odometer.

        Returns None for a non-vehicle asset with no posted check-in, so distance progress is skipped.
        """
        latest = check_in_repository.get_latest_posted_check_in(self._session, asset_id)
        if latest is not None and latest.usage_end is not None:
            return latest.usage_end
        profile = check_in_repository.get_vehicle_profile(self._session, asset_id)
        return profile.starting_odometer if profile is not None else None

    def _maintenance_view(
        self, row: MaintenanceItem, current_usage: int | None, today: date
    ) -> MaintenanceItemView:
        """Compute one row's since-service distances/months, progress ratios, status, and remaining."""
        km_since_service = self._km_since_service(row, current_usage)
        months_since_service = (
            calculator.whole_months(row.last_serviced_at_date, today)
            if row.last_serviced_at_date is not None
            else None
        )
        km_progress, month_progress = calculator.maintenance_progress(
            km_since_service, row.interval_km, months_since_service, row.interval_months
        )
        status = calculator.maintenance_status(km_progress, month_progress)
        remaining_km = (
            max(0, row.interval_km - km_since_service)
            if row.interval_km is not None and km_since_service is not None
            else None
        )
        remaining_months = (
            max(0, row.interval_months - months_since_service)
            if row.interval_months is not None and months_since_service is not None
            else None
        )
        return MaintenanceItemView(
            row=row,
            status=status,
            km_since_service=km_since_service,
            months_since_service=months_since_service,
            km_progress=km_progress,
            month_progress=month_progress,
            remaining_km=remaining_km,
            remaining_months=remaining_months,
        )

    def _km_since_service(self, row: MaintenanceItem, current_usage: int | None) -> int | None:
        """Distance since last service, or None when unknown; never negative on odometer anomalies."""
        if current_usage is None or row.last_serviced_at_odometer is None:
            return None
        delta = current_usage - row.last_serviced_at_odometer
        return delta if delta >= 0 else None

    def _apply_and_commit(
        self,
        row: _Row,
        changes: dict[str, object],
        editable_keys: frozenset[str],
        validate: Callable[[_Row], None] | None = None,
    ) -> _Row:
        """Mutate whitelisted keys, run any post-merge validation, flush, and commit.

        Mutation, validation, and commit share one rollback guard so a validation failure discards
        the in-session mutation instead of leaving a dirty row to break the next request's flush.
        """
        try:
            self._apply_changes(row, changes, editable_keys)
            if validate is not None:
                validate(row)
            self._session.flush()
            self._session.commit()
        except Exception:
            self._session.rollback()
            raise
        return row

    def _apply_changes(self, row: object, changes: dict[str, object], editable_keys: frozenset[str]) -> None:
        """Mutate only whitelisted keys on the loaded row; reject anything else defensively."""
        for key, value in changes.items():
            if key not in editable_keys:
                raise ValidationError(f"Field '{key}' cannot be edited.")
            setattr(row, key, value)

    def _require_interval_unless_other(self, row: MaintenanceItem) -> None:
        """Reject a merged maintenance row with no interval unless it is the `other` catch-all."""
        if row.interval_km is None and row.interval_months is None and row.technical_key != "other":
            raise ValidationError("A maintenance item must keep interval_km or interval_months.")

    def _add_and_commit(self, row: _Row) -> _Row:
        """Add a new row, flush for its id, and commit; roll back on any failure."""
        try:
            cost_repository.add_and_flush(self._session, row)
            self._session.commit()
        except Exception:
            self._session.rollback()
            raise
        return row
