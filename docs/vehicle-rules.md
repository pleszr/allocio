# Allocio Vehicle Rules

Status: Draft v1
Last updated: 2026-07-25

## Purpose

This document defines the backend calculation and posting rules for the vehicle-first MVP.

It is the source of truth for:

- time-based accrual
- usage-based reserve accrual
- maintenance status derivation
- usage-based reserve recommendation
- check-in preview outputs
- check-in posting behavior
- future-only effect of edits

This document builds on [Domain model](domain-model.md).

## Scope

These rules apply only to `asset.type = vehicle`.

Out of scope for this document:

- frontend copy and layout
- SQL schema details
- non-vehicle asset types
- deferred workbook-only concepts such as depreciation

## Core Principle

The product is a virtual bucket planner.

Each posted check-in answers one question:

- how much value should be added to the bucket for the elapsed period, what expenses occurred, and
  how each expense is split between the virtual bucket and a one-time out-of-pocket payment

Posted history is immutable for normal product flows.

## Time Model

### Period boundaries

A vehicle check-in period is defined by:

- `period_start`
- `period_end`

Rules:

- `period_end` must be later than `period_start`, with one exception: the first posted check-in
  may have `period_end == period_start` (a zero-length baseline period, `elapsed_days = 0`) — see
  "First check-in" below
- a posted check-in covers one contiguous period
- `elapsed_days = period_end - period_start`, measured in whole calendar days

### First check-in

For the first posted vehicle check-in:

- `period_start = asset.created_at::date`
- `usage_start = vehicle_profile.starting_odometer`

