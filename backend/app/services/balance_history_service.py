"""Balance-history use case: reconstruct a monthly bucket-balance series for one owned asset.

Read-only. Reuses the pure `app.domain.calculator` helpers for all money math and the existing
single-asset repository functions. It never commits or flushes; empty history is a valid result
(a single current-month zero point), not a 404.

The newest point is a live snapshot as of today, so — assuming every effective bucket movement date
is on or before today — it equals the live covered balance `workspace_service` derives. Check-in
expense coverage moves at period end beside its allocation; standalone coverage moves at event date.
"""

import uuid
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from sqlalchemy.orm import Session

from app.common.exceptions import NotFoundError
from app.domain import calculator
from app.domain.asset import Bucket
from app.repository import check_in_repository, expense_repository


@dataclass(frozen=True)
class BalancePoint:
    """One monthly point of the reconstructed series; `month` is the `"YYYY-MM"` label of `as_of`."""

    month: str
    as_of: date
    balance: Decimal


@dataclass(frozen=True)
class BalanceHistory:
    """An owned asset's ordered (oldest → newest) monthly balance series for a `GET .../balance-history` call."""

    asset_id: uuid.UUID
    currency: str
    points: list[BalancePoint]


class BalanceHistoryService:
    """Reconstructs a read-only monthly balance series over a request-scoped session; never mutates."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def balance_history(self, user_id: uuid.UUID, asset_id: uuid.UUID, months: int) -> BalanceHistory:
        """Derive the monthly balance series for one owned asset. Writes nothing."""
        bucket = self._owned_bucket(user_id, asset_id)
        signed = self._signed_events(bucket.id)
        as_of_dates = calculator.month_anchor_dates(
            date.today(), months, min((event_date for event_date, _ in signed), default=None)
        )
        balances = [max(balance, Decimal(0)) for balance in calculator.balance_at_dates(signed, as_of_dates)]
        points = [
            BalancePoint(month=as_of.strftime("%Y-%m"), as_of=as_of, balance=balance)
            for as_of, balance in zip(as_of_dates, balances, strict=True)
        ]
        return BalanceHistory(asset_id=asset_id, currency=bucket.currency, points=points)

    def _owned_bucket(self, user_id: uuid.UUID, asset_id: uuid.UUID) -> Bucket:
        """Gate on ownership then resolve the asset's bucket; unowned or missing rows raise `NotFoundError`."""
        if expense_repository.get_owned_asset(self._session, user_id, asset_id) is None:
            raise NotFoundError("Asset not found.")
        bucket = expense_repository.get_bucket_for_asset(self._session, asset_id)
        if bucket is None:
            raise NotFoundError("Bucket not found for asset.")
        return bucket

    def _signed_events(self, bucket_id: uuid.UUID) -> list[tuple[date, Decimal]]:
        """Merge posted allocations (positive) and expenses (negative) into signed net `(date, amount)` pairs."""
        allocations = check_in_repository.list_posted_allocation_events(self._session, bucket_id)
        expenses = expense_repository.list_bucket_expense_movements(self._session, bucket_id)
        return [(event_date, amount) for event_date, amount in allocations] + [
            (event_date, -amount) for event_date, amount in expenses
        ]
