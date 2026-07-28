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
accounted for.

Every one of the 14 periods, including September 2025's post-purchase catch-up service visit
(front brake disc, front/rear brake pads, annual service, transmission fluid, fuel filter, water
pump, timing system, plus an uncategorized 'egyéb' amount -- read straight from the sheet's own
H9:U9 row, 1,140,002 Ft total, 1,055,118.20 Ft of it paid out of pocket per the AJ9 formula), is now
posted as a real expense. This overrides an earlier version of this script that deliberately left
September unposted (see PRs #100/#106) on the reasoning that a one-time post-purchase backlog
shouldn't skew Allocio's future-cost accrual signals; Roland's explicit direction now is to treat
his own spreadsheet's real cash ledger as the source of truth for every check-in's expenses and
paid-out-of-pocket total, so `_verify_expenses`/`_verify_paid_out_of_pocket` below assert an exact
match against the sheet's 'summa kiadás' (AH) and 'Kifizettük zsebből' (AJ) columns for every
period where the app's own bucket genuinely has that much money in it (13 of the 14 -- see the July
2026 period below for the one documented, reconciled exception).

The sheet's September AJ9 figure was originally 955,118.20 -- Roland later found and fixed a bug in
its own `AK` running-bucket-balance formula (`=SUM(AE:AF)-SUM(...)-AJ+AI`): every row's `AK` summed
`J:U`, which skips `H`/`I` (the front/rear brake-disc columns), so the front-brake-disc replacement
was counted in the total expense (`AH`) but silently excluded from the sheet's own running
bucket-balance tracker (`AN`). September was the only one of the 14 real rows with a nonzero `H`
value, so it was the only row the bug actually affected. Fixing the formula to `SUM(H:U)` moved
AJ9 to -1,055,118.20 (a clean +100,000 correction), which now sits only ~1,000 Ft above the app's
own honestly-reconstructed bucket floor for that period -- within the day-count residual below,
not a new gap.

Reinstating September also makes the old `apply_maintenance_baselines` seeding step (previously
needed to backfill affected maintenance items' service baselines without a posting expense to
trigger the normal reset) fully redundant: every item that step used to seed by hand -- including
`front_brake_disc`, previously assumed to predate this sheet's tracked history -- turns out to have
its own real cost on the September row (H9 = 100,000 Ft), so the normal check-in-linked-expense
reset (`CheckInService._reset_maintenance_baselines`) now derives every one of those baselines from
a real posted expense instead. That whole seeding step has been removed.

Reconciling the sheet's 'summa utalás' (AG = 'utalandó éves ktg' AE + 'utalandó 10 ft/km' AF, i.e.
the sheet's own recommended-transfer-this-period figure) against the app's own computed allocation
total was investigated and found NOT achievable through `COST_OVERRIDES` tuning: it's a structural
mismatch between the sheet's Excel formulas and this app's accrual engine
(`app/domain/calculator.py`), not a wrong cost-line amount or interval, so it is deliberately left
unreconciled here (per Roland: out of scope for this script). The usage-based leg (AF) always
matches exactly -- both sides compute `usage_amount * amount_per_unit` identically. The time-based
leg (AE) does not, for two independent, structural reasons:

- Day-count convention: AE's formula is `YEARFRAC(period_end, period_start)` with Excel's default
  basis 0 (US 30/360), which for two first-of-month dates always evaluates to exactly `1/12`
  regardless of whether the real month has 28, 30, or 31 days. `time_based_period_accrual`
  (`calculator.py`) instead spreads the annualized amount over *actual* elapsed calendar days via
  `annualized/365 * elapsed_days`. No single `COST_OVERRIDES` amount can satisfy both a
  day-count-independent target and a days-proportional formula across periods of different
  lengths at once -- it's mathematically over-determined, not a tuning gap.
- Rollover timing: the sheet applies a new real-world price (the Feb 2026 motorway vignette bump,
  the May 2026 tire/tax bump, the Jul 2026 insurance bump) to the *same* row/period it changes in.
  `reference_amount()` (`calculator.py`) only applies a newly-logged modeled expense starting the
  *next* period whose `period_start` is on/after that expense's `event_date` -- by design
  (`docs/vehicle-rules.md`, "Time-Based Accrual") -- because `check_in_service._compute` only ever
  sees *already-posted* expenses, never the ones submitted with the same check-in being computed.