Since `period_start` is pinned to asset creation and cannot be moved earlier, an asset checked in
on its creation day would otherwise have no valid `period_end` at all (today collides with
`period_start`, and any later date is rejected as future-dated). The first check-in is therefore
allowed to have `period_end == period_start`: a zero-length baseline that records the starting
odometer and tire type with zero accrual (`elapsed_days = 0` accrues nothing — see "Time-Based
Accrual" and "Usage-Based Reserve Accrual" below, both linear in `elapsed_days`/`usage_amount`). The
next check-in then starts from that same date, same as if the user had waited a day to post it.

### Subsequent check-ins

For every later posted vehicle check-in:

- `period_start = previous_posted_check_in.period_end`
- `usage_start = previous_posted_check_in.usage_end`

Rules:

- the next period starts where the previous posted period ended
- no gap or overlap is allowed between posted check-ins for the same vehicle

## Odometer And Usage

For a vehicle the usage unit is km, so the usage counter is the odometer and `usage_amount` is the kilometers driven.

For each check-in:

- `usage_amount = usage_end - usage_start`

Rules:

- `usage_end` must be greater than or equal to `usage_start`
- `usage_amount` must be greater than or equal to `0`
- odometer is always stored in kilometers in MVP

## Time-Based Accrual

### What accrues

Each active `time_based_cost` contributes accrual during the elapsed period.

Examples:

- Seasonal tire change
- Vehicle inspection
- Mandatory liability insurance
- Theft CASCO
- Parking CASCO
- Vehicle tax
- Motorway vignette

### Annualized amount

Each `time_based_cost` stores:

- `amount`
- `interval_value`
- `interval_unit`

The stored `amount` is the baseline amount for that cost line.

If modeled `expense_event` rows are linked to the same `time_based_cost`, the latest such expense may supersede the baseline for future periods.

Supported interval units for MVP:

- `months`
- `years`

Formula:

- `interval_years = interval_value / 12` when `interval_unit = months`
- `interval_years = interval_value` when `interval_unit = years`
- `reference_amount(period) = latest linked modeled expense amount whose event_date is on or before period_start`, if one exists
- otherwise `reference_amount(period) = time_based_cost.amount`
- `annualized_amount = reference_amount(period) / interval_years`

Examples:

- `14,000 HUF` every `6 months` -> `28,000 HUF/year`
- `49,900 HUF` every `1 year` -> `49,900 HUF/year`
- `41,500 HUF` every `2 years` -> `20,750 HUF/year`

Example of latest-cost rollover:

- insurance expense logged for `2025-06-01`: `49,900 HUF`
- insurance expense logged for `2026-06-01`: `56,000 HUF`
- periods with `period_start >= 2025-06-01` and `< 2026-06-01` use `49,900 HUF`
- periods with `period_start >= 2026-06-01` use `56,000 HUF`

### Period accrual

Formula:

- `daily_rate = annualized_amount / 365`
- `period_time_accrual = daily_rate * elapsed_days`

Rules:

- time-based accrual is continuous across the period
- each active time-based cost generates its own preview line item
- each active time-based cost generates its own posted allocation event
- one time-based cost line uses one `reference_amount(period)` for the entire check-in period
- no within-period proration is applied in MVP when a new modeled expense is logged
- a newly logged modeled expense for a time-based cost becomes the reference amount starting with the first period whose `period_start` is on or after that expense date

### Creation estimate

Before an asset exists, the New Bucket review asks the backend to annualize the selected template
time-based rows, their overrides, and custom draft time-based rows with the same formulas above.
For each row it returns quantized annualized, monthly (`annualized_amount / 12`), and daily
(`annualized_amount / 365`) values, plus totals. In particular, a one-month amount annualizes to
exactly twelve times that amount; the estimate never approximates a month as 30 days. The estimate
is read-only and excludes usage-based rows because no usage history or forecast is supplied.

### Next-due date

The next-due date is an informational signal derived from a time-based cost's optional `first_due_date` anchor and its interval.

Rules:

- next-due is the first occurrence on or after today, found by rolling `first_due_date` forward by whole intervals
- a `first_due_date` on or after today yields itself (the first occurrence has not happened yet)
- a null `first_due_date` yields no next-due date (null)
- month-end anchors clamp to the target month's last day (e.g. `2025-01-31` + 1 month → `2025-02-28`)
- next-due is informational only: it does not change the annualized amount or the period accrual formulas above

## Usage-Based Reserve Accrual

### What accrues

An asset may have several active `usage_based_cost` rows. A vehicle starts seeded with one
(`10 HUF/km`), and the user may add further usage-based components (e.g. fuel, tire wear).

Each row reserves money per unit of usage (per kilometer driven for a vehicle).

Example:

- `Usage-based reserve: 10 HUF/km`, `Fuel: 45 HUF/km`, `Tire wear: 4 HUF/km`

### Period accrual

Formula:

- `period_usage_accrual = Σ over active rows of (usage_amount * amount_per_unit)`

Rules:

- there is one usage-based preview line item **and one allocation event per active usage row**
- each row's line is rounded independently and then summed (`Σ quantize`); with a single active row
  this collapses to `quantize(usage_amount * amount_per_unit)`, unchanged from the prior single-row behavior
- posting creates one usage-based allocation event **per active usage row** for the period
- each rate is fully user-adjustable, and rows can be deactivated

> Rounding divergence (not a bug): check-in accrual rounds **per line** (`Σ quantize`, each allocation
> line quantized then summed), while the workspace recommended-monthly figure rounds the **combined
> total once** (`quantize(Σ)`). Both are pre-existing, internally-correct patterns.

## Maintenance Status

### Applicability

Each active `maintenance_item` may have:

- `interval_km`
- `interval_months`
- `last_serviced_at_date`
- `last_serviced_at_odometer`
- optional `tire_type`

At least one interval must be present.

### Elapsed distance and elapsed months

For non-tire-specific maintenance items:

- `km_since_service = current_odometer - last_serviced_at_odometer`

For tire-specific maintenance items:

- `km_since_service = sum(usage_amount)` across posted check-ins after `last_serviced_at_date` where `check_in.active_tire_type = maintenance_item.tire_type`

For all maintenance items:

- `months_since_service = full calendar months between last_serviced_at_date and reference_date`

Reference date:

- use `period_end` during check-in preview
- use today or the latest posted state for read endpoints

### Progress ratios

Formula:

- `km_progress = km_since_service / interval_km` when `interval_km` is present
- `month_progress = months_since_service / interval_months` when `interval_months` is present

### Status thresholds

Status is derived as follows:

- `overdue` if any present progress ratio is greater than or equal to `1.05`
- `due` if not overdue and any present progress ratio is greater than or equal to `0.90`
- `soon` if not due or overdue and any present progress ratio is greater than or equal to `0.80`
- `ok` otherwise

Rules:

- if both km and month thresholds exist, the earlier threshold wins
- tire-specific rows should be evaluated only against usage from matching tire periods
- `soon` is a preparation state and should be shown as a yellow warning in the UI
- `due` should be called out explicitly and should be shown as orange in the UI
- `overdue` should be called out explicitly and should be shown as red in the UI

## Usage-Based Reserve Recommendation

### Goal

The app should help the user understand whether the current `HUF/km` reserve rate looks low, reasonable, or high.

### Inputs

Only maintenance items with all of the following contribute:

- `is_active = true`
- `estimated_cost` present
- `interval_km` present

Tire-specific rule:

- a tire-specific row contributes only when its `tire_type` is relevant to the current vehicle setup
- for all-season tires, use the all-season row
- for summer or winter tire setups, use the matching row

### Recommended rate

For each contributing maintenance item:

- `item_rate = estimated_cost / interval_km`

Formula:

- `recommended_usage_rate = sum(item_rate for all contributing items)`

### Guidance bands

Compare the user-configured `amount_per_unit` against `recommended_usage_rate`.

Rules:

- `low` if configured rate is less than `0.9 * recommended_usage_rate`
- `reasonable` if configured rate is between `0.9 * recommended_usage_rate` and `1.1 * recommended_usage_rate`
- `high` if configured rate is greater than `1.1 * recommended_usage_rate`

If no maintenance items contribute:

- no recommendation category should be shown
- the API may still return `recommended_usage_rate = null`

## Expense Recognition

### Expense kinds

Expenses recognized against the bucket may be:

- modeled expenses linked to a source row
- manual `Other` expenses with a free-text comment

Each expense may include:

- `event_date`
- `amount`
- `comment`
- `source_type`
- `source_id`
- optional `usage_counter_at_event`

Each computed or posted expense exposes:

- `amount`: the full real-world expense
- `bucket_amount`: the portion funded by the virtual bucket
- `paid_out_of_pocket`: the derived remainder funded outside the bucket

### Relation to check-in

For MVP check-in posting:

- expenses included in the check-in request are posted as `expense_event` rows as part of the same posting transaction

Rules:

- each submitted expense becomes its own posted expense event
- expenses consume the available bucket amount in request order
- a check-in expense can use both the opening balance and allocations created by that check-in
- an expense reduces the bucket only by `bucket_amount = amount - paid_out_of_pocket`
- `paid_out_of_pocket` defaults to the derived shortfall; the caller may raise it (never lower it below the derived shortfall) up to `amount`. Always non-negative and never exceeds `amount`.
- a standalone expense is covered only by the bucket balance available on its `event_date`
- the bucket balance never becomes negative
- modeled expenses may reference the maintenance or cost row they relate to
- `Other` may leave `source_type` and `source_id` empty
- if a modeled expense is linked to a `time_based_cost`, its `amount` may become the new `reference_amount(period)` for future periods as defined above

## Check-In Preview

### Inputs

A check-in preview must be able to accept:

- `asset_id`
- `period_end`
- `usage_end`
- `active_tire_type`
- optional expense draft items for the period

### Derived preview fields

Preview must derive:

- `period_start`
- `usage_start`
- `elapsed_days`
- `usage_amount`
- time-based accrual line items
- usage-based accrual line items
- a prorated manual-extra allocation line when `manual_extra_monthly > 0` and `elapsed_days > 0`
- expense line items
- `balance_before`
- `total_allocation`
- `total_expense`
- `total_bucket_expense`
- `paid_out_of_pocket`
- `net_bucket_change`
- `balance_after`
- maintenance statuses at period end
- usage-based reserve recommendation

### Period validation and tire-type default

- `period_start` is always server-derived from the latest posted check-in's `period_end` (or the asset's creation date/starting odometer for the first check-in) — a caller can never supply it, so backdating is inherently append-only: there is no way to insert a period between two already-posted ones.
- `period_end` must be later than the derived `period_start` **and** no later than today, except that the first posted check-in may have `period_end == period_start` (see "First check-in" above). A future `period_end` is rejected: future-dated events would make the live bucket balance diverge from the derived monthly series (see "Derived monthly series" below, which only counts events dated on or before today).
- Within that window, `period_end` may be in the past — a backdated check-in is a normal, supported preview/post input, not a special case.
- `active_tire_type` defaults to the previous posted check-in's value when the caller omits it (`null`); there is no default for an asset's first check-in. An explicit value in the request always overrides the default, for both preview and posting.

