"""Asset creation use case: assemble the record set for one asset and persist it atomically."""

import uuid
from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy.orm import Session

from app.common.exceptions import ValidationError
from app.domain.asset import Asset, Bucket, VehicleProfile
from app.domain.asset_templates import ASSET_TEMPLATES, AssetTemplate
from app.domain.cost import MaintenanceItem, TimeBasedCost, UsageBasedCost
from app.domain.vehicle_defaults import build_selected_rows, overridable_catalog_keys, vehicle_catalog_keys
from app.repository import user_repository
from app.repository.asset_repository import insert_asset_dependents, persist_asset


@dataclass(frozen=True)
class VehicleDetails:
    """Optional vehicle-profile inputs supplied when the vehicle template is selected."""

    year: int | None = None
    make: str | None = None
    model: str | None = None
    starting_odometer: int = 0


@dataclass(frozen=True)
class CostOverride:
    """One user-edited template row, mapped from the request by the router before it reaches the service.

    `interval_value`/`interval_unit` apply to time-based rows only; they are `None` for the
    usage-based reserve row.
    """

    technical_key: str
    amount: Decimal
    interval_value: int | None = None
    interval_unit: str | None = None


@dataclass(frozen=True)
class CreatedAsset:
    """The record set produced by one asset creation, ready for response serialization.

    `profile` is None and the cost lists are empty for a bare (template-less) asset.
    """

    asset: Asset
    profile: VehicleProfile | None
    bucket: Bucket
    time_based_costs: list[TimeBasedCost]
    usage_based_costs: list[UsageBasedCost]
    maintenance_items: list[MaintenanceItem]


