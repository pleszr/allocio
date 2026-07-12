"""Vehicle creation use case: assemble the full record set and persist it atomically."""

import uuid
from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.domain.asset import Asset, Bucket, VehicleProfile
from app.domain.cost import MaintenanceItem, TimeBasedCost, UsageBasedCost
from app.domain.vehicle_defaults import build_default_rows
from app.repository.vehicle_repository import insert_vehicle_dependents, persist_asset

BUCKET_CURRENCY = "HUF"


@dataclass(frozen=True)
class CreatedVehicle:
    """The full record set produced by one vehicle creation, ready for response serialization."""

    asset: Asset
    profile: VehicleProfile
    bucket: Bucket
    time_based_costs: list[TimeBasedCost]
    usage_based_costs: list[UsageBasedCost]
    maintenance_items: list[MaintenanceItem]


class VehicleService:
    """Orchestrates vehicle creation over a request-scoped session; owns the transaction."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def create_vehicle(
        self,
        user_id: uuid.UUID,
        name: str,
        year: int | None,
        make: str | None,
        model: str | None,
        starting_odometer: int,
    ) -> CreatedVehicle:
        """Create the asset, profile, bucket, and cloned default cost rows in one transaction.

        Persists the asset first so its id is available, clones the current default templates
        onto it, inserts everything, and commits exactly once. Any failure rolls back the whole
        set — there is no state where only part of the record set exists.
        """
        try:
            asset = Asset(type="vehicle", user_id=user_id, name=name)
            persist_asset(self._session, asset)

            profile = VehicleProfile(
                asset_id=asset.id, year=year, make=make, model=model, starting_odometer=starting_odometer
            )
            bucket = Bucket(asset_id=asset.id, currency=BUCKET_CURRENCY)
            time_based, usage_based, maintenance = build_default_rows(asset.id)

            insert_vehicle_dependents(self._session, profile, bucket, time_based, usage_based, maintenance)
            self._session.commit()
        except Exception:
            self._session.rollback()
            raise

        return CreatedVehicle(
            asset=asset,
            profile=profile,
            bucket=bucket,
            time_based_costs=time_based,
            usage_based_costs=usage_based,
            maintenance_items=maintenance,
        )
