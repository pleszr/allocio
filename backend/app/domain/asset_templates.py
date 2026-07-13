"""Built-in asset templates: the seam that keeps `vehicle` a template, not a hardcoded type.

A template names an asset type and declares what a fresh asset inherits when the user selects
it at creation time. `vehicle` is the only MVP entry; adding a future template (e.g. a house)
is a new entry here plus its own default-row builder. The registry holds metadata only — no
SQLAlchemy, no row building — so it stays in the domain layer.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class AssetTemplate:
    """A selectable creation preset: its stored `asset.type` and whether it carries a vehicle profile."""

    key: str
    asset_type: str
    has_vehicle_profile: bool


VEHICLE_TEMPLATE = AssetTemplate(key="vehicle", asset_type="vehicle", has_vehicle_profile=True)

ASSET_TEMPLATES: dict[str, AssetTemplate] = {VEHICLE_TEMPLATE.key: VEHICLE_TEMPLATE}