class AssetService:
    """Orchestrates asset creation over a request-scoped session; owns the transaction."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def create_asset(
        self,
        user_id: uuid.UUID,
        name: str,
        asset_type: str | None,
        template_key: str | None,
        vehicle_details: VehicleDetails | None,
        subtitle: str | None = None,
        attributes: dict | None = None,
        selected_cost_keys: list[str] | None = None,
        cost_overrides: list[CostOverride] | None = None,
    ) -> CreatedAsset:
        """Create an asset, its bucket, and any template-supplied profile and selected cost rows atomically.

        A template-less asset gets only a bucket. Selecting a template resolves the stored type and
        attaches a vehicle profile when the template carries one; only the template cost rows whose
        `technical_key` is in `selected_cost_keys` are cloned (omitted/empty clones none). Each cloned
        row uses the template's default for the owner's currency unless `cost_overrides` supplies a
        caller-edited value for that row's `technical_key`. `subtitle` and `attributes` are opaque,
        type-agnostic detail the caller supplies for any asset. Persists the asset first for its id,
        inserts every dependent, and commits exactly once; any failure rolls back the whole set.
        """
        template = self._resolve_template(template_key)
        resolved_type = template.asset_type if template is not None else self._require_type(asset_type)
        selected_keys = self._validate_selected_keys(template, selected_cost_keys)
        self._validate_cost_overrides(selected_keys, cost_overrides)
        currency = self._resolve_owner_currency(user_id)
        try:
            asset = Asset(
                type=resolved_type, user_id=user_id, name=name, subtitle=subtitle, attributes=attributes
            )
            persist_asset(self._session, asset)

            bucket = Bucket(asset_id=asset.id, currency=currency)
            profile, time_based, usage_based, maintenance = self._build_template_dependents(
                asset.id, template, vehicle_details, selected_keys, currency, cost_overrides
            )

            insert_asset_dependents(self._session, bucket, profile, time_based, usage_based, maintenance)
            self._session.commit()
        except Exception:
            self._session.rollback()
            raise

        return CreatedAsset(
            asset=asset,
            profile=profile,
            bucket=bucket,
            time_based_costs=time_based,
            usage_based_costs=usage_based,
            maintenance_items=maintenance,
        )

    def _resolve_owner_currency(self, user_id: uuid.UUID) -> str:
        """Return the owner's default currency so the new bucket and seeded rows adopt it.

        The caller is authenticated, so a missing row is an integrity fault rather than user error.
        """
        user = user_repository.get_by_id(self._session, user_id)
        if user is None:
            raise ValidationError(f"Owner '{user_id}' not found.")
        return user.default_currency

    def _resolve_template(self, template_key: str | None) -> AssetTemplate | None:
        """Look up a template by key, or return None for a bare asset; reject an unknown key."""
        if template_key is None:
            return None
        template = ASSET_TEMPLATES.get(template_key)
        if template is None:
            raise ValidationError(f"Unknown asset template '{template_key}'.")
        return template

    def _require_type(self, asset_type: str | None) -> str:
        """Return the caller-supplied type for a bare asset, or reject a missing one."""
        if not asset_type:
            raise ValidationError("A template-less asset must set a type.")
        return asset_type

    def _validate_selected_keys(
        self, template: AssetTemplate | None, selected_cost_keys: list[str] | None
    ) -> set[str]:
        """Normalize the selected keys and reject a template-less selection or unknown catalog keys."""
        selected = set(selected_cost_keys or ())
        if template is None:
            if selected:
                raise ValidationError("Cost selection requires a template.")
            return set()
        unknown = selected - vehicle_catalog_keys()
        if unknown:
            raise ValidationError(f"Unknown cost keys: {sorted(unknown)}.")
        return selected

    def _validate_cost_overrides(self, selected_keys: set[str], cost_overrides: list[CostOverride] | None) -> None:
        """Reject an override for a key that isn't selected or doesn't accept an override.

        Only time-based costs and the usage-based reserve accept an override; a maintenance-item
        key has no curated amount to override.
        """
        for override in cost_overrides or ():
            if override.technical_key not in selected_keys:
                raise ValidationError(f"Cost override for unselected key '{override.technical_key}'.")
            if override.technical_key not in overridable_catalog_keys():
                raise ValidationError(f"Cost key '{override.technical_key}' does not accept an override.")

    def _build_template_dependents(
        self,
        asset_id: uuid.UUID,
        template: AssetTemplate | None,
        vehicle_details: VehicleDetails | None,
        selected_keys: set[str],
        currency: str,
        cost_overrides: list[CostOverride] | None,
    ) -> tuple[VehicleProfile | None, list[TimeBasedCost], list[UsageBasedCost], list[MaintenanceItem]]:
        """Build the profile and selected cost rows for a template, or empty results for a bare asset."""
        if template is None:
            return None, [], [], []
        amount_overrides, interval_overrides = self._split_cost_overrides(cost_overrides)
        time_based, usage_based, maintenance = build_selected_rows(
            asset_id, selected_keys, currency, amount_overrides, interval_overrides
        )
        profile = self._build_vehicle_profile(asset_id, vehicle_details) if template.has_vehicle_profile else None
        return profile, time_based, usage_based, maintenance

    def _split_cost_overrides(
        self, cost_overrides: list[CostOverride] | None
    ) -> tuple[dict[str, Decimal], dict[str, tuple[int, str]]]:
        """Split the flat override list into the amount/interval maps `build_selected_rows` expects."""
        amount_overrides = {override.technical_key: override.amount for override in cost_overrides or ()}
        interval_overrides = {
            override.technical_key: (override.interval_value, override.interval_unit)
            for override in cost_overrides or ()
            if override.interval_value is not None and override.interval_unit is not None
        }
        return amount_overrides, interval_overrides

    def _build_vehicle_profile(self, asset_id: uuid.UUID, vehicle_details: VehicleDetails | None) -> VehicleProfile:
        """Build a vehicle profile from the supplied details, defaulting every field when omitted."""
        details = vehicle_details if vehicle_details is not None else VehicleDetails()
        return VehicleProfile(
            asset_id=asset_id,
            year=details.year,
            make=details.make,
            model=details.model,
            starting_odometer=details.starting_odometer,
        )
