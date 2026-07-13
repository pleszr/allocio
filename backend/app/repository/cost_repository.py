"""Ownership-scoped persistence for asset-owned cost rows. Owns queries and flushes, never the transaction."""

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.asset import Asset
from app.domain.cost import MaintenanceItem, TimeBasedCost, UsageBasedCost


def get_owned_vehicle_asset(session: Session, user_id: uuid.UUID, asset_id: uuid.UUID) -> Asset | None:
    """Return the asset only when it is a vehicle owned by `user_id`; otherwise `None`.

    One query is the ownership gate for every cost-management call, so an unowned or non-vehicle
    asset is indistinguishable from a missing one and never leaks another user's rows.
    """
    stmt = select(Asset).where(Asset.id == asset_id, Asset.user_id == user_id, Asset.type == "vehicle")
    return session.scalars(stmt).one_or_none()


def list_time_based_costs(session: Session, asset_id: uuid.UUID) -> list[TimeBasedCost]:
    """Return all time-based cost rows for the asset, active and inactive, ordered by label."""
    stmt = select(TimeBasedCost).where(TimeBasedCost.asset_id == asset_id).order_by(TimeBasedCost.label)
    return list(session.scalars(stmt).all())


def get_time_based_cost(session: Session, asset_id: uuid.UUID, cost_id: uuid.UUID) -> TimeBasedCost | None:
    """Return the time-based cost row under the asset, or `None` if no such row exists there."""
    stmt = select(TimeBasedCost).where(TimeBasedCost.id == cost_id, TimeBasedCost.asset_id == asset_id)
    return session.scalars(stmt).one_or_none()


def get_active_usage_based_cost(session: Session, asset_id: uuid.UUID) -> UsageBasedCost | None:
    """Return the single active usage-based reserve row for the asset, or `None` if there is none."""
    stmt = select(UsageBasedCost).where(
        UsageBasedCost.asset_id == asset_id, UsageBasedCost.is_active.is_(True)
    )
    return session.scalars(stmt).one_or_none()


def list_maintenance_items(session: Session, asset_id: uuid.UUID) -> list[MaintenanceItem]:
    """Return all maintenance item rows for the asset, active and inactive, ordered by label."""
    stmt = select(MaintenanceItem).where(MaintenanceItem.asset_id == asset_id).order_by(MaintenanceItem.label)
    return list(session.scalars(stmt).all())


def get_maintenance_item(session: Session, asset_id: uuid.UUID, item_id: uuid.UUID) -> MaintenanceItem | None:
    """Return the maintenance item under the asset, or `None` if no such row exists there."""
    stmt = select(MaintenanceItem).where(MaintenanceItem.id == item_id, MaintenanceItem.asset_id == asset_id)
    return session.scalars(stmt).one_or_none()


def add_and_flush(session: Session, row: object) -> None:
    """Add a newly built row and flush so its server-generated id is populated for the caller.

    No commit — the service owns the transaction boundary.
    """
    session.add(row)
    session.flush()
