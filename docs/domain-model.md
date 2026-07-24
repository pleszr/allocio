# Allocio Domain Model

Status: Draft v1
Last updated: 2026-05-15

## Purpose

This document defines the canonical domain model for the vehicle-first MVP.

It is the source of truth for:

- core product entities
- relationships between entities
- what is stored versus what is derived
- default vehicle templates
- auditability rules for balances, check-ins, and future edits

This document is intentionally product-oriented. It is not yet the SQL schema.

## MVP Scope

- `asset.type` is type-agnostic: any asset (e.g. a house, an appliance) can be tracked
- `vehicle` is not a first-class type; it is a built-in creation template that prefills a vehicle profile and default cost rows
- a bare asset gets only a bucket; it has no profile and no default rows until the user adds them
- the model should stay extensible for future built-in templates
- the bucket is virtual
- the app does not move real money
- the app is not a fuel-tracking or general expense-tracking app

## Terminology

### Asset

The thing being tracked.

MVP example:

- a specific car

### Bucket

The virtual savings container attached to an asset.

### Time-based cost

A recurring cost driven by time, not distance.

Examples:

- mandatory liability insurance
- comprehensive insurance
- vehicle tax
- motorway vignette
- vehicle inspection
- seasonal tire change

### Usage-based cost

One or more adjustable usage-based components driven by usage of the asset.

These are user-defined per-usage-unit reserves that smooth wear and maintenance costs over time (e.g. a general reserve, fuel, tire wear).

MVP example:

- `10 HUF/km`

### Maintenance item

A tracked item with a service or replacement interval. It exists to show operational status such as `ok`, `soon`, `due`, or `overdue`.

Maintenance items may also provide recommendation input for the usage-based reserve if they include cost assumptions.

In the spreadsheet model, a maintenance item may become due by distance, by elapsed time, or by whichever threshold is reached first.

### Check-in

The monthly review workflow where the user records elapsed usage, reviews accruals and expenses, and posts the period result.

### Allocation event

A posted event that moves value into the bucket.

### Expense event

A posted event that moves value out of the bucket.

## Domain Principles

- historical truth comes from posted events
- current editable rows drive future calculations only
- bucket balance is derived, not primary source data
- the current usage counter (the odometer for a vehicle) is derived from the latest posted check-in, not stored as an independent source of truth
- maintenance status is derived, not stored as canonical truth
- users can remove or deactivate defaults, but historical references must remain auditable

## Core Entities

### `asset`

Top-level tracked item.

Fields:

- `id`
- `user_id`
- `type`
- `name`
- `status`
- `created_at`
- `archived_at`

Rules:

- `type` is the product term, not `kind`
- `type` is free-form; `vehicle` is the type set by the built-in vehicle template, not the only allowed value
- `name` is the sole asset and bucket-facing identifier
- one asset has one bucket in MVP

### `vehicle_profile`

Vehicle-only metadata attached to an asset.

Fields:

- `asset_id`
- `starting_odometer`

Rules:

- `vehicle_profile` exists only for `asset.type = vehicle`
- `starting_odometer` is the only vehicle-specific metadata collected at creation
- `current_odometer` is derived from the latest posted check-in
- no `trim`
- no odometer unit field in MVP
- odometer is always stored in kilometers in MVP

### `bucket`

Virtual savings container for one asset.

Fields:

- `id`
- `asset_id`
- `currency`
- `opened_at`
- `closed_at`

Rules:

- one bucket per asset in MVP
- stored balance, if introduced for performance later, is a cache only
- canonical balance is the sum of posted allocation and expense events

### `time_based_cost`

Recurring cost driven by elapsed time.

Fields:

- `id`
- `asset_id`
- `label`
- `technical_key`
- `amount`
- `interval_value`
- `interval_unit`
- `first_due_date`
- `notes`
- `is_active`

Rules:

- no `effective_from`
- no `effective_to`
- active rows participate in future calculations
- inactive rows do not participate in future calculations
- posted history remains unchanged when a row is edited or deactivated
- `label` is user-facing copy
- `technical_key` is an internal stable identifier for system-defined rows
- user-created custom rows may leave `technical_key` empty
- `amount` is the baseline amount used when no later modeled expense has superseded it
- `first_due_date` is a nullable anchor date of a known occurrence
- when `first_due_date` is set, a next-due date is derived by rolling the interval forward to the first occurrence on or after today
- when `first_due_date` is null the next-due date is omitted (null)
- template rows are seeded with a null anchor
- the anchor and its derived next-due date are informational only and do not affect accrual

### `usage_based_cost`

A collection of adjustable usage-based components driven by usage of the asset.

Fields:

- `id`
- `asset_id`
- `label`
- `technical_key`
- `amount_per_unit`
- `usage_unit`
- `currency`
- `notes`
- `is_active`

Rules:

