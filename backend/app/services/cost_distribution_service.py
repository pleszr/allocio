"""Cost-distribution use case: group an owned asset's posted expenses by cost item over a trailing window.

Read-only, like `balance_history_service` and `check_in_history_service`. Powers the Costs screen's
distribution pie chart: one slice per distinct cost item (not per transaction), summed over the last
`months` months or however much history the asset actually has, whichever is shorter.
"""

import uuid
from calendar import monthrange
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from sqlalchemy.orm import Session

from app.common.exceptions import NotFoundError
from app.domain.asset import Bucket
from app.domain.check_in import ExpenseEvent
from app.repository import expense_repository


@dataclass(frozen=True)
class CostDistributionSlice:
    """One cost item's total posted amount within the window."""

    label: str
    source_type: str | None
    amount: Decimal


@dataclass(frozen=True)
class CostDistribution:
    """An owned asset's expense-by-cost-item breakdown for a `GET .../cost-distribution` call."""

    asset_id: uuid.UUID
    currency: str
    window_start: date
    window_end: date
    months_with_data: int
    total: Decimal
    slices: list[CostDistributionSlice]


class CostDistributionService:
    """Groups an owned asset's posted expenses by cost item over a request-scoped session; never mutates."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def cost_distribution(self, user_id: uuid.UUID, asset_id: uuid.UUID, months: int) -> CostDistribution:
        """Build the cost-item breakdown for one owned asset over the trailing `months` months. Writes nothing."""
        bucket = self._owned_bucket(user_id, asset_id)
        window_end = date.today()
        window_start = _subtract_months_clamped(window_end, months)
        expenses = expense_repository.list_expenses_for_bucket_since(self._session, bucket.id, window_start)
        source_labels = expense_repository.resolve_source_labels(self._session, expenses)
        slices = self._aggregate(expenses, source_labels)
        return CostDistribution(
            asset_id=asset_id,
            currency=bucket.currency,
            window_start=window_start,
            window_end=window_end,
            months_with_data=len({(expense.event_date.year, expense.event_date.month) for expense in expenses}),
            total=sum((s.amount for s in slices), Decimal(0)),
            slices=slices,
        )

    def _owned_bucket(self, user_id: uuid.UUID, asset_id: uuid.UUID) -> Bucket:
        """Gate on ownership then resolve the asset's bucket; unowned or missing rows raise `NotFoundError`."""
        if expense_repository.get_owned_asset(self._session, user_id, asset_id) is None:
            raise NotFoundError("Asset not found.")
        bucket = expense_repository.get_bucket_for_asset(self._session, asset_id)
        if bucket is None:
            raise NotFoundError("Bucket not found for asset.")
        return bucket

    def _aggregate(
        self, expenses: list[ExpenseEvent], source_labels: dict[tuple[str, uuid.UUID], str]
    ) -> list[CostDistributionSlice]:
        """Sum `amount` per distinct cost item, largest first."""
        totals: dict[tuple[str, str | None], Decimal] = {}
        for expense in expenses:
            key = self._group_key(expense, source_labels)
            totals[key] = totals.get(key, Decimal(0)) + expense.amount
        return sorted(
            (
                CostDistributionSlice(label=label, source_type=source_type, amount=amount)
                for (label, source_type), amount in totals.items()
            ),
            key=lambda item: item.amount,
            reverse=True,
        )

    @staticmethod
    def _group_key(expense: ExpenseEvent, source_labels: dict[tuple[str, uuid.UUID], str]) -> tuple[str, str | None]:
        """Resolve the cost-item identity a transaction rolls up into, ignoring its own one-off comment.

        Unlike `ExpenseEvent.resolved_label`, this never appends the transaction's `comment` — doing
        so would split one recurring cost row (e.g. "Insurance") into a new slice per transaction note.
        """
        if expense.source_type is not None and expense.source_id is not None:
            label = source_labels.get((expense.source_type, expense.source_id))
            if label:
                return label, expense.source_type
        if expense.source_type:
            return expense.source_type.replace("_", " ").capitalize(), expense.source_type
        if expense.comment:
            return expense.comment, None
        return "Manual expense", None


def _subtract_months_clamped(value: date, months: int) -> date:
    """Move a date back by whole calendar months, clamping its day to the target month's final day."""
    target_month_index = value.year * 12 + value.month - 1 - months
    target_year, zero_based_month = divmod(target_month_index, 12)
    target_month = zero_based_month + 1
    return date(target_year, target_month, min(value.day, monthrange(target_year, target_month)[1]))
