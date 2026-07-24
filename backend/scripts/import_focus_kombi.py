"""One-off import of the 'Focus kombi 2025 -' sheet from PleszCsalad_costs.xlsx into Allocio.

Run once, from `backend/`, as a module so both `app.*` and this package resolve:

    cd backend && uv run python -m scripts.import_focus_kombi

Backdates the new asset's `created_at` directly in the DB (mirroring
`tests/conftest.py::backdate_asset_creation`) so the first check-in's period_start lands on the
real 2025-06-25 acquisition date, then replays the sheet's 12 real monthly check-ins in order
through the normal service layer so balances/maintenance timers reconstruct exactly like the
spreadsheet. Not part of the layered `app/` architecture and not wired into the code map; a
personal, run-once data migration kept for reference/re-run rather than a reusable import feature.
"""

import uuid
from datetime import date, datetime, timezone
from decimal import Decimal

from app.db import SessionLocal
from app.domain.user import User
from app.domain.vehicle_defaults import vehicle_catalog_keys
from app.services.asset_service import AssetService, CostOverride, VehicleDetails
from app.services.check_in_service import CheckInService, ExpenseDraft

OWNER_EMAIL = "plesz.roland@gmail.com"
ASSET_NAME = "Focus Kombi"
STARTING_ODOMETER = 174500
ACQUISITION_DATE = date(2025, 6, 25)

COST_OVERRIDES = [
    CostOverride("seasonal_tire_change", Decimal("15000")),
    CostOverride("vehicle_inspection", Decimal("41500")),
    CostOverride("mandatory_liability_insurance", Decimal("53000")),
    CostOverride("comprehensive_insurance", Decimal("194648")),
    CostOverride("vehicle_tax", Decimal("9570")),
    CostOverride("motorway_vignette", Decimal("28000")),
    CostOverride("usage_based_reserve", Decimal("10")),
]

SourceMap = dict[str, tuple[str, uuid.UUID]]


def modeled(technical_key: str, amount: str, source_map: SourceMap, event_date: date, usage_km: int) -> ExpenseDraft:
    """Build a 'modeled' expense draft linked to a cost/maintenance row by its technical_key."""
    source_type, source_id = source_map[technical_key]
    return ExpenseDraft(
        kind="modeled",
        amount=Decimal(amount),
        event_date=event_date,
        usage_counter_at_event=usage_km,
        comment=None,
        source_type=source_type,
        source_id=source_id,
    )


def other(amount: str, comment: str, event_date: date, usage_km: int) -> ExpenseDraft:
    """Build an 'other' (uncategorized, no source) expense draft."""
    return ExpenseDraft(
        kind="other",
        amount=Decimal(amount),
        event_date=event_date,
        usage_counter_at_event=usage_km,
        comment=comment,
        source_type=None,
        source_id=None,
    )