### Preview formulas

Formula:

- `manual_extra_period = quantize_currency(manual_extra_monthly * 12 / 365 * elapsed_days)`
- `total_allocation = sum(time_based_line_items) + sum(usage_based_line_items) + manual_extra_period`
- `total_expense = sum(expense_line_item.amount)`
- `available = balance_before + total_allocation`
- for each expense in submitted order:
  - `natural_bucket_amount = min(expense.amount, remaining_available)`
  - `natural_paid_out_of_pocket = expense.amount - natural_bucket_amount`
  - `paid_out_of_pocket = clamp(override, natural_paid_out_of_pocket, expense.amount)` when an override is submitted, else `natural_paid_out_of_pocket`
  - `bucket_amount = expense.amount - paid_out_of_pocket`
  - `remaining_available = remaining_available - bucket_amount`
- `total_bucket_expense = sum(expense_line_item.bucket_amount)`
- `paid_out_of_pocket = sum(expense_line_item.paid_out_of_pocket)`
- `net_bucket_change = total_allocation - total_bucket_expense`
- `balance_before = sum(posted_allocation_events) - sum(posted_expense_event.bucket_amount)`
- `balance_after = max(0, balance_before + net_bucket_change)`

Rules:

- preview does not write any records
- preview must be deterministic for the same input and underlying stored state
- preview is the exact calculation basis for posting

