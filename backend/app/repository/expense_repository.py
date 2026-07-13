"""Ownership-scoped persistence for asset expense events. Owns queries and flushes, never the transaction."""

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.asset import Asset, Bucket
from app.domain.check_in import ExpenseEvent
from app.domain.cost import MaintenanceItem, TimeBasedCost, UsageBasedCost

_SOURCE_MODELS = {
    "time_based_cost": TimeBasedCost,
    "usage_based_cost": UsageBasedCost,
    "maintenance_item": MaintenanceItem,
}


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
