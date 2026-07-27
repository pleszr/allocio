"""One-off import of the '17) Focus 2018-' sheet from PleszCsalad_costs.xlsx into Allocio.

Run once, from `backend/`, as a module so both `app.*` and this package resolve:

    cd backend && uv run python -m scripts.import_focus_2018

Backdates the new asset's `created_at` directly in the DB (mirroring
`tests/conftest.py::backdate_asset_creation` and `import_focus_kombi.py`) so the first check-in's
period_start lands on 2018-08-22 (sheet row 6, starting odometer 242429), then replays the
remaining 98 real rows through 2026-07-01 as check-ins in chronological order, irregularly spaced
exactly as recorded (not monthly -- unlike `import_focus_kombi.py`, whose 14 rows happened to all
be ~monthly). Also replays the sheet's 'Extra safety' (AJ) column as `manual_extra_monthly`
(resetting to 0 on every row that leaves AJ blank -- confirmed against the sheet's own `AL`/`AO`
formulas, which treat a blank AJ as exactly 0, not "same as the last non-blank value") and, via
`apply_pocket_overrides`, distributes each period's 'Kifizettuk zsebbol' (AK) total across that
period's expense lines as a `paid_out_of_pocket_override` (see issue #95), the same way
`import_focus_kombi.py` does.

Rows 3-5 (2015-02-20, 2016-01-20, 2018-05-11) are deliberately NOT replayed as check-ins. A
post-import balance investigation found the app's posted balance overshot the sheet's own
cumulative ground truth (`AO103`, `=SUM(AL$6:AL103)`) by ~1.01M Ft, of which ~925k Ft (91%) traced
to exactly these three rows: the sheet's own `AF`/`AG`/`AL` formulas are completely blank for
rows 3-5 (no formula at all, not just excluded from a sum) and `AO`'s cumulative sum explicitly
starts at row 6 -- i.e. the sheet's own model never accrues anything before 2018-08-22, treating
2015-2018 as pure pre-tracking odometer history. Posting them as real check-ins made the app
accrue ~3.3 years of time-based and usage-based savings (mostly usage-based reserve, driven by the
50,273 km gap across those sparse rows) that the sheet's own ground truth never counted. Roland
confirmed: match the sheet, no accrual before 2018-08-22. All three rows have zero real values in
every H:AC cost column (confirmed by re-reading the sheet fresh), so nothing needs preserving as a
maintenance baseline or otherwise -- they are simply dropped.

A remaining ~78,620 Ft residual (the app's time-based accrual still runs slightly higher than the
sheet's `AF` column across the real 2018-08-22 to 2026-07-01 window, plus a small ~-18,440 Ft
usage-based quirk at the very first real row where the sheet's own `AG6`/`AH6` cells don't follow
its usual formula pattern) was investigated but not chased further -- same accepted-residual
treatment as `import_focus_kombi.py`'s day-count/rollover gap. The `vehicle_tax` 12-month interval
override (see COST_OVERRIDES) was specifically checked as a candidate cause and ruled out: a
counterfactual simulation against the real posted `vehicle_tax` expense history shows it *reduces*
total accrual by ~41,441 Ft relative to the original 6-month/2800 baseline, so it is not a
contributor to this residual.

Structural differences from the kombi sheet (same underlying logic, different real columns -- see
the requesting task for the full column-by-column diff):

- This sheet has single combined 'féktárcsa' (brake disc) and 'fékbetét' (brake pad) columns
  instead of kombi's separate front/rear columns, and in fact NEITHER combined column ever carries
  a real value across all 101 rows (H is always empty; I has exactly one real value, at
  2020-01-01). The sheet's own parallel 'csere/cserélendő km/hónap' forecast table (AP-AU) lists
  TWO forecast rows each for féktárcsa and fékbetét, one matching this app's stock front/rear
  defaults exactly and one carrying a custom (shorter) interval -- inferred here as front (custom,
  faster wear) vs. rear (matches app defaults) since the forecast table itself does not label
  which is which. Roland confirmed this inferred front/rear assignment. See
  MAINTENANCE_BASELINE_RESETS.
- This sheet has granular 'olaj' (oil) / 'olajszűrő' (oil filter) / 'levegőszűrő' (air filter) /
  'pollenszűrő' (cabin filter) columns instead of kombi's single 'éves szervíz' column. None of
  the four has its own Allocio maintenance-item technical_key, so each row's non-null subset of
  the four is summed and posted as one modeled `annual_service` expense -- the closest existing
  catalog concept to "the bundled oil-change visit" -- same technical_key kombi's own 'éves
  szervíz' column maps to.
- 'ékszíj' (serpentine belt) and 'hosszbordás szíj' (ribbed belt) are tracked in the sheet's own
  forecast table (both last replaced 2015-02-20, i.e. at the sheet's own tracking start) but have
  no matching Allocio maintenance-item technical_key at all today, and never carry a real cost
  value in any of the 101 rows either. They are simply not representable in this import; flagged
  for Roland rather than invented.
- 'lopás casco' (theft casco) + 'parkolás casco' (parking casco) are two separate columns here,
  vs. kombi's single 'casco' plus its own 'parkolás casco'. They co-occur exactly once (2018-08-22,
  8000 + 3650 = 11650), which is exactly this app's `comprehensive_insurance` template default --
  strong evidence the two columns together represent one comprehensive-insurance premium, so they
  are summed into one modeled `comprehensive_insurance` expense. Roland confirmed this mapping.
- 'súlyadó x2' genuinely was paid semi-annually in its cleanest stretch (2019-2020: two equal
  7590 Ft payments exactly 6 months apart), unlike kombi's own 'súlyadó' column (already a full
  annual bill). Per Roland's decision, the override interval is still annual here -- matching
  kombi's own vehicle_tax treatment -- with the baseline amount recalculated to a real annual total
  (15180, the summed 2019-2020 matched pair) rather than reused from a single half-year cell. The
  individual historical `modeled("vehicle_tax", ...)` amounts are left as their real transcribed
  values, not doubled; see the COST_OVERRIDES comment for the full reasoning and its one accepted
  accrual-accuracy trade-off.
- Two rows (2023-06-01, 2024-03-01) record all four oil/filter columns as a flat "1" (Ft), clearly
  a placeholder/marker rather than a real amount. Posted literally as a 4 HUF modeled expense
  rather than invented or dropped, since 4 HUF is financially immaterial but still correctly resets
  the annual_service due-date clock from the real visit date. A near-zero (~5e-08) floating-point
  artifact in the tire-cost columns at 2018-08-22 is treated as exactly zero and skipped instead,
  since it is Excel formula noise rather than a deliberate entry.
- The AK ('Kifizettuk zsebbol') column was corrected by Roland after the first import: the sheet
  originally had one negative cell (2024-02-01, -23247 Ft) that did not fit the paid-out-of-pocket
  model (`apply_pocket_overrides` assumes a non-negative amount to distribute across that period's
  expense lines). Roland's correction removed that cell (now blank) and also revised several other
  AK values across the sheet (2020-01-01, 2020-02-01 newly populated; 2020-09-01, 2021-01-01,
  2021-02-01, 2024-07-01, 2025-09-01 cleared to blank; 2025-03-01 and 2026-03-01 changed to new
  amounts). `build_periods` reflects the corrected column exactly; no other column changed in the
  re-read sheet (verified by a full fresh re-dump and diff against the original, not assumed).

MAINTENANCE_BASELINE_RESETS covers the maintenance items that never receive a real posted expense
anywhere in the 101 rows (front_brake_disc, rear_brake_disc, rear_brake_pad) using the sheet's own
forecast table as the source of truth for last-serviced date/odometer, plus a same-call interval
override for the two items (front_brake_disc, front_brake_pad) whose forecast-table interval
differs from this app's stock default. Unlike kombi's baseline resets (all pre-2015, seeding a
catch-up visit this import deliberately excludes as an expense), all of these dates fall within the
sheet's own 101-row range; they are seeded here because the forecast table is `otherwise
inferable` evidence of the true last-serviced point in the absence of any linked expense, exactly
as the task's own guidance permits.

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
from app.services.cost_service import CostService

OWNER_EMAIL = "plesz.roland@gmail.com"
ASSET_NAME = "White Focus"
# Row 6 (2018-08-22) -- the sheet's own accrual/tracking start, not the sheet's earliest row
# (2015-02-20). See the module docstring for why rows 3-5 are dropped rather than replayed.
STARTING_ODOMETER = 242429
ACQUISITION_DATE = date(2018, 8, 22)
MANUFACTURE_YEAR = 2009

COST_OVERRIDES = [
    # Each amount is this asset's own first real observed value for that technical_key (same
    # convention import_focus_kombi.py uses), since ~3.3 real years (2015-02-20 to 2018-08-22) pass
    # before this sheet records any cost at all for most of these -- there is no earlier real data
    # to anchor the template default to, so the first known real value is the best available proxy
    # for what the asset should accrue toward during that gap.
    CostOverride("seasonal_tire_change", Decimal("7000")),
    CostOverride("vehicle_inspection", Decimal("29000")),
    CostOverride("mandatory_liability_insurance", Decimal("49355")),
    CostOverride("comprehensive_insurance", Decimal("11650")),
    # súlyadó x2 (vehicle_tax): the cleanest real evidence (2019-10-01 + 2020-04-01, two equal
    # 7590 Ft payments exactly 6 months apart) shows this was genuinely paid in two semi-annual
    # installments during 2019-2020, summing to a real annual total of 15180. Later payments
    # (2021 onward) space out irregularly (9-25 months apart) rather than staying strictly
    # semi-annual, closer to an annual cadence -- so, per Roland's decision, the override interval
    # is annual (matching import_focus_kombi.py's own vehicle_tax treatment) with 15180 as the
    # best real annual-equivalent baseline. The individual historical `modeled("vehicle_tax", ...)`
    # amounts in build_periods are deliberately left unchanged (not doubled) since each is a
    # genuine standalone cash payment faithfully transcribed from its own sheet row; doubling them
    # would fabricate amounts that were never actually paid on those dates. One accepted
    # consequence: `reference_amount()` always uses the latest linked expense, so during the
    # semi-annual era the live "recommended annual accrual" will read low right after a half-year
    # amount supersedes this baseline, until the next real vehicle_tax event corrects it -- an
    # unavoidable side effect of framing a genuinely-mixed-cadence cost as a 12-month interval.
    CostOverride("vehicle_tax", Decimal("15180"), interval_value=12, interval_unit="months"),
    CostOverride("motorway_vignette", Decimal("26400")),
    CostOverride("usage_based_reserve", Decimal("10")),
]

SourceMap = dict[str, tuple[str, uuid.UUID]]

# (technical_key, changes) for maintenance items that never receive a real posted expense anywhere
# in the 101 rows (front_brake_disc, rear_brake_disc, rear_brake_pad), seeded from the sheet's own
# 'csere/cserélendő km/hónap' forecast table (AP-AU), plus a same-call interval override for the
# two items (front_brake_disc, front_brake_pad) whose forecast-table interval differs from this
# app's stock default. front_brake_pad itself DOES receive a real posted expense (2020-01-01, see
# build_periods) so only its interval is overridden here; its last-serviced date/odometer come from
# that real expense through the normal check-in flow instead. See module docstring for the
# front/rear inference and why it is a guess, not a certainty.
MAINTENANCE_BASELINE_RESETS: list[tuple[str, dict[str, object]]] = [
    (
        "front_brake_disc",
        {
            "last_serviced_at_date": date(2016, 1, 20),
            "last_serviced_at_odometer": 215000,
            "interval_km": 80000,
            "interval_months": 60,
        },
    ),
    (
        "rear_brake_disc",
        {
            "last_serviced_at_date": date(2016, 1, 20),
            "last_serviced_at_odometer": 215000,
        },
    ),
    (
        "front_brake_pad",
        {
            "interval_km": 40000,
            "interval_months": 60,
        },
    ),
    (
        "rear_brake_pad",
        {
            "last_serviced_at_date": date(2020, 1, 1),
            "last_serviced_at_odometer": 262132,
        },
    ),
]


@dataclass(frozen=True)
class Period:
    """One check-in period from the sheet, including its AJ/AK columns for that row."""

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
    """Return the sheet's 98 real check-in periods (rows 6-103), columns B/C/D/AJ/AK mapped per row.

    Rows 3-5 (2015-02-20, 2016-01-20, 2018-05-11) are not included -- see module docstring.
    """
    zero = Decimal(0)
    return [
        # 2018-08-22: creation baseline, period_end == period_start. Row 6, the sheet's own
        # accrual/tracking start (see module docstring).
        Period(
            date(2018, 8, 22),
            242429,
            None,
            [
                modeled("mandatory_liability_insurance", "49355", source_map, date(2018, 8, 22), 242429),
                # lopás casco (8000) + parkolás casco (3650) combined -- see module docstring.
                modeled("comprehensive_insurance", "11650", source_map, date(2018, 8, 22), 242429),
            ],
            zero,
            None,
        ),
        Period(date(2018, 8, 23), 242442, "summer", [], zero, None),
        Period(date(2018, 9, 1), 243373, None, [], zero, None),
        Period(
            date(2018, 10, 1),
            244792,
            None,
            [other("6500", "Imported from spreadsheet: uncategorized 'egyéb' cost, Oct 2018", date(2018, 10, 1), 244792)],
            zero,
            None,
        ),
        Period(
            date(2018, 11, 4),
            246202,
            None,
            [
                modeled("annual_service", "9000", source_map, date(2018, 11, 4), 246202),
                other("11000", "Imported from spreadsheet: uncategorized 'egyéb' cost, Nov 2018", date(2018, 11, 4), 246202),
            ],
            zero,
            None,
        ),
        Period(
            date(2018, 12, 1),
            247890,
            "winter",
            [other("22500", "Imported from spreadsheet: uncategorized 'egyéb' cost, Dec 2018", date(2018, 12, 1), 247890)],
            zero,
            None,
        ),
        Period(
            date(2019, 1, 1),
            248523,
            None,
            [modeled("motorway_vignette", "26400", source_map, date(2019, 1, 1), 248523)],
            zero,
            None,
        ),
        Period(date(2019, 2, 1), 248786, None, [], zero, None),
        Period(date(2019, 3, 1), 249660, None, [], zero, None),
        Period(
            date(2019, 4, 1),
            249910,
            None,
            [modeled("vehicle_tax", "2800", source_map, date(2019, 4, 1), 249910)],
            zero,
            None,
        ),
        Period(
            date(2019, 4, 16),
            250121,
            None,
            [
                modeled("annual_service", "22050", source_map, date(2019, 4, 16), 250121),
                modeled("fuel_filter", "30850", source_map, date(2019, 4, 16), 250121),
            ],
            zero,
            None,
        ),
        Period(
            date(2019, 5, 1),
            250725,
            None,
            [modeled("seasonal_tire_change", "7000", source_map, date(2019, 5, 1), 250725)],
            zero,
            None,
        ),
        Period(date(2019, 6, 1), 251181, "summer", [], zero, None),
        Period(date(2019, 7, 1), 253691, None, [], zero, None),
        Period(
            date(2019, 8, 1),
            255253,
            None,
            [modeled("vehicle_inspection", "29000", source_map, date(2019, 8, 1), 255253)],
            zero,
            None,
        ),
        Period(
            date(2019, 9, 1),
            257523,
            None,
            [modeled("mandatory_liability_insurance", "51650", source_map, date(2019, 9, 1), 257523)],
            zero,
            None,
        ),
        Period(
            date(2019, 10, 1),
            258268,
            None,
            [modeled("vehicle_tax", "7590", source_map, date(2019, 10, 1), 258268)],
            zero,
            None,
        ),
        Period(date(2019, 11, 1), 259526, None, [], zero, None),
        Period(
            date(2019, 12, 1),
            261138,
            None,
            [
                modeled("all_season_tires", "80000", source_map, date(2019, 12, 1), 261138),
                modeled("seasonal_tire_change", "9000", source_map, date(2019, 12, 1), 261138),
            ],
            zero,
            None,
        ),
        Period(
            date(2020, 1, 1),
            262132,
            "all_season",
            [
                # The sheet's single 58000 Ft fékbetét (brake pad) payment; see
                # MAINTENANCE_BASELINE_RESETS for the same-date rear_brake_pad baseline seed this
                # doesn't itself post an expense for.
                modeled("front_brake_pad", "58000", source_map, date(2020, 1, 1), 262132),
                modeled("annual_service", "41600", source_map, date(2020, 1, 1), 262132),
                other("35000", "Imported from spreadsheet: uncategorized 'egyéb' cost, Jan 2020", date(2020, 1, 1), 262132),
            ],
            zero,
            Decimal("68000"),
        ),
        Period(
            date(2020, 2, 1),
            262792,
            None,
            [modeled("motorway_vignette", "44460", source_map, date(2020, 2, 1), 262792)],
            zero,
            Decimal("26128"),
        ),
        Period(date(2020, 3, 1), 263700, None, [], zero, None),
        Period(
            date(2020, 4, 1),
            264290,
            None,
            [modeled("vehicle_tax", "7590", source_map, date(2020, 4, 1), 264290)],
            zero,
            None,
        ),
        Period(date(2020, 5, 1), 264974, None, [], zero, None),
        Period(date(2020, 6, 1), 266430, None, [], zero, None),
        Period(date(2020, 7, 1), 268190, None, [], zero, None),
        Period(date(2020, 8, 1), 269438, None, [], zero, None),
        Period(
            date(2020, 9, 1),
            270601,
            None,
            [
                modeled("battery", "26000", source_map, date(2020, 9, 1), 270601),
                modeled("mandatory_liability_insurance", "67000", source_map, date(2020, 9, 1), 270601),
            ],
            zero,
            None,
        ),
        Period(date(2020, 10, 1), 271684, None, [], zero, None),
        Period(
            date(2020, 11, 1),
            273265,
            None,
            [
                modeled("annual_service", "39983", source_map, date(2020, 11, 1), 273265),
                other("84103", "Imported from spreadsheet: uncategorized 'egyéb' cost, Nov 2020", date(2020, 11, 1), 273265),
            ],
            zero,
            Decimal("20000"),
        ),
        Period(date(2020, 12, 1), 273730, None, [], zero, None),
        Period(date(2021, 1, 1), 274983, None, [], zero, None),
        Period(
            date(2021, 2, 1),
            275470,
            None,
            [modeled("motorway_vignette", "46000", source_map, date(2021, 2, 1), 275470)],
            zero,
            None,
        ),
        Period(date(2021, 3, 1), 276391, None, [], zero, None),
        Period(date(2021, 4, 1), 277043, None, [], zero, None),
        Period(date(2021, 5, 1), 277973, None, [], zero, None),
        Period(
            date(2021, 6, 1),
            278817,
            None,
            [modeled("vehicle_tax", "6100", source_map, date(2021, 6, 1), 278817)],
            zero,
            None,
        ),
        Period(date(2021, 7, 1), 280500, None, [], zero, None),
        Period(
            date(2021, 8, 1),
            281494,
            None,
            [
                modeled("annual_service", "49305", source_map, date(2021, 8, 1), 281494),
                modeled("vehicle_inspection", "41500", source_map, date(2021, 8, 1), 281494),
                modeled("mandatory_liability_insurance", "49900", source_map, date(2021, 8, 1), 281494),
            ],
            zero,
            None,
        ),
        Period(date(2021, 9, 1), 283455, None, [], zero, None),
        Period(date(2021, 10, 1), 285911, None, [], zero, None),
        Period(date(2021, 11, 1), 286414, None, [], zero, None),
        Period(date(2021, 12, 1), 288333, None, [], zero, None),
        Period(date(2022, 1, 1), 289475, None, [], zero, None),
        Period(
            date(2022, 2, 1),
            290504,
            None,
            [modeled("motorway_vignette", "48400", source_map, date(2022, 2, 1), 290504)],
            zero,
            None,
        ),
        Period(
            date(2022, 3, 1),
            291204,
            None,
            [modeled("vehicle_tax", "6500", source_map, date(2022, 3, 1), 291204)],
            zero,
            None,
        ),
        Period(
            date(2022, 4, 1),
            292202,
            None,
            [
                modeled("annual_service", "42000", source_map, date(2022, 4, 1), 292202),
                other("80000", "Imported from spreadsheet: uncategorized 'egyéb' cost, Apr 2022", date(2022, 4, 1), 292202),
            ],
            zero,
            None,
        ),
        Period(date(2022, 5, 1), 293314, None, [], zero, None),
        Period(date(2022, 6, 1), 294955, None, [], zero, None),
        Period(date(2022, 7, 1), 296523, None, [], zero, None),
        Period(date(2022, 8, 1), 299037, None, [], zero, None),
        Period(
            date(2022, 9, 1),
            301308,
            None,
            [modeled("mandatory_liability_insurance", "38640", source_map, date(2022, 9, 1), 301308)],
            zero,
            None,
        ),
        Period(date(2022, 10, 1), 302308, None, [], zero, None),
        Period(date(2022, 11, 1), 303660, None, [], zero, None),
        Period(
            date(2022, 12, 1),
            304860,
            None,
            [modeled("annual_service", "48000", source_map, date(2022, 12, 1), 304860)],
            zero,
            None,
        ),
        Period(
            date(2023, 1, 1),
            306479,
            None,
            [modeled("annual_service", "12000", source_map, date(2023, 1, 1), 306479)],
            zero,
            None,
        ),
        Period(
            date(2023, 2, 1),
            307252,
            None,
            [
                modeled("water_pump", "10000", source_map, date(2023, 2, 1), 307252),
                modeled("timing_system", "100000", source_map, date(2023, 2, 1), 307252),
                other("40000", "Imported from spreadsheet: uncategorized 'egyéb' cost, Feb 2023", date(2023, 2, 1), 307252),
                modeled("motorway_vignette", "50990", source_map, date(2023, 2, 1), 307252),
            ],
            zero,
            Decimal("10000"),
        ),
        Period(date(2023, 3, 1), 308802, None, [], zero, None),
        Period(date(2023, 4, 1), 310173, None, [], zero, None),
        Period(date(2023, 5, 1), 311451, None, [], zero, None),
        Period(
            date(2023, 6, 1),
            313667,
            None,
            # Flat "1" Ft placeholder across all four oil/filter columns -- see module docstring.
            [modeled("annual_service", "4", source_map, date(2023, 6, 1), 313667)],
            zero,
            None,
        ),
        Period(
            date(2023, 7, 1),
            314914,
            None,
            [modeled("mandatory_liability_insurance", "55396", source_map, date(2023, 7, 1), 314914)],
            zero,
            None,
        ),
        Period(date(2023, 8, 1), 317478, None, [], zero, None),
        Period(date(2023, 9, 1), 318999, None, [], zero, None),
        Period(date(2023, 10, 1), 319500, None, [], zero, None),
        Period(date(2023, 11, 1), 320959, None, [], zero, None),
        Period(date(2023, 12, 1), 322759, None, [], zero, None),
        Period(
            date(2024, 1, 1),
            324663,
            None,
            [modeled("motorway_vignette", "57260", source_map, date(2024, 1, 1), 324663)],
            zero,
            None,
        ),
        Period(
            date(2024, 2, 1),
            326243,
            None,
            [
                modeled("annual_service", "52000", source_map, date(2024, 2, 1), 326243),
                modeled("all_season_tires", "94000", source_map, date(2024, 2, 1), 326243),
                modeled("seasonal_tire_change", "14000", source_map, date(2024, 2, 1), 326243),
            ],
            zero,
            None,
        ),
        Period(
            date(2024, 3, 1),
            327779,
            None,
            [modeled("annual_service", "4", source_map, date(2024, 3, 1), 327779)],
            zero,
            None,
        ),
        Period(
            date(2024, 4, 1),
            328645,
            None,
            [modeled("vehicle_tax", "6100", source_map, date(2024, 4, 1), 328645)],
            zero,
            None,
        ),
        Period(date(2024, 5, 1), 330314, None, [], zero, None),
        Period(date(2024, 6, 1), 331257, None, [], zero, None),
        Period(
            date(2024, 7, 1),
            332590,
            None,
            [other("200000", "Imported from spreadsheet: uncategorized 'egyéb' cost, Jul 2024", date(2024, 7, 1), 332590)],
            zero,
            None,
        ),
        Period(date(2024, 8, 1), 334053, None, [], zero, None),
        Period(
            date(2024, 9, 1),
            335049,
            None,
            [modeled("mandatory_liability_insurance", "66000", source_map, date(2024, 9, 1), 335049)],
            zero,
            Decimal("12609"),
        ),
        Period(date(2024, 10, 1), 336027, None, [], zero, None),
        Period(date(2024, 11, 1), 336546, None, [], zero, None),
        Period(date(2024, 12, 1), 336900, None, [], zero, None),
        Period(date(2025, 1, 1), 337123, None, [], zero, None),
        Period(
            date(2025, 2, 1),
            337706,
            None,
            [modeled("motorway_vignette", "23000", source_map, date(2025, 2, 1), 337706)],
            zero,
            None,
        ),
        Period(
            date(2025, 3, 1),
            338006,
            None,
            [
                modeled("annual_service", "52004", source_map, date(2025, 3, 1), 338006),
                modeled("fuel_filter", "38571", source_map, date(2025, 3, 1), 338006),
                other("38500", "Imported from spreadsheet: uncategorized 'egyéb' cost, Mar 2025", date(2025, 3, 1), 338006),
            ],
            zero,
            Decimal("38300"),
        ),
        Period(date(2025, 4, 1), 338906, None, [], zero, None),
        Period(
            date(2025, 5, 1),
            339600,
            None,
            [modeled("vehicle_tax", "9570", source_map, date(2025, 5, 1), 339600)],
            zero,
            None,
        ),
        Period(date(2025, 6, 1), 340500, None, [], zero, None),
        Period(date(2025, 7, 1), 341715, None, [], zero, None),
        Period(
            date(2025, 8, 1),
            342493,
            None,
            [modeled("vehicle_inspection", "40000", source_map, date(2025, 8, 1), 342493)],
            zero,
            None,
        ),
        Period(
            date(2025, 9, 1),
            343740,
            None,
            [modeled("mandatory_liability_insurance", "50119", source_map, date(2025, 9, 1), 343740)],
            zero,
            None,
        ),
        Period(date(2025, 10, 1), 343741, None, [], zero, None),
        Period(date(2025, 11, 1), 344151, None, [], zero, None),
        Period(date(2025, 12, 1), 344461, None, [], zero, None),
        # 'Extra safety' (AJ) starts being tracked here; a blank AJ resets to 0 rather than
        # carrying forward the last non-blank value -- see module docstring.
        Period(date(2026, 1, 1), 344752, None, [], Decimal("5000"), None),
        Period(
            date(2026, 2, 1),
            344753,
            None,
            [modeled("motorway_vignette", "7190", source_map, date(2026, 2, 1), 344753)],
            Decimal("5000"),
            None,
        ),
        Period(
            date(2026, 3, 1),
            344913,
            None,
            [modeled("fuel_filter", "19000", source_map, date(2026, 3, 1), 344913)],
            Decimal("10000"),
            Decimal("10000"),
        ),
        Period(
            date(2026, 4, 1),
            344914,
            None,
            [
                modeled("annual_service", "80000", source_map, date(2026, 4, 1), 344914),
                modeled("fuel_filter", "40000", source_map, date(2026, 4, 1), 344914),
            ],
            Decimal("10000"),
            None,
        ),
        Period(date(2026, 5, 1), 344915, None, [], zero, None),
        Period(date(2026, 6, 1), 344916, None, [], zero, None),
        Period(date(2026, 7, 1), 344980, None, [], zero, None),
    ]


def apply_pocket_overrides(period: Period) -> Period:
    """Distribute the period's sheet-derived paid-out-of-pocket total across its expense lines.

    Which specific line absorbs how much doesn't matter -- paid-out-of-pocket is a check-in-level
    concept -- so this fills lines in submission order, the same way the bucket-depletion split
    itself works. Any amount left over once every line is fully covered (including a period with no
    modeled/other expenses at all) becomes a new synthetic 'other' expense, so the sheet's AK total
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
            "Imported from spreadsheet: untracked cash outlay (AK column, no matching expense line)",
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


