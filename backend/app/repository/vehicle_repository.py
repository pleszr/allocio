"""Persistence for the vehicle aggregate. Owns inserts and flushes, never the transaction."""

from sqlalchemy.orm import Session

from app.domain.asset import Asset, Bucket, VehicleProfile
from app.domain.cost import MaintenanceItem, TimeBasedCost, UsageBasedCost


def persist_asset(session: Session, asset: Asset) -> None:
    """Add and flush the asset so its server-generated `id` is populated for dependent rows.

    Flushed first, on its own, because the vehicle profile, bucket, and cloned cost rows all
    reference `asset.id`. No commit — the service owns the transaction boundary.
    """
    session.add(asset)
    session.flush()


def insert_vehicle_dependents(
    session: Session,
    profile: VehicleProfile,
    bucket: Bucket,
    time_based: list[TimeBasedCost],
    usage_based: list[UsageBasedCost],
    maintenance: list[MaintenanceItem],
) -> None:
    """Insert every row that hangs off an already-persisted asset, then flush.

    The flush materializes server-side defaults/PKs (`bucket.id`, each cost row `id`) so the
    caller can serialize them. Still no commit — all inserts stay in the caller's transaction.
    """
    session.add(profile)
    session.add(bucket)
    session.add_all(time_based)
    session.add_all(usage_based)
    session.add_all(maintenance)
    session.flush()