## Check-In Posting

### Records created

Posting a confirmed check-in creates:

- one `check_in` row
- one `allocation_event` per active time-based cost
- one `allocation_event` per active usage-based cost row
- one `manual_extra` allocation event when the configured monthly extra and elapsed period are positive
- one `expense_event` per submitted expense

### Posting formulas

Posting uses the exact same formulas as preview.

Rules:

- the posted amounts must match the immediately preceding preview for the same input
- every posted expense persists its full `amount` and derived `paid_out_of_pocket`; `bucket_amount`
  remains derivable as their difference
- the manual-extra event has `source_type = manual_extra`, no `source_id`, and stores the
  prorated period amount; a zero-length baseline emits no manual-extra event
- posting is transactional
- either the check-in and all resulting events are written, or none of them are

### Maintenance service-baseline reset

When a posted check-in includes an expense whose `source_type = maintenance_item`, posting resets that maintenance item's service baseline as a side-effect, in the same transaction as the rest of the post:

- MVP rule: **any** maintenance-linked expense resets the item — there is no separate "was this actually a service?" flag.
- Reset target is the check-in's own `period_end` and `usage_end`, not the expense's `event_date`:
  - non-tire items (`tire_type` is unset): `last_serviced_at_date = period_end` and `last_serviced_at_odometer = usage_end`
  - tire items (`tire_type` set): `last_serviced_at_date = period_end` only — the odometer field is left unchanged, because tire km-since-service already re-sums usage from that date across matching-tire-type check-ins (see "Elapsed distance and elapsed months" above); resetting the odometer too would double-count.
- The reset changes only the maintenance item's current editable row, which drives future status/recommendation figures. It does not alter the posted `check_in`/`allocation_event`/`expense_event` rows, which stay immutable exactly as before (see "Future-Only Effect Of Edits" below).
- If multiple submitted expenses link to the same maintenance item in one check-in, the result is the same as if only one had — the target values are the check-in's own `period_end`/`usage_end`, not the expense's.
- A failure anywhere in the post (including an unexpected missing maintenance row) rolls back the whole transaction, so a maintenance item is never reset without its triggering check-in also being posted, and vice versa.