Measured deltas (app's computed time-based accrual minus the sheet's AE, HUF, at the
`COST_OVERRIDES` below, which already match the sheet's real June 2025 starting prices exactly):
Jul25 -76.71, Aug25 +536.94, Sep25 +536.94, Oct25 -383.52, Nov25 +536.94, Dec25 -383.52,
Jan26 +536.94, Feb26 -177.23, Mar26 -2,281.19, Apr26 +550.64, May26 -3,119.98, Jun26 +602.93,
Jul26 -7,148.67. Fixing this would mean changing the core accrual formula in
`app/domain/calculator.py`/`check_in_calc.py`, which affects every vehicle asset in the app, not
just this one, and is a deliberate, documented product decision, not a bug in this import -- so
this script reports the finding here rather than gating on it.

Because the bucket balance carries forward from one period to the next, these per-period deltas
accumulate: by July 2026 (the last of the 14 periods) the app's bucket has ~10,269 Ft less in it
than the sheet's own running balance (`AN`) would imply, plus a further ~55 Ft from
`manual_extra_monthly` being day-prorated in the app but applied as a flat monthly add-on in the
sheet's `AI` column. That is the entire cause of the one paid-out-of-pocket mismatch this script
still reports (see the comment on the July 2026 `Period` below) -- verified cell-for-cell against
the sheet, not assumed.

Not part of the layered `app/` architecture and not wired into the code map; a personal, run-once
data migration kept for reference/re-run rather than a reusable import feature.
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
    """One monthly check-in period from the sheet, including its AH/AI/AJ columns for that row."""

    period_end: date
    usage_end: int
    tire: str | None
    expenses: list[ExpenseDraft]
    manual_extra_monthly: Decimal
    expected_expense_total: Decimal
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
    """Return the sheet's 14 real monthly check-in periods, columns B/C/D/AH/AI/AJ mapped per row."""
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
            Decimal("531719"),
        ),
        Period(date(2025, 7, 1), 174900, None, [], zero, Decimal("0"), None),
        Period(date(2025, 8, 1), 176200, None, [], zero, Decimal("0"), None),
        Period(
            date(2025, 9, 1),
            176829,
            None,
            [
                # Post-purchase catch-up service visit; every line here is read straight from the
                # sheet's own H9:U9 row (front brake disc through 'egyéb'), summing to AH9's
                # 1,140,002 Ft exactly. `rear_brake_disc` (I9) is blank in the sheet -- no cost, no
                # line posted for it.
                modeled("front_brake_disc", "100000", source_map, date(2025, 9, 1), 176829),
                modeled("front_brake_pad", "50000", source_map, date(2025, 9, 1), 176829),
                modeled("rear_brake_pad", "1", source_map, date(2025, 9, 1), 176829),
                modeled("annual_service", "60000", source_map, date(2025, 9, 1), 176829),
                modeled("automatic_transmission_fluid", "140000", source_map, date(2025, 9, 1), 176829),
                modeled("fuel_filter", "40000", source_map, date(2025, 9, 1), 176829),
                modeled("water_pump", "1", source_map, date(2025, 9, 1), 176829),
                modeled("timing_system", "250000", source_map, date(2025, 9, 1), 176829),
                other(
                    "500000", "Imported from spreadsheet: uncategorized 'egyéb' cost, Sep 2025", date(2025, 9, 1), 176829
                ),
            ],
            zero,
            Decimal("1140002"),
            Decimal("1055118.20"),
        ),
        Period(date(2025, 10, 1), 178132, None, [], zero, Decimal("0"), None),
        Period(date(2025, 11, 1), 178551, None, [], zero, Decimal("0"), None),
        Period(
            date(2025, 12, 1),
            179254,
            "winter",
            [modeled("winter_tires", "248000", source_map, date(2025, 12, 1), 179254)],
            zero,
            Decimal("248000"),
            Decimal("139758"),
        ),
        Period(
            date(2026, 1, 1),
            180300,
            None,
            [modeled("battery", "62900", source_map, date(2026, 1, 1), 180300)],
            Decimal("15000"),
            Decimal("62900"),
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
            Decimal("70570"),
            None,
        ),
        Period(date(2026, 3, 1), 181700, None, [], Decimal("10000"), Decimal("0"), None),
        Period(date(2026, 4, 1), 182686, None, [], Decimal("15000"), Decimal("0"), None),
        Period(
            date(2026, 5, 1),
            183725,
            "summer",
            [
                modeled("seasonal_tire_change", "17000", source_map, date(2026, 5, 1), 183725),
                modeled("vehicle_tax", "38290", source_map, date(2026, 5, 1), 183725),
            ],
            Decimal("15000"),
            Decimal("55290"),
            None,
        ),
        Period(date(2026, 6, 1), 184640, None, [], Decimal("15000"), Decimal("0"), None),
        # This period's paid_out_of_pocket target (74979.33) is the one known, reconciled exception
        # to an exact match: verified cell-for-cell against the sheet (AN18=190,008.50 running
        # balance + AG19=48,276.17 this-period accrual + AI19=15,000 extra safety -> AH19(328,264) -
        # that = 74,979.33, matching AJ19 to the cent, so the sheet's own figure is internally
        # consistent, not a bug). The app's own bucket at this point has only 242,960.37 available
        # (10,324.30 Ft less), which is the cumulative sum of the per-period day-count/rollover
        # accrual deltas documented in the module docstring across all 13 prior periods (~10,269 Ft),
        # plus a small extra effect from `manual_extra_monthly` being day-prorated here
        # (`_manual_extra_line`) versus applied as a flat, unprorated monthly add-on in the sheet's
        # `AI` column. `resolve_paid_out_of_pocket` can only raise paid_out_of_pocket above this
        # bucket-shortfall floor, never lower it, so the override below cannot close this gap;
        # `_verify_paid_out_of_pocket` reports it as a FAIL rather than a forced match.
        Period(
            date(2026, 7, 1),
            185652,
            None,
            [
                modeled("mandatory_liability_insurance", "112021", source_map, date(2026, 7, 1), 185652),
                modeled("comprehensive_insurance", "216243", source_map, date(2026, 7, 1), 185652),
            ],
            Decimal("15000"),
            Decimal("328264"),
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

        results: list[tuple[str, bool, bool]] = []
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
            expenses_ok = _verify_expenses(period, expense_events)
            pocket_ok = _verify_paid_out_of_pocket(period, expense_events)
            results.append((period.period_end.isoformat(), expenses_ok, pocket_ok))

        print(f"\nDone. Asset id: {asset_id}")
        _print_summary(results)
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def _verify_expenses(period: Period, expense_events) -> bool:  # noqa: ANN001 - list[ExpenseEvent], kept loose
    """Confirm the posted expense total for this period matches the sheet's AH ('summa kiadás') value."""
    actual = sum((event.amount for event in expense_events), Decimal(0))
    if actual == period.expected_expense_total:
        print(f"  expenses OK: {actual} matches sheet AH")
        return True
    print(
        f"  WARNING: expenses mismatch for {period.period_end.isoformat()}: "
        f"app posted {actual}, sheet AH was {period.expected_expense_total}"
    )
    return False


def _verify_paid_out_of_pocket(period: Period, expense_events) -> bool:  # noqa: ANN001 - list[ExpenseEvent], kept loose
    """Confirm the posted paid_out_of_pocket total for this period matches the sheet's AJ value.

    `apply_pocket_overrides` distributes AJ across the period's expense lines (via
    `paid_out_of_pocket_override`, issue #95) before posting, so this should always match; a mismatch
    means the distribution or a modeled amount is wrong, not that the app can't represent it. A period
    where the sheet itself leaves AJ blank has no target to check against -- the natural
    bucket-shortfall split stands uncontested, so it counts as a pass.
    """
    if period.expected_paid_out_of_pocket is None:
        print("  paid_out_of_pocket: no sheet AJ target for this period (natural split stands)")
        return True
    actual = sum((event.paid_out_of_pocket for event in expense_events), Decimal(0))
    if actual == period.expected_paid_out_of_pocket:
        print(f"  paid_out_of_pocket OK: {actual} matches sheet AJ")
        return True
    print(
        f"  WARNING: paid_out_of_pocket mismatch for {period.period_end.isoformat()}: "
        f"app computed {actual}, sheet AJ was {period.expected_paid_out_of_pocket}"
    )
    return False


def _print_summary(results: list[tuple[str, bool, bool]]) -> None:
    """Print a compact PASS/FAIL table for every period's expenses/paid-out-of-pocket reconciliation."""
    print("\nperiod_end   expenses  paid_out_of_pocket")
    for period_end, expenses_ok, pocket_ok in results:
        print(f"{period_end}   {'PASS' if expenses_ok else 'FAIL':8}  {'PASS' if pocket_ok else 'FAIL'}")
    if all(expenses_ok and pocket_ok for _, expenses_ok, pocket_ok in results):
        print("\nAll periods PASS on expenses and paid-out-of-pocket.")
    else:
        print("\nSome periods FAILED -- see WARNING lines above.")


if __name__ == "__main__":
    main()
