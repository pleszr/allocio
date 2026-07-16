"""Ownership-scoped persistence for check-ins and their posted events. Owns queries and flushes, never the transaction."""

import uuid
from decimal import Decimal

from sqlalchemy import select
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


def list_posted_allocation_amounts(session: Session, bucket_id: uuid.UUID) -> list[Decimal]:
    """Return the amounts of every posted allocation event for the bucket, for balance reconstruction."""
    stmt = select(AllocationEvent.amount).where(AllocationEvent.bucket_id == bucket_id)
    return list(session.scalars(stmt).all())


def add_and_flush(session: Session, row: CheckIn | AllocationEvent | ExpenseEvent) -> None:
    """Add a newly built check-in or event and flush so its server-generated id is populated.

    No commit — the service owns the transaction boundary so the whole check-in posts all-or-none.
    """
    session.add(row)
    session.flush()
