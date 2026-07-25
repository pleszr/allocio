"""Check-in history use case: list an owned asset's posted check-ins as a running ledger.

Read-only, like `balance_history_service`. Reuses the same ownership-gate repository calls and
never commits or flushes; a zero-check-in asset returns an empty row list, not a 404.
"""

import uuid
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from sqlalchemy.orm import Session

from app.common.exceptions import NotFoundError
from app.domain.asset import Bucket
from app.domain.check_in import CheckIn
from app.repository import check_in_repository, expense_repository


@dataclass(frozen=True)
class CheckInHistoryRow:
    """One posted check-in's ledger row, in period order."""

    check_in_id: uuid.UUID
    period_end: date
    usage_end: int | None
    usage_since_last: int | None
    elapsed_days: int
    allocated: Decimal
    expense: Decimal
    bucket_expense: Decimal
    paid_out_of_pocket: Decimal
    net: Decimal
    balance: Decimal


@dataclass(frozen=True)
class CheckInHistory:
    """An owned asset's ordered (oldest → newest) check-in ledger for a `GET .../check-in-history` call."""

    asset_id: uuid.UUID
    currency: str
    rows: list[CheckInHistoryRow]


class CheckInHistoryService:
    """Reconstructs a read-only per-check-in ledger over a request-scoped session; never mutates."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def check_in_history(self, user_id: uuid.UUID, asset_id: uuid.UUID) -> CheckInHistory:
        """Build the ordered ledger for one owned asset. Writes nothing."""
        bucket = self._owned_bucket(user_id, asset_id)
        check_ins = check_in_repository.list_posted_check_ins(self._session, asset_id)
        allocation_totals = check_in_repository.sum_allocation_amounts_by_check_in(self._session, bucket.id)
        expense_totals = expense_repository.sum_expense_funding_by_check_in(self._session, bucket.id)
        rows = self._build_rows(check_ins, allocation_totals, expense_totals)
        return CheckInHistory(asset_id=asset_id, currency=bucket.currency, rows=rows)

    def _owned_bucket(self, user_id: uuid.UUID, asset_id: uuid.UUID) -> Bucket:
        """Gate on ownership then resolve the asset's bucket; unowned or missing rows raise `NotFoundError`."""
        if expense_repository.get_owned_asset(self._session, user_id, asset_id) is None:
            raise NotFoundError("Asset not found.")
        bucket = expense_repository.get_bucket_for_asset(self._session, asset_id)
        if bucket is None:
            raise NotFoundError("Bucket not found for asset.")
        return bucket

    def _build_rows(
        self,
        check_ins: list[CheckIn],
        allocation_totals: dict[uuid.UUID, Decimal],
        expense_totals: dict[uuid.UUID, expense_repository.ExpenseFundingTotals],
    ) -> list[CheckInHistoryRow]:
        """Walk posted check-ins in period order, accumulating the running bucket balance."""
        rows: list[CheckInHistoryRow] = []
        balance = Decimal(0)
        for check_in in check_ins:
            allocated = allocation_totals.get(check_in.id, Decimal(0))
            funding = expense_totals.get(
                check_in.id,
                expense_repository.ExpenseFundingTotals(Decimal(0), Decimal(0), Decimal(0)),
            )
            net = allocated - funding.bucket_amount
            balance = max(balance + net, Decimal(0))
            rows.append(
                CheckInHistoryRow(
                    check_in_id=check_in.id,
                    period_end=check_in.period_end,
                    usage_end=check_in.usage_end,
                    usage_since_last=check_in.usage_amount,
                    elapsed_days=(check_in.period_end - check_in.period_start).days,
                    allocated=allocated,
                    expense=funding.amount,
                    bucket_expense=funding.bucket_amount,
                    paid_out_of_pocket=funding.paid_out_of_pocket,
                    net=net,
                    balance=balance,
                )
            )
        return rows
