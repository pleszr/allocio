"""Ownership-scoped persistence for check-ins and their posted events. Owns queries and flushes, never the transaction."""

import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.domain.asset import Asset, VehicleProfile
from app.domain.check_in import AllocationEvent, CheckIn, ExpenseEvent


def get_owned_asset(session: Session, user_id: uuid.UUID, asset_id: uuid.UUID) -> Asset | None:
    """Return the asset only when it is owned by `user_id`; otherwise `None`.

    One query is the ownership gate for every check-in call, so an unowned asset is indistinguishable
    from a missing one and never leaks another user's rows.
    """
    stmt = select(Asset).where(Asset.id == asset_id, Asset.user_id == user_id)
    return session.scalars(stmt).one_or_none()


def get_vehicle_profile(session: Session, asset_id: uuid.UUID) -> VehicleProfile | None:
    """Return the asset's vehicle profile, or `None`; its `starting_odometer` seeds the first check-in."""
    stmt = select(VehicleProfile).where(VehicleProfile.asset_id == asset_id)
    return session.scalars(stmt).one_or_none()


def get_latest_posted_check_in(session: Session, asset_id: uuid.UUID) -> CheckIn | None:
    """Return the asset's posted check-in with the greatest `period_end`, or `None` if none is posted.

    Its `period_end`/`usage_end` become the next period's contiguous start (no gap or overlap).
    """
    stmt = (
        select(CheckIn)
        .where(CheckIn.asset_id == asset_id, CheckIn.status == "posted")
        .order_by(CheckIn.period_end.desc())
        .limit(1)
    )
    return session.scalars(stmt).one_or_none()


def list_posted_check_ins(session: Session, asset_id: uuid.UUID) -> list[CheckIn]:
    """Return every posted check-in for the asset, oldest first, for the History ledger."""
    stmt = (
        select(CheckIn)
        .where(CheckIn.asset_id == asset_id, CheckIn.status == "posted")
        .order_by(CheckIn.period_end)
    )
    return list(session.scalars(stmt).all())


def get_owned_check_in(
    session: Session, user_id: uuid.UUID, asset_id: uuid.UUID, check_in_id: uuid.UUID
) -> CheckIn | None:
    """Return the posted check-in only when it belongs to `asset_id` and the asset is owned by `user_id`.

    Joins through the asset ownership gate so an unowned, non-posted, or missing check-in is
    indistinguishable from any other 404 and never leaks another user's rows.
    """
    stmt = (
        select(CheckIn)
        .join(Asset, Asset.id == CheckIn.asset_id)
        .where(
            CheckIn.id == check_in_id,
            CheckIn.asset_id == asset_id,
            CheckIn.status == "posted",
            Asset.user_id == user_id,
        )
    )
    return session.scalars(stmt).one_or_none()


def list_posted_check_ins_after(session: Session, asset_id: uuid.UUID, period_end: date) -> list[CheckIn]:
    """Return posted check-ins with a later `period_end`, oldest first, for an edit's forward-simulation walk."""
    stmt = (
        select(CheckIn)
        .where(CheckIn.asset_id == asset_id, CheckIn.status == "posted", CheckIn.period_end > period_end)
        .order_by(CheckIn.period_end)
    )
    return list(session.scalars(stmt).all())


def list_allocation_events_for_check_in(session: Session, check_in_id: uuid.UUID) -> list[AllocationEvent]:
    """Return every allocation event posted for one check-in, for its detail view."""
    stmt = select(AllocationEvent).where(AllocationEvent.check_in_id == check_in_id)
    return list(session.scalars(stmt).all())


def get_latest_check_in_linked_to_maintenance_item(
    session: Session, asset_id: uuid.UUID, maintenance_item_id: uuid.UUID
) -> CheckIn | None:
    """Return the asset's latest posted check-in that still links an expense to this maintenance item.

    Used to re-derive a maintenance item's baseline after an edit changes which check-in is "latest".
    """
    stmt = (
        select(CheckIn)
        .join(ExpenseEvent, ExpenseEvent.check_in_id == CheckIn.id)
        .where(
            CheckIn.asset_id == asset_id,
            CheckIn.status == "posted",
            ExpenseEvent.source_type == "maintenance_item",
            ExpenseEvent.source_id == maintenance_item_id,
        )
        .order_by(CheckIn.period_end.desc())
        .limit(1)
    )
    return session.scalars(stmt).one_or_none()