def apply_maintenance_baselines(
    cost_service: CostService, owner_id: uuid.UUID, asset_id: uuid.UUID, source_map: SourceMap
) -> None:
    """Seed each item in `MAINTENANCE_BASELINE_RESETS` with its real last-serviced/interval fields.

    Bypasses the normal check-in-linked-expense reset for items that never get a real posted
    expense in this sheet's 101 rows, and additionally carries a same-call interval override for
    the two items whose forecast-table interval differs from this app's stock default (see module
    docstring).
    """
    for technical_key, changes in MAINTENANCE_BASELINE_RESETS:
        _source_type, item_id = source_map[technical_key]
        cost_service.update_maintenance_item(
            user_id=owner_id,
            asset_id=asset_id,
            item_id=item_id,
            changes=changes,
        )
        print(f"  Seeded {technical_key} baseline: {changes}")


def main() -> None:
    """Create the backdated vehicle asset, then replay its 101 real check-ins in order."""
    session = SessionLocal()
    try:
        owner = session.query(User).filter_by(email=OWNER_EMAIL).one()
        asset_service = AssetService(session)

        created = asset_service.create_asset(
            user_id=owner.id,
            name=ASSET_NAME,
            asset_type=None,
            template_key="vehicle",
            vehicle_details=VehicleDetails(starting_odometer=STARTING_ODOMETER, manufacture_year=MANUFACTURE_YEAR),
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
        cost_service = CostService(session)
        apply_maintenance_baselines(cost_service, owner.id, asset_id, source_map)

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
    """Confirm the posted paid_out_of_pocket total for this period matches the sheet's AK value.

    `apply_pocket_overrides` distributes AK across the period's expense lines (via
    `paid_out_of_pocket_override`, issue #95) before posting, so this should always match; a mismatch
    means the distribution or a modeled amount is wrong, not that the app can't represent it.
    """
    if period.expected_paid_out_of_pocket is None:
        return
    actual = sum((event.paid_out_of_pocket for event in expense_events), Decimal(0))
    if actual == period.expected_paid_out_of_pocket:
        print(f"  paid_out_of_pocket OK: {actual} matches sheet AK")
    else:
        print(
            f"  WARNING: paid_out_of_pocket mismatch for {period.period_end.isoformat()}: "
            f"app computed {actual}, sheet AK was {period.expected_paid_out_of_pocket}"
        )


if __name__ == "__main__":
    main()
