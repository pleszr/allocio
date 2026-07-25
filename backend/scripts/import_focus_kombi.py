"""One-off import of the 'Focus kombi 2025 -' sheet from PleszCsalad_costs.xlsx into Allocio.

Run once, from `backend/`, as a module so both `app.*` and this package resolve:

    cd backend && uv run python -m scripts.import_focus_kombi

Backdates the new asset's `created_at` directly in the DB (mirroring
`tests/conftest.py::backdate_asset_creation`) so the first check-in's period_start lands on the
real 2025-06-25 acquisition date, then replays the sheet's 14 real monthly check-ins in order
through the normal service layer so balances/maintenance timers reconstruct exactly like the
spreadsheet. Also replays the sheet's 'Extra safety' (AI) column as `manual_extra_monthly` and,
via `apply_pocket_overrides`, distributes each period's 'Kifizettük zsebből' (AJ) total across
that period's expense lines as a `paid_out_of_pocket_override` (see issue #95) -- filling lines in
submission order, the same way the bucket-depletion split itself works, since which specific line
absorbs how much doesn't matter for a check-in-level paid-out-of-pocket amount. A period with AJ
left over after its own lines are exhausted (including periods with no modeled/other expenses at
all) gets a synthetic 'other' expense for the remainder, so every AJ value is always fully
accounted for. Not part of the layered `app/` architecture and not wired into the code map; a
personal, run-once data migration kept for reference/re-run rather than a reusable import feature.
"""

import uuid
from dataclasses import dataclass, replace
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
    # The template default (`vehicle_defaults.py`) accrues vehicle_tax on a 6-month interval; this
    # asset's real súlyadó amounts are the full annual bill (confirmed against the sheet's own `AA`
    # rollover formula, which applies no x2/÷2 multiplier unlike its tire/inspection columns), so
    # override the interval to a full year to match.
    CostOverride("vehicle_tax", Decimal("9570"), interval_value=12, interval_unit="months"),
    CostOverride("motorway_vignette", Decimal("28000")),
    CostOverride("usage_based_reserve", Decimal("10")),
]

SourceMap = dict[str, tuple[str, uuid.UUID]]


@dataclass(frozen=True)
class Period:
    """One monthly check-in period from the sheet, including its AI/AJ columns for that row."""

    period_end: date
    usage_end: int
    tire: str | None
    expenses: list[ExpenseDraft]
    manual_extra_monthly: Decimal
    expected_paid_out_of_pocket: Decimal | None


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
        paid_out_of_pocket_override=None,
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
        paid_out_of_pocket_override=None,
    )


def build_periods(source_map: SourceMap) -> list[Period]:
    """Return the sheet's 14 real monthly check-in periods, columns B/C/D/AI/AJ mapped per row."""
    zero = Decimal(0)
    return [
        Period(
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
            zero,
            Decimal("531719"),
        ),
        Period(date(2025, 7, 1), 174900, None, [], zero, None),
        Period(date(2025, 8, 1), 176200, None, [], zero, None),
        Period(
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
            zero,
            Decimal("955118.20"),
        ),
        Period(date(2025, 10, 1), 178132, None, [], zero, None),
        Period(date(2025, 11, 1), 178551, None, [], zero, None),
        Period(
            date(2025, 12, 1),
            179254,
            "winter",
            [modeled("winter_tires", "248000", source_map, date(2025, 12, 1), 179254)],
            zero,
            Decimal("139758"),
        ),
        Period(
            date(2026, 1, 1),
            180300,
            None,
            [modeled("battery", "62900", source_map, date(2026, 1, 1), 180300)],
            Decimal("15000"),
            Decimal("62900"),
        ),
        Period(
            date(2026, 2, 1),
            181085,
            None,
            [
                other("34000", "Imported from spreadsheet: uncategorized 'egyéb' cost, Feb 2026", date(2026, 2, 1), 181085),
                modeled("motorway_vignette", "36570", source_map, date(2026, 2, 1), 181085),
            ],
            Decimal("15000"),
            None,
        ),
        Period(date(2026, 3, 1), 181700, None, [], Decimal("10000"), None),
        Period(date(2026, 4, 1), 182686, None, [], Decimal("15000"), None),
        Period(
            date(2026, 5, 1),
            183725,
            "summer",
            [
                modeled("seasonal_tire_change", "17000", source_map, date(2026, 5, 1), 183725),
                modeled("vehicle_tax", "38290", source_map, date(2026, 5, 1), 183725),
            ],
            Decimal("15000"),
            None,
        ),
        Period(date(2026, 6, 1), 184640, None, [], Decimal("15000"), None),
        Period(
            date(2026, 7, 1),
            185652,
            None,
            [
                modeled("mandatory_liability_insurance", "112021", source_map, date(2026, 7, 1), 185652),
                modeled("comprehensive_insurance", "216243", source_map, date(2026, 7, 1), 185652),
            ],
            Decimal("15000"),
            Decimal("74979.33"),
        ),
    ]