### Check-in status

For MVP:

- preview is transient
- persisted check-ins should use `status = posted`

If draft check-ins are added later:

- they must not affect balance or history until posted

## Bucket Balance Reconstruction

Canonical balance is always derived from posted events.

Formula:

- `bucket_balance = sum(allocation_event.amount) - sum(expense_event.amount - expense_event.paid_out_of_pocket)`

Rules:

- read models may cache balance for performance later
- cached balance is not source of truth
- balance is never presented below zero for newly posted data
- a check-in-linked expense keeps its real `event_date` for audit and reference-cost rollover, but
  its covered bucket movement is recognized on the parent check-in's `period_end`, alongside that
  check-in's allocations
- a standalone expense's covered bucket movement is recognized on its own `event_date`

### Derived monthly series (dashboard sparkline)

`GET /api/assets/{asset_id}/balance-history` reconstructs a monthly time series of this same
event-derived covered balance. Each point is the cumulative balance as of one as-of date — the last day of
that month, or today for the current (partial) month — so the series is derived entirely from posted
`allocation_events` and the bucket-covered portions of `expense_events`, never stored. This follows the same reconstruction
principle stated in `docs/domain-model.md:361` (balances are derived, not persisted).

The newest point (as of today) equals the live bucket balance above, assuming every effective bucket
movement date is on or before today. Future-dated standalone expenses are the one exception: the live
balance includes every posted event, whereas the newest history point counts only movements dated on
or before today.

## Future-Only Effect Of Edits

### Meaning of future-only

For MVP:

- `future` means any period that has not yet been posted
- `past` means any period already represented by posted events

### Edit rules

When a user edits or deactivates a cost or maintenance row:

- already posted check-ins and posted events do not change
- future previews and future postings use the current active configuration

Rules:

- editing a time-based cost changes future time-based accrual only
- logging a modeled expense against a time-based cost may change the future reference amount for that cost only
- editing the usage-based reserve changes future usage accrual only
- editing a maintenance item changes future status and recommendation logic only
- deactivation removes the row from future calculations but not from historical audit

### Check-in expense edit (deliberate exception)

A user may correct a posted check-in's expenses from the History tab. This is a narrow, deliberate
exception to the future-only rule above, not a general reopen of posted history:

- editable: only that check-in's `expense_event` rows (add/remove/edit `amount`, `comment`,
  `source_type`/`source_id`, and the `paid_out_of_pocket` split) and its `notes`
- immutable even on this path: `period_end`, `usage_start`/`usage_end`, `active_tire_type`, and every
  `allocation_event` row — the period's derived accrual is never recomputed and never recomputed from
  a since-changed cost rate, since the edit reuses the check-in's own already-posted allocation total
