"""Expense-logging use case: post auditable outflow events into an asset's bucket and list them back.

Every method is ownership-scoped. The service owns the transaction boundary; the repository owns
queries and flushes. Posted events are immutable here — there is no edit or delete path.
"""

import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy.orm import Session

from app.common.exceptions import NotFoundError, ValidationError
from app.domain.asset import Asset
from app.domain.check_in import ExpenseEvent
from app.repository import expense_repository


class ExpenseService:
    """Orchestrates expense logging over a request-scoped session; owns the transaction."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def log_expense(
        self,
        user_id: uuid.UUID,
        asset_id: uuid.UUID,
        kind: str,
        amount: Decimal,
        event_date: date | None,
        usage_counter_at_event: int | None,
        comment: str | None,
        source_type: str | None,
        source_id: uuid.UUID | None,
        check_in_id: uuid.UUID | None = None,
    ) -> ExpenseEvent:
        """Post an expense event against an owned asset's bucket and commit.

        `check_in_id` defaults to `None` so the endpoint logs standalone expenses; the future monthly
        check-in posting flow reuses this method to attach posted expenses to a check-in.
        """
        self._require_owned_asset(user_id, asset_id)
        bucket = expense_repository.get_bucket_for_asset(self._session, asset_id)
        if bucket is None:
            raise NotFoundError("Bucket not found for asset.")
        if kind == "modeled" and not expense_repository.source_row_exists(
            self._session, asset_id, source_type, source_id
        ):
            raise ValidationError("Source row not found for this asset.")
        row = ExpenseEvent(
            bucket_id=bucket.id,
            check_in_id=check_in_id,
            event_date=event_date or date.today(),
            usage_counter_at_event=usage_counter_at_event,
            kind=kind,
            amount=amount,
            comment=comment,
            source_type=source_type,
            source_id=source_id,
            metadata_json=None,
        )
        return self._add_and_commit(row)

    def list_expenses(self, user_id: uuid.UUID, asset_id: uuid.UUID) -> list[ExpenseEvent]:
        """Return all posted expense events for an owned asset's bucket. Read-only."""
        self._require_owned_asset(user_id, asset_id)
        bucket = expense_repository.get_bucket_for_asset(self._session, asset_id)
        if bucket is None:
            raise NotFoundError("Bucket not found for asset.")
        return expense_repository.list_expenses_for_bucket(self._session, bucket.id)

    def _require_owned_asset(self, user_id: uuid.UUID, asset_id: uuid.UUID) -> Asset:
        """Return the owned asset or raise `NotFoundError` so unowned rows never leak."""
        asset = expense_repository.get_owned_asset(self._session, user_id, asset_id)
        if asset is None:
            raise NotFoundError("Asset not found.")
        return asset

    def _add_and_commit(self, row: ExpenseEvent) -> ExpenseEvent:
        """Add a new event, flush for its id, and commit; roll back on any failure."""
        try:
            expense_repository.add_and_flush(self._session, row)
            self._session.commit()
        except Exception:
            self._session.rollback()
            raise
        return row