def build_periods(source_map: SourceMap) -> list[tuple[date, int, str | None, list[ExpenseDraft]]]:
    """Return the sheet's 12 real monthly check-in periods, each as (period_end, usage_end, tire, expenses)."""
    return [
        (
            date(2025, 6, 25),
            174500,
            "summer",
            [
                modeled("mandatory_liability_insurance", "53000", source_map, date(2025, 6, 25), 174500),
                modeled("comprehensive_insurance", "194648", source_map, date(2025, 6, 25), 174500),
                modeled("vehicle_tax", "9570", source_map, date(2025, 6, 25), 174500),
                modeled("motorway_vignette", "28000", source_map, date(2025, 6, 25), 174500),
                modeled("vehicle_inspection", "41500", source_map, date(2025, 6, 25), 174500),
                modeled("seasonal_tire_change", "15000", source_map, date(2025, 6, 25), 174500),
                modeled("summer_tires", "190000", source_map, date(2025, 6, 25), 174500),
                modeled("battery", "1", source_map, date(2025, 6, 25), 174500),
            ],
        ),
        (date(2025, 7, 1), 174900, None, []),
        (date(2025, 8, 1), 176200, None, []),
        (
            date(2025, 9, 1),
            176829,
            None,
            [
                modeled("front_brake_disc", "100000", source_map, date(2025, 9, 1), 176829),
                modeled("front_brake_pad", "50000", source_map, date(2025, 9, 1), 176829),
                modeled("rear_brake_pad", "1", source_map, date(2025, 9, 1), 176829),
                modeled("annual_service", "60000", source_map, date(2025, 9, 1), 176829),
                modeled("automatic_transmission_fluid", "140000", source_map, date(2025, 9, 1), 176829),
                modeled("fuel_filter", "40000", source_map, date(2025, 9, 1), 176829),
                modeled("water_pump", "1", source_map, date(2025, 9, 1), 176829),
                modeled("timing_system", "250000", source_map, date(2025, 9, 1), 176829),
                other(
                    "500000",
                    "Imported from spreadsheet: uncategorized 'egyéb' cost, Sept 2025 service visit",
                    date(2025, 9, 1),
                    176829,
                ),
            ],
        ),
        (date(2025, 10, 1), 178132, None, []),
        (date(2025, 11, 1), 178551, None, []),
        (
            date(2025, 12, 1),
            179254,
            "winter",
            [modeled("winter_tires", "248000", source_map, date(2025, 12, 1), 179254)],
        ),
        (
            date(2026, 1, 1),
            180300,
            None,
            [modeled("battery", "62900", source_map, date(2026, 1, 1), 180300)],
        ),
        (
            date(2026, 2, 1),
            181085,
            None,
            [
                other("34000", "Imported from spreadsheet: uncategorized 'egyéb' cost, Feb 2026", date(2026, 2, 1), 181085),
                modeled("motorway_vignette", "36570", source_map, date(2026, 2, 1), 181085),
            ],
        ),
        (date(2026, 3, 1), 181700, None, []),
        (date(2026, 4, 1), 182686, None, []),
        (
            date(2026, 5, 1),
            183725,
            "summer",
            [
                modeled("seasonal_tire_change", "17000", source_map, date(2026, 5, 1), 183725),
                modeled("vehicle_tax", "38290", source_map, date(2026, 5, 1), 183725),
            ],
        ),
    ]


def build_source_map(created) -> SourceMap:  # noqa: ANN001 - CreatedAsset from asset_service, kept loosely typed here
    """Map each cloned template row's technical_key to its (source_type, id) for expense linking."""
    source_map: SourceMap = {}
    for row in created.time_based_costs:
        if row.technical_key:
            source_map[row.technical_key] = ("time_based_cost", row.id)
    for row in created.usage_based_costs:
        if row.technical_key:
            source_map[row.technical_key] = ("usage_based_cost", row.id)
    for row in created.maintenance_items:
        if row.technical_key:
            source_map[row.technical_key] = ("maintenance_item", row.id)
    return source_map


def main() -> None:
    """Create the backdated vehicle asset, then replay its 12 real monthly check-ins in order."""
    session = SessionLocal()
    try:
        owner = session.query(User).filter_by(email=OWNER_EMAIL).one()

        created = AssetService(session).create_asset(
            user_id=owner.id,
            name=ASSET_NAME,
            asset_type=None,
            template_key="vehicle",
            vehicle_details=VehicleDetails(starting_odometer=STARTING_ODOMETER),
            selected_cost_keys=list(vehicle_catalog_keys()),
            cost_overrides=COST_OVERRIDES,
        )
        asset_id = created.asset.id
        print(f"Created asset {asset_id} ({ASSET_NAME})")

        created.asset.created_at = datetime.combine(ACQUISITION_DATE, datetime.min.time(), tzinfo=timezone.utc)
        session.flush()
        session.commit()
        print(f"Backdated created_at to {ACQUISITION_DATE.isoformat()}")

        source_map = build_source_map(created)
        check_in_service = CheckInService(session)

        for period_end, usage_end, tire, expenses in build_periods(source_map):
            check_in, allocations, expense_events = check_in_service.post_check_in(
                user_id=owner.id,
                asset_id=asset_id,
                period_end=period_end,
                usage_end=usage_end,
                active_tire_type=tire,
                expenses=expenses,
                notes="Imported from PleszCsalad_costs.xlsx",
            )
            print(
                f"Posted check-in {check_in.id} through {period_end.isoformat()} "
                f"(usage_end={usage_end}, {len(allocations)} allocations, {len(expense_events)} expenses)"
            )

        print(f"\nDone. Asset id: {asset_id}")
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


if __name__ == "__main__":
    main()