def sum_allocation_amounts_by_check_in(session: Session, bucket_id: uuid.UUID) -> dict[uuid.UUID, Decimal]:
    """Return each check-in's total posted allocation amount, keyed by `check_in_id`, for the History ledger."""
    stmt = (
        select(AllocationEvent.check_in_id, func.sum(AllocationEvent.amount))
        .where(AllocationEvent.bucket_id == bucket_id)
        .group_by(AllocationEvent.check_in_id)
    )
    return {check_in_id: total for check_in_id, total in session.execute(stmt).all()}


def list_posted_allocation_amounts(session: Session, bucket_id: uuid.UUID) -> list[Decimal]:
    """Return the amounts of every posted allocation event for the bucket, for balance reconstruction."""
    stmt = select(AllocationEvent.amount).where(AllocationEvent.bucket_id == bucket_id)
    return list(session.scalars(stmt).all())


def list_posted_allocation_amounts_before(session: Session, bucket_id: uuid.UUID, period_end: date) -> list[Decimal]:
    """Return posted allocation amounts effective strictly before `period_end`, for an edit's opening balance.

    An allocation event's `event_date` is always its own check-in's `period_end` (see
    `CheckInService._build_allocation_events`), so this scopes to "everything posted for an earlier
    period" exactly as an edit's balance-before must.
    """
    stmt = select(AllocationEvent.amount).where(
        AllocationEvent.bucket_id == bucket_id, AllocationEvent.event_date < period_end
    )
    return list(session.scalars(stmt).all())


def list_posted_allocation_events(session: Session, bucket_id: uuid.UUID) -> list[tuple[date, Decimal]]:
    """Return every posted allocation event's `(event_date, amount)` for the bucket, ordered by date.

    Dated counterpart of `list_posted_allocation_amounts`, used to reconstruct the balance history
    series; that amounts-only query stays for the workspace overview's single-figure balance.
    """
    stmt = (
        select(AllocationEvent.event_date, AllocationEvent.amount)
        .where(AllocationEvent.bucket_id == bucket_id)
        .order_by(AllocationEvent.event_date)
    )
    return [(row.event_date, row.amount) for row in session.execute(stmt).all()]


def list_allocation_events_for_bucket(session: Session, bucket_id: uuid.UUID) -> list[AllocationEvent]:
    """Return every posted allocation event row for the bucket, newest first, for the activity feed.

    Full rows (not just amounts) so callers can read each event's `metadata_json` label.
    """
    stmt = (
        select(AllocationEvent)
        .where(AllocationEvent.bucket_id == bucket_id)
        .order_by(AllocationEvent.event_date.desc())
    )
    return list(session.scalars(stmt).all())


def get_posted_usage_totals(
    session: Session, asset_id: uuid.UUID
) -> tuple[int, date | None, date | None]:
    """Aggregate posted check-in usage into a total and its covered date span.

    Sizes the trailing usage window for the workspace overview's usage-based monthly accrual.

    Returns:
        ``(total_usage, first_period_start, last_period_end)``; ``(0, None, None)`` when the asset
        has no posted check-ins.
    """
    stmt = select(
        func.coalesce(func.sum(CheckIn.usage_amount), 0),
        func.min(CheckIn.period_start),
        func.max(CheckIn.period_end),
    ).where(CheckIn.asset_id == asset_id, CheckIn.status == "posted")
    total_usage, first_start, last_end = session.execute(stmt).one()
    return int(total_usage), first_start, last_end


def add_and_flush(session: Session, row: CheckIn | AllocationEvent | ExpenseEvent) -> None:
    """Add a newly built check-in or event and flush so its server-generated id is populated.

    No commit — the service owns the transaction boundary so the whole check-in posts all-or-none.
    """
    session.add(row)
    session.flush()
