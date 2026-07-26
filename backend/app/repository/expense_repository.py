"""Ownership-scoped persistence for asset expense events. Owns queries and flushes, never the transaction."""

import uuid
from collections.abc import Iterable
from datetime import date
from decimal import Decimal
from typing import NamedTuple

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.domain.asset import Asset, Bucket
from app.domain.check_in import CheckIn, ExpenseEvent
from app.domain.cost import MaintenanceItem, TimeBasedCost, UsageBasedCost

_SOURCE_MODELS = {
    "time_based_cost": TimeBasedCost,
    "usage_based_cost": UsageBasedCost,
    "maintenance_item": MaintenanceItem,
}


class ExpenseFundingTotals(NamedTuple):
    """Aggregated full, bucket-covered, and out-of-pocket expense amounts."""

    amount: Decimal
    bucket_amount: Decimal
    paid_out_of_pocket: Decimal


def get_owned_asset(session: Session, user_id: uuid.UUID, asset_id: uuid.UUID) -> Asset | None:
    """Return the asset only when it is owned by `user_id`; otherwise `None`.

    One query is the ownership gate for every expense call, so an unowned asset is indistinguishable
    from a missing one and never leaks another user's rows.
    """
    stmt = select(Asset).where(Asset.id == asset_id, Asset.user_id == user_id)
    return session.scalars(stmt).one_or_none()


def get_bucket_for_asset(session: Session, asset_id: uuid.UUID) -> Bucket | None:
    """Return the asset's single savings bucket, or `None` if the asset has none."""
    stmt = select(Bucket).where(Bucket.asset_id == asset_id)
    return session.scalars(stmt).one_or_none()


def source_row_exists(
    session: Session, asset_id: uuid.UUID, source_type: str, source_id: uuid.UUID
) -> bool:
    """Return whether the referenced source row exists under the asset for the given source table."""
    model = _SOURCE_MODELS[source_type]
    stmt = select(model.id).where(model.id == source_id, model.asset_id == asset_id)
    return session.scalars(stmt).one_or_none() is not None


def resolve_source_labels(
    session: Session, expenses: Iterable[ExpenseEvent]
) -> dict[tuple[str, uuid.UUID], str]:
    """Batch-resolve modeled expenses' (source_type, source_id) pairs to their source row's label.

    A pair missing from the result means its source row no longer exists; callers fall back to a
    source-type-derived label in that case.
    """
    refs = {
        (expense.source_type, expense.source_id)
        for expense in expenses
        if expense.source_type is not None and expense.source_id is not None
    }
    labels: dict[tuple[str, uuid.UUID], str] = {}
    for source_type, model in _SOURCE_MODELS.items():
        ids = {source_id for st, source_id in refs if st == source_type}
        if not ids:
            continue
        stmt = select(model.id, model.label).where(model.id.in_(ids))
        for row_id, label in session.execute(stmt).all():
            labels[(source_type, row_id)] = label
    return labels


def add_and_flush(session: Session, row: ExpenseEvent) -> None:
    """Add a newly built expense event and flush so its server-generated id is populated.

    No commit — the service owns the transaction boundary.
    """
    session.add(row)
    session.flush()


def list_expenses_for_bucket(session: Session, bucket_id: uuid.UUID) -> list[ExpenseEvent]:
    """Return all expense events for the bucket ordered by `event_date` for stable output."""
    stmt = select(ExpenseEvent).where(ExpenseEvent.bucket_id == bucket_id).order_by(ExpenseEvent.event_date)
    return list(session.scalars(stmt).all())


def list_expenses_for_bucket_since(session: Session, bucket_id: uuid.UUID, since: date) -> list[ExpenseEvent]:
    """Return expense events for the bucket with `event_date >= since`, ordered by `event_date`."""
    stmt = (
        select(ExpenseEvent)
        .where(ExpenseEvent.bucket_id == bucket_id, ExpenseEvent.event_date >= since)
        .order_by(ExpenseEvent.event_date)
    )
    return list(session.scalars(stmt).all())


