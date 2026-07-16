"""Persistence for the asset aggregate. Owns inserts and flushes, never the transaction."""

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.asset import Asset, Bucket, VehicleProfile
from app.domain.cost import MaintenanceItem, TimeBasedCost, UsageBasedCost


def list_owned_assets(session: Session, user_id: uuid.UUID) -> list[Asset]:
    """Return the user's active (non-archived) assets, oldest first.

    This is the ownership gate for the workspace overview: it never returns another user's rows
    and never widens beyond active assets.
    """
    stmt = (
        select(Asset)
        .where(Asset.user_id == user_id, Asset.archived_at.is_(None))
        .order_by(Asset.created_at)
    )
    return list(session.scalars(stmt).all())


def persist_asset(session: Session, asset: Asset) -> None:
    """Add and flush the asset so its server-generated `id` is populated for dependent rows.

    Flushed first, on its own, because the bucket, optional vehicle profile, and cloned cost rows
    all reference `asset.id`. No commit — the service owns the transaction boundary.
    """
    session.add(asset)
    session.flush()


def insert_asset_dependents(
    session: Session,
    bucket: Bucket,
    profile: VehicleProfile | None,
    time_based: list[TimeBasedCost],
    usage_based: list[UsageBasedCost],
    maintenance: list[MaintenanceItem],
) -> None:
    """Insert every row that hangs off an already-persisted asset, then flush.

    The bucket is always inserted; the vehicle profile only when a template supplied one. Empty
    cost lists are no-ops, so a bare asset inserts just its bucket. The flush materializes
    server-side defaults/PKs (`bucket.id`, each cost row `id`) so the caller can serialize them.
    Still no commit — all inserts stay in the caller's transaction.
    """
    session.add(bucket)
    if profile is not None:
        session.add(profile)
    session.add_all(time_based)
    session.add_all(usage_based)
    session.add_all(maintenance)
    session.flush()