def apply_pocket_overrides(period: Period) -> Period:
    """Distribute the period's sheet-derived paid-out-of-pocket total across its expense lines.

    Which specific line absorbs how much doesn't matter -- paid-out-of-pocket is a check-in-level
    concept -- so this fills lines in submission order, the same way the bucket-depletion split
    itself works. Any amount left over once every line is fully covered (including a period with no
    modeled/other expenses at all) becomes a new synthetic 'other' expense, so the sheet's AJ total
    is always fully accounted for rather than silently dropped.
    """
    if period.expected_paid_out_of_pocket is None:
        return period
    remaining = period.expected_paid_out_of_pocket
    updated: list[ExpenseDraft] = []
    for draft in period.expenses:
        if remaining > 0:
            override = min(remaining, draft.amount)
            draft = replace(draft, paid_out_of_pocket_override=override)
            remaining -= override
        updated.append(draft)
    if remaining > 0:
        leftover = other(
            str(remaining),
            "Imported from spreadsheet: untracked cash outlay (AJ column, no matching expense line)",
            period.period_end,
            period.usage_end,
        )
        updated.append(replace(leftover, paid_out_of_pocket_override=remaining))
    return replace(period, expenses=updated)


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
    """Create the backdated vehicle asset, then replay its 14 real monthly check-ins in order."""
    session = SessionLocal()
    try:
        owner = session.query(User).filter_by(email=OWNER_EMAIL).one()
        asset_service = AssetService(session)

        created = asset_service.create_asset(
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

        for period in build_periods(source_map):
            period = apply_pocket_overrides(period)
            asset_service.update_manual_extra_monthly(owner.id, asset_id, period.manual_extra_monthly)
            check_in, allocations, expense_events = check_in_service.post_check_in(
                user_id=owner.id,
                asset_id=asset_id,
                period_end=period.period_end,
                usage_end=period.usage_end,
                active_tire_type=period.tire,
                expenses=period.expenses,
                notes="Imported from PleszCsalad_costs.xlsx",
            )
            print(
                f"Posted check-in {check_in.id} through {period.period_end.isoformat()} "
                f"(usage_end={period.usage_end}, manual_extra={period.manual_extra_monthly}, "
                f"{len(allocations)} allocations, {len(expense_events)} expenses)"
            )
            _verify_paid_out_of_pocket(period, expense_events)

        print(f"\nDone. Asset id: {asset_id}")
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def _verify_paid_out_of_pocket(period: Period, expense_events) -> None:  # noqa: ANN001 - list[ExpenseEvent], kept loose
    """Confirm the posted paid_out_of_pocket total for this period matches the sheet's AJ value.

    `apply_pocket_overrides` distributes AJ across the period's expense lines (via
    `paid_out_of_pocket_override`, issue #95) before posting, so this should always match; a mismatch
    means the distribution or a modeled amount is wrong, not that the app can't represent it.
    """
    if period.expected_paid_out_of_pocket is None:
        return
    actual = sum((event.paid_out_of_pocket for event in expense_events), Decimal(0))
    if actual == period.expected_paid_out_of_pocket:
        print(f"  paid_out_of_pocket OK: {actual} matches sheet AJ")
    else:
        print(
            f"  WARNING: paid_out_of_pocket mismatch for {period.period_end.isoformat()}: "
            f"app computed {actual}, sheet AJ was {period.expected_paid_out_of_pocket}"
        )


if __name__ == "__main__":
    main()