def list_bucket_expense_movements(session: Session, bucket_id: uuid.UUID) -> list[tuple[date, Decimal]]:
    """Return effective-date, covered-amount pairs used to reconstruct bucket balances.

    Check-in expenses move the bucket at the parent period end alongside that period's allocations;
    standalone expenses move it on their real event date.
    """
    effective_date = func.coalesce(CheckIn.period_end, ExpenseEvent.event_date).label("effective_date")
    bucket_amount = (ExpenseEvent.amount - ExpenseEvent.paid_out_of_pocket).label("bucket_amount")
    stmt = (
        select(effective_date, bucket_amount)
        .outerjoin(CheckIn, ExpenseEvent.check_in_id == CheckIn.id)
        .where(ExpenseEvent.bucket_id == bucket_id)
        .order_by(effective_date)
    )
    return [(row.effective_date, row.bucket_amount) for row in session.execute(stmt).all()]


def sum_expense_funding_by_check_in(
    session: Session, bucket_id: uuid.UUID
) -> dict[uuid.UUID, ExpenseFundingTotals]:
    """Return each check-in's full, covered, and out-of-pocket expense totals."""
    stmt = (
        select(
            ExpenseEvent.check_in_id,
            func.sum(ExpenseEvent.amount),
            func.sum(ExpenseEvent.amount - ExpenseEvent.paid_out_of_pocket),
            func.sum(ExpenseEvent.paid_out_of_pocket),
        )
        .where(ExpenseEvent.bucket_id == bucket_id, ExpenseEvent.check_in_id.is_not(None))
        .group_by(ExpenseEvent.check_in_id)
    )
    return {
        check_in_id: ExpenseFundingTotals(
            amount=amount,
            bucket_amount=bucket_amount,
            paid_out_of_pocket=paid_out_of_pocket,
        )
        for check_in_id, amount, bucket_amount, paid_out_of_pocket in session.execute(stmt).all()
    }


def list_expense_events_for_check_in(session: Session, check_in_id: uuid.UUID) -> list[ExpenseEvent]:
    """Return every expense event row linked to one check-in, ordered by `event_date`, for its detail view."""
    stmt = select(ExpenseEvent).where(ExpenseEvent.check_in_id == check_in_id).order_by(ExpenseEvent.event_date)
    return list(session.scalars(stmt).all())


def delete_expense_events_for_check_in(session: Session, check_in_id: uuid.UUID) -> None:
    """Delete every expense event row linked to this check-in.

    No flush/commit — the service owns the transaction boundary, so the delete and its replacement
    inserts commit together or not at all.
    """
    session.execute(delete(ExpenseEvent).where(ExpenseEvent.check_in_id == check_in_id))


def list_bucket_covered_amounts_before(session: Session, bucket_id: uuid.UUID, period_end: date) -> list[Decimal]:
    """Return bucket-covered expense amounts effective strictly before `period_end`, for an edit's opening balance.

    Uses the same effective-date coalescing as `list_bucket_expense_movements`: a check-in-linked
    expense's covered movement is dated at its parent check-in's `period_end`, a standalone expense's
    at its own `event_date`.
    """
    effective_date = func.coalesce(CheckIn.period_end, ExpenseEvent.event_date)
    bucket_amount = ExpenseEvent.amount - ExpenseEvent.paid_out_of_pocket
    stmt = (
        select(bucket_amount)
        .outerjoin(CheckIn, ExpenseEvent.check_in_id == CheckIn.id)
        .where(ExpenseEvent.bucket_id == bucket_id, effective_date < period_end)
    )
    return list(session.scalars(stmt).all())


def list_expenses_by_check_in(session: Session, bucket_id: uuid.UUID) -> dict[uuid.UUID, list[ExpenseEvent]]:
    """Return each check-in's linked expense events, ordered by `event_date`.

    A check-in absent from the returned dict has no linked expense events.
    """
    stmt = (
        select(ExpenseEvent)
        .where(ExpenseEvent.bucket_id == bucket_id, ExpenseEvent.check_in_id.is_not(None))
        .order_by(ExpenseEvent.event_date)
    )
    expenses_by_check_in: dict[uuid.UUID, list[ExpenseEvent]] = {}
    for expense in session.scalars(stmt).all():
        expenses_by_check_in.setdefault(expense.check_in_id, []).append(expense)
    return expenses_by_check_in
