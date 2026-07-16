# Allocio Vehicle Rules

Status: Draft v1
Last updated: 2026-05-15

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
- deferred workbook-only concepts such as depreciation or extra safety

## Core Principle

The product is a virtual bucket planner.

Each posted check-in answers one question:

- how much value should be added to the bucket for the elapsed period, and what expenses should be recognized against the bucket for that same period

Posted history is immutable for normal product flows.

## Time Model

### Period boundaries

A vehicle check-in period is defined by:

- `period_start`
- `period_end`

Rules:

- `period_end` must be later than `period_start`
- a posted check-in covers one contiguous period
- `elapsed_days = period_end - period_start`, measured in whole calendar days

### First check-in

For the first posted vehicle check-in:

- `period_start = asset.created_at::date`
- `usage_start = vehicle_profile.starting_odometer`

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

## Usage-Based Reserve Accrual

### What accrues

Each vehicle has one active `usage_based_cost` row in MVP.

Its purpose is to reserve money per kilometer driven.

Example:

- `10 HUF/km`

### Period accrual

Formula:

- `period_usage_accrual = usage_amount * amount_per_unit`

Rules:

- there is one usage-based preview line item per vehicle
- posting creates one usage-based allocation event for the period
- the rate is fully user-adjustable

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

### Relation to check-in

For MVP check-in posting:

- expenses included in the check-in request are posted as `expense_event` rows as part of the same posting transaction

Rules:

- each submitted expense becomes its own posted expense event
- expenses reduce the bucket balance
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
- usage-based accrual line item
- expense line items
- `balance_before`
- `total_allocation`
- `total_expense`
- `net_bucket_change`
- `balance_after`
- maintenance statuses at period end
- usage-based reserve recommendation

### Preview formulas

Formula:

- `total_allocation = sum(time_based_line_items) + period_usage_accrual`
- `total_expense = sum(expense_line_items)`
- `net_bucket_change = total_allocation - total_expense`
- `balance_before = sum(posted_allocation_events) - sum(posted_expense_events)`
- `balance_after = balance_before + net_bucket_change`

Rules:

- preview does not write any records
- preview must be deterministic for the same input and underlying stored state
- preview is the exact calculation basis for posting

## Check-In Posting

### Records created

Posting a confirmed check-in creates:

- one `check_in` row
- one `allocation_event` per active time-based cost
- one `allocation_event` for the usage-based reserve
- one `expense_event` per submitted expense

### Posting formulas

Posting uses the exact same formulas as preview.

Rules:

- the posted amounts must match the immediately preceding preview for the same input
- posting is transactional
- either the check-in and all resulting events are written, or none of them are

### Check-in status

For MVP:

- preview is transient
- persisted check-ins should use `status = posted`

If draft check-ins are added later:

- they must not affect balance or history until posted

## Bucket Balance Reconstruction

Canonical balance is always derived from posted events.

Formula:

- `bucket_balance = sum(allocation_event.amount) - sum(expense_event.amount)`

Rules:

- read models may cache balance for performance later
- cached balance is not source of truth

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

### Health status

Each asset's funding health bands its event-derived bucket balance against an `expected_reserve`,
reusing the same `0.9` / `1.1` ratios as `reserve_guidance` (no new magic numbers):

- `underfunded` when `balance < 0.9 × expected_reserve`
- `healthy` when `0.9 × expected_reserve ≤ balance ≤ 1.1 × expected_reserve`
- `overflowing` when `balance > 1.1 × expected_reserve`
- `healthy` whenever `expected_reserve ≤ 0` (nothing to fund)

`alert_count` in the workspace totals counts the `underfunded` assets.

**v1 definition and limitation:** `expected_reserve = one recommended monthly allocation`. Because
this compares a stock (the accumulated balance) against a single month's target, a brand-new asset
(balance `0`) reads `underfunded`, and a bucket saved up over several months trends toward
`overflowing`. This is an intentional MVP simplification: there is no next-due model for time-based
costs to anchor an accrued-to-date target. A future issue should replace `expected_reserve` with an
accrued-to-date target once time-based costs carry a next-due date.