- persistence is in-place mutation (delete then re-insert the check-in's `expense_events`), not a
  supersede/versioning model — there is no "edited" indicator anywhere in the History UI
- mandatory forward-simulation guard: before applying, walk the *unclamped* running balance forward
  from the edited check-in through every later already-posted check-in's own existing (unchanged)
  `allocated - bucket_expense` total; if that running total would go negative at any later check-in,
  the edit is rejected outright (422, naming the first offending `period_end`) — never silently
  clamped to zero. Both the edit-preview and the apply endpoint independently run this guard; the
  apply endpoint never trusts a prior preview call
- maintenance-baseline re-derivation: after applying the edit, for every maintenance item whose link
  changed (removed by the edit, or newly added by it), reset that item's baseline
  (`last_serviced_at_date`, and `last_serviced_at_odometer` for a non-tire item) to whichever posted
  check-in is now the *latest* one still linking an expense to it — not assumed to still be the
  just-edited check-in. Documented limitation: if the edit removes the only check-in that ever linked
  to an item, that item's current baseline fields are left exactly as they were rather than nulled —
  there is no prior value recorded to roll back to, so this is accepted behavior, not a bug

## Workbook-Grounded Examples

### Example 1: usage-based accrual

Inputs:

- `period_start = 2026-04-01`
- `period_end = 2026-05-01`
- `usage_start = 344,914`
- `usage_end = 345,814`
- `amount_per_unit = 10 HUF/km`

Derived:

- `elapsed_days = 30`
- `usage_amount = 900`
- `period_usage_accrual = 900 * 10 = 9,000 HUF`

### Example 2: time-based accrual

Inputs:

- Mandatory liability insurance: `49,900 HUF` every `1 year`
- Seasonal tire change: `14,000 HUF` every `6 months`
- Vehicle inspection: `41,500 HUF` every `2 years`
- `elapsed_days = 30`

Derived:

- KGFB annualized = `49,900 HUF/year`
- Tire change annualized = `28,000 HUF/year`
- Inspection annualized = `20,750 HUF/year`
- Period KGFB accrual = `49,900 / 365 * 30 = 4,101.37 HUF`
- Period tire-change accrual = `28,000 / 365 * 30 = 2,301.37 HUF`
- Period inspection accrual = `20,750 / 365 * 30 = 1,705.48 HUF`

### Example 3: maintenance status

Oil service assumptions:

- `interval_km = 12,000`
- `interval_months = 12`
- `last_serviced_at_odometer = 344,000`
- `current_odometer = 354,500`
- `last_serviced_at_date = 2025-08-01`
- `reference_date = 2026-05-01`

Derived:

- `km_since_service = 10,500`
- `km_progress = 10,500 / 12,000 = 0.875`
- `months_since_service = 9`
- `month_progress = 9 / 12 = 0.75`
- status = `soon` because max progress is `0.875`

### Example 4: reserve recommendation

Contributing maintenance items:

- Battery: `estimated_cost = 60,000`, `interval_km = 100,000` -> `0.60 HUF/km`
- Fuel filter: `estimated_cost = 36,000`, `interval_km = 45,000` -> `0.80 HUF/km`
- All-season tires: `estimated_cost = 140,000`, `interval_km = 50,000` -> `2.80 HUF/km`

Derived:

- `recommended_usage_rate = 0.60 + 0.80 + 2.80 = 4.20 HUF/km`

If the user-configured rate is:

- `3.5 HUF/km` -> `low`
- `4.2 HUF/km` -> `reasonable`
- `5.0 HUF/km` -> `high`

## Backend Implementation Notes

- calculator logic should live in a domain/service layer, not in routers
- preview and posting must share the same calculation functions
- each posted allocation event should keep enough metadata to explain its source row later
- each posted expense event should keep enough metadata to explain whether it was modeled or `Other`
  and how much was covered by the bucket versus paid out of pocket

## Workspace Overview Derivations

The workspace overview (`GET /api/assets`) derives, per asset and workspace-wide, from the same
pure calculator used by check-ins. These are canonical rules.

### Recommended monthly allocation

For each asset, the recommended monthly allocation is the amount the user should set aside per
month to keep the bucket funded:

- **Time-based monthly** = for every **active** time-based cost, its reference amount (after
  latest-cost rollover) annualized over its interval and spread across twelve months:
  `reference_amount / interval_years / 12`. Inactive rows are excluded. Sum across active rows.
- **Usage-based monthly** = `amount_per_unit × trailing-average monthly usage`, where the average
  is `total_posted_usage / whole_months(first_period_start, last_period_end)` (a span of zero
  months divides by one, and zero usage yields zero).
- **Recommended monthly allocation** = `quantize_currency(time_based_monthly + usage_based_monthly)`.

Workspace totals are plain sums of the per-asset balances and recommended monthly allocations
(single-currency MVP — all buckets are HUF today).

### Funding health

The former `underfunded` / `healthy` / `overflowing` status and workspace `alert_count` are not part
of the current contract. They compared accumulated balance with one month's allocation and therefore
misclassified both new buckets and buckets saved over several months. A future target-based model may
reintroduce funding health once it can explain the status against accrued-to-date obligations.