- an asset may have several active usage-based cost rows; each accrues independently and emits its own preview line and allocation event
- the earlier "one active usage-based reserve" rule was enforced only in the service layer (via `.one_or_none()` plus a single create path), never as a DB constraint; issue #49 intentionally reverses it to a multi-component model with no schema/migration change
- `usage_unit` names the unit usage is counted in; the vehicle template sets `usage_unit = km`
- no `effective_from`
- no `effective_to`
- active rows participate in future calculations
- inactive rows do not participate in future calculations
- the rate is user-adjustable
- the app may derive a recommendation for whether the current rate is low, reasonable, or high
- that recommendation is derived guidance, not canonical stored truth
- `label` is user-facing copy
- `technical_key` is an internal stable identifier for system-defined rows

### `maintenance_item`

Tracked maintenance or replacement item with an interval.

Fields:

- `id`
- `asset_id`
- `label`
- `technical_key`
- `interval_km`
- `interval_months`
- `last_serviced_at_date`
- `last_serviced_at_odometer`
- `estimated_cost`
- `tire_type`
- `notes`
- `is_active`

Rules:

- `interval_km` is optional
- `interval_months` is optional
- at least one of `interval_km` or `interval_months` must be present, except for the default `Other` catch-all (`technical_key = 'other'`), which may leave both null
- `estimated_cost` is optional
- `tire_type` is nullable
- `tire_type` is used for tire-specific maintenance rows
- status such as `ok`, `soon`, `due`, or `overdue` is derived
- a maintenance item may become due because of kilometers, elapsed months, or both
- inactive rows remain visible in history but do not drive future alerts
- km-based items with an `estimated_cost` may contribute to the derived recommendation for the usage-based reserve rate
- `label` is user-facing copy
- `technical_key` is an internal stable identifier for system-defined rows
- user-created custom rows may leave `technical_key` empty

### `check_in`

Monthly review record for one asset.

Fields:

- `id`
- `asset_id`
- `period_start`
- `period_end`
- `checked_in_at`
- `usage_start`
- `usage_end`
- `usage_amount`
- `active_tire_type`
- `notes`
- `status`

Rules:

- `usage_amount = usage_end - usage_start`
- `usage_start`, `usage_end`, and `usage_amount` are nullable; a non-usage asset posts a check-in with no usage counter
- `active_tire_type` is one of `summer`, `winter`, or `all_season`
- tire-specific maintenance progress should reflect the selected tire type for the check-in
- MVP assumes one tire type per check-in period
- posting a check-in creates the auditable events for that period

### `allocation_event`

Posted value moving into the bucket.

Fields:

- `id`
- `bucket_id`
- `check_in_id`
- `event_date`
- `source_type`
- `source_id`
- `amount`
- `metadata_json`

Rules:

- examples of `source_type`: `time_based_cost`, `usage_based_cost`
- events are immutable after posting, except for explicit admin repair workflows if such workflows are added later

### `expense_event`

Posted value moving out of the bucket.

Fields:

- `id`
- `bucket_id`
- `check_in_id`
- `event_date`
- `usage_counter_at_event`
- `kind`
- `amount`
- `comment`
- `source_type`
- `source_id`
- `metadata_json`

Rules:

- `kind` supports both modeled expenses and manual `Other`
- `usage_counter_at_event` is optional but should be supported for vehicle service and replacement history
- a modeled expense linked to a `time_based_cost` may become the new reference amount for future accrual periods for that source row
- `source_type` and `source_id` are nullable for manual `Other`
- posted expenses must remain sufficient to reconstruct balance history

## Relationships

- one `asset` belongs to one user
- one `asset` has one `bucket` in MVP
- one `asset` may have one `vehicle_profile`
- one `asset` has many `time_based_cost` rows
- one `asset` has many `usage_based_cost` rows
- one `asset` has many `maintenance_item` rows
- one `asset` has many `check_in` rows
- one `bucket` has many `allocation_event` rows
- one `bucket` has many `expense_event` rows
- one `check_in` may post many allocation and expense events

## Stored Versus Derived

Stored:

- asset metadata
- vehicle metadata
- editable cost rows
- editable maintenance rows
- check-in records
- posted allocation events
- posted expense events

Derived:

- current bucket balance
- current usage counter
- monthly allocation suggestion
- recommendation for usage-based reserve rate
- maintenance health and urgency status
- dashboard summaries and trends

## Edit And History Rules

- editing a current cost row changes future calculations only
- deactivating a row changes future calculations only
- posted events are not recalculated from the current editable rows
- historical balances are reconstructed from posted events, not from current cost configuration
- if a row has already contributed to posted history, it should not be hard-deleted from canonical storage
- implementation may hard-delete an unused draft or template-cloned row only if it has never been referenced by posted data

## Built-In Templates

Vehicle is the first built-in template; more may be added later, each as its own registry entry with its own default rows. The template exposes a catalog of pickable default rows the caller selects from at creation time, across:

- time-based costs
- usage-based reserve settings
- maintenance items

Creation rule:

- the template's full catalog is readable up front so a client can build a selection UI
- selecting the vehicle template clones only the caller-selected catalog rows (by `technical_key`) into asset-owned rows; selecting none clones no rows (there is no implicit clone-all)
- the vehicle profile and bucket are still created from the template regardless of the cost selection
- after creation, the asset owns those rows
- the user may deactivate or remove them
- the user may add custom rows
- later template changes do not retroactively change existing assets
- system-defined template rows should carry both a user-facing `label` and an internal `technical_key`
- a time-based or usage-based row's default amount is curated per currency (HUF/EUR/USD); the clone uses the entry matching the asset owner's currency, never a live or computed conversion
- the caller may override a selected time-based or usage-based row's amount (and, for time-based rows, its interval) at clone time; the template value is only the starting default. A maintenance-item row has no curated amount yet and does not accept an override
- a template row's `label` is the stable translation source: the New Bucket wizard looks up a UI-language translation keyed by `technical_key`, falling back to this `label` when no translation exists for the active language

The defaults are code-backed seed definitions today (`app/domain/vehicle_defaults.py`), selected through the template registry (`app/domain/asset_templates.py`). That implementation choice is separate from the domain model.

## Default Time-Based Cost Templates For Vehicles

Proposed English labels:

- Seasonal tire change
- Vehicle inspection
- Mandatory liability insurance
- Comprehensive insurance
- Vehicle tax
- Motorway vignette

Notes:

- `Seasonal tire change` should default to a recurring cadence that represents two changes per year
- `Vehicle inspection` should default to a recurring cadence of every two years
- `Vehicle tax` should default to two payments per year, matching the workbook model
- `Comprehensive insurance` is a single merged row (`technical_key` `comprehensive_insurance`) covering own-damage cover that pays even when the driver is at fault. It replaces the earlier two-row `Theft CASCO` + `Parking CASCO` model; its default `amount` is the sum of those two workbook lines. The non-English "CASCO"/"Kasko" term is intentionally dropped in favor of the English label.
- each row's HUF amount is the workbook-sourced figure; its EUR and USD amounts are a rough flat-conversion placeholder (not live/authoritative pricing) pending a market-accuracy review

## Default Usage-Based Cost Templates For Vehicles

Vehicle should start with one editable usage-based reserve row.

Proposed label:

- Usage-based reserve

Notes:

- this is a per-kilometer rate for the whole vehicle
- example: `10 HUF/km` (HUF default; the row also carries a curated EUR and USD default — see "Built-In Templates" above)
- the rate is user-adjustable
- users may add further usage-based components (e.g. fuel, tire wear); the seeded row is a starting default, not a hard limit
- the app should later help the user understand whether the chosen rate is low, reasonable, or high based on captured maintenance assumptions

## Default Maintenance Templates For Vehicles

These defaults are the main structured inputs for maintenance tracking and for future recommendation of the usage-based reserve rate.

Proposed English labels:

- Front brake discs
- Rear brake discs
- Front brake pads
- Rear brake pads
- Annual service
- Automatic transmission fluid
- Fuel filter
- Water pump
- Timing system
- Battery
- All-season tires
- Winter tires
- Summer tires
- Other

Notes:

- fuel is intentionally not part of the usage-based model in MVP
- tire-specific rows should use `tire_type` where applicable
- `Annual service` should exist only as a maintenance item in MVP
- `Other` should be created by default as a manual catch-all item
- `Other` should not drive product intelligence by default
- recommendation logic for usage-based reserve should use only the subset of maintenance items that have sufficient cost and interval data

For tire-related items:

- `All-season tires` should map to `tire_type = all_season`
- `Winter tires` should map to `tire_type = winter`
- `Summer tires` should map to `tire_type = summer`

This allows check-ins to update the correct tire-specific maintenance progress.

## Non-Goals And Boundaries

- no fuel purchase tracking
- no real-money account integration
- no support for miles in MVP
- bare non-vehicle assets are creatable via the API, but the asset-creation and template-picker UI is a later increment
- no retroactive mutation of posted history through normal editing flows

## Deferred Concepts From The Workbook

The following concepts exist in the spreadsheet model but are intentionally deferred from the current MVP domain model:

- vehicle depreciation (`autó értékcsökkenés`)
- alternative vehicle cost (`autó alternatív ktg`)
- out-of-pocket payments (`Kifizettuk zsebbol`)
- extra safety buffer (`Extra safety`)

These may be added later as separate planning or reconciliation concepts, but they should not shape the first schema and calculator pass.

## Technical Identifier Note

System-defined rows may include an internal stable identifier such as:

- `front_brake_disc`
- `annual_service`
- `battery`

This is the purpose of `technical_key`. It is not user-facing copy. The user-facing text should live in `label`.
