"""Cost-management use cases: list, create, edit, and deactivate asset-owned cost rows.

Every method is ownership-scoped and never touches posted history, so edits only affect future
accruals. The service owns the transaction boundary; the repository owns queries and flushes.
"""

import uuid
from collections.abc import Callable
from datetime import date
from decimal import Decimal
from typing import TypeVar

from sqlalchemy.orm import Session

from app.common.exceptions import NotFoundError, ValidationError
from app.domain import calculator
from app.domain.asset import Asset
from app.domain.cost import MaintenanceItem, TimeBasedCost, UsageBasedCost
from app.repository import cost_repository

_TIME_BASED_EDITABLE_KEYS = frozenset(
    {"label", "amount", "interval_value", "interval_unit", "first_due_date", "notes", "is_active"}
)
_USAGE_BASED_EDITABLE_KEYS = frozenset({"amount_per_unit", "notes"})
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


class CostService:
    """Orchestrates cost-row management over a request-scoped session; owns the transaction."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def list_time_based_costs(self, user_id: uuid.UUID, asset_id: uuid.UUID) -> list[TimeBasedCost]:
        """Return all time-based cost rows for an owned asset. Read-only."""
        self._require_owned_asset(user_id, asset_id)
        return cost_repository.list_time_based_costs(self._session, asset_id)

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
        """Compute a time-based cost's informational next-due date as of today, or None without an anchor."""
        return calculator.next_due_date(cost.first_due_date, cost.interval_value, cost.interval_unit, date.today())

    def update_usage_based_cost(
        self, user_id: uuid.UUID, asset_id: uuid.UUID, changes: dict[str, object]
    ) -> UsageBasedCost:
        """Apply the sent fields to the single active usage-based reserve and commit."""
        self._require_owned_asset(user_id, asset_id)
        row = cost_repository.get_active_usage_based_cost(self._session, asset_id)
        if row is None:
            raise NotFoundError("Usage-based reserve not found.")
        return self._apply_and_commit(row, changes, _USAGE_BASED_EDITABLE_KEYS)

    def list_maintenance_items(self, user_id: uuid.UUID, asset_id: uuid.UUID) -> list[MaintenanceItem]:
        """Return all maintenance item rows for an owned asset. Read-only."""
        self._require_owned_asset(user_id, asset_id)
        return cost_repository.list_maintenance_items(self._session, asset_id)

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
