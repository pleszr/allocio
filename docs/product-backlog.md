# Allocio Product Backlog

Status: Draft v1
Last updated: 2026-07-26

## Product Frame

Allocio is a predictive cost-allocation app that helps users self-insure against irregular future expenses.

Core principle:

Convert irregular, hard-to-time costs into small, regular allocations so the user can build a predictable savings habit and have funds ready when expenses arrive.

What Allocio is:

- A future-cost smoothing tool
- A virtual bucket planner for real-life assets and responsibilities
- A monthly check-in workflow for reconciling time-based and usage-based accruals

What Allocio is not:

- A general expense tracker
- A bookkeeping system
- A bank-account-first budgeting app

## Product Read From The Design Handoff

The handoff already expresses a coherent MVP:

- Workspace overview with tracked buckets
- Per-entity dashboard
- Cost editor for time-based, usage-based, and maintenance inputs
- Monthly check-in workflow
- New bucket creation wizard

The strongest designed flow is the vehicle journey. The underlying model is generic, but the detailed math and review flow are currently most concrete for cars.

## MVP Recommendation

Launch v1 around one deeply solved use case:

- Vehicle ownership only

Keep the data model generic enough to support:

- property
- pet
- bike
- boat
- child-related recurring buckets

Out of scope for MVP:

- bank sync
- full expense tracking
- automated transaction import
- shared household collaboration
- advanced forecasting and scenario simulation

Operational note:

- Users will move real money outside the app, for example into Revolut sub-accounts
- Allocio remains the planning and accrual layer, not the money-moving layer

## Locked Product Decisions

### PM-01 Terminology

Priority: P0

Decision:

- Use `asset` for the thing being tracked
- Use `bucket` for the virtual savings container
- Keep `entity` as an internal implementation term only if needed

### PM-02 Check-In Model

Priority: P0

Decision:

- Use a monthly accrual workflow
- The app calculates what should be added to the bucket for the elapsed period
- The bucket is virtual
- Allocio does not integrate with real money accounts in MVP
- Users move real funds separately if they want to mirror the bucket in a bank or Revolut sub-account

### PM-03 Scope Of Non-Vehicle Types

Priority: P0

Decision:

- Vehicle is the only first-class MVP flow
- Non-vehicle assets are out of MVP as full experiences

### PM-04 Expense Logging Boundaries

Priority: P0

Decision:

- Users can log predefined expenses tied to modeled costs
- Users can also log `Other` items with a free-text comment for smaller or miscellaneous costs
- `Other` is a manual catch-all, not an auto-categorization feature
- Recommendations or automatic promotion of `Other` items into real categories are out of MVP

## Prioritized Backlog

### P0 Product And Domain Foundation

#### PM-05 Canonical Domain Model

Type: Product + Engineering

Define the base model for:

- asset
- virtual bucket
- time-based cost
- usage-based cost
- optional maintenance item
- check-in
- allocation event
- expense event

Done when:

- each concept has a clear definition
- relationships between records are explicit
- future calculations can be reproduced from stored events

#### PM-06 Allocation Rules Spec

Type: Product + Engineering

Write the source-of-truth calculation spec for:

- daily accrual from time-based costs
- variable accrual from usage-based costs
- maintenance status thresholds
- effect of cost edits on future versus past periods
- bucket balance updates after check-in

Done when:

- the rules are written as deterministic formulas
- sample scenarios can be worked by hand
- engineering can implement without inventing business logic

#### PM-07 Information Architecture

Type: Product + Design

Lock the top-level app structure:

- overview
- asset detail
- costs
- check-in
- new bucket

Done when:

- navigation names are final
- the relationship between overview, bucket, and check-in is unambiguous

### P1 MVP User Flows

#### PM-08 Overview Screen

Type: Design + Frontend

Build the workspace overview that shows:

- all tracked buckets
- current balances
- next allocation signal
- alerts requiring attention

Done when:

- users can understand portfolio state in one glance
- users can jump to an item or create a new one

#### PM-09 New Bucket Wizard

Type: Product + Design + Frontend

Build the setup flow for creating a new tracked item with:

- vehicle metadata
- suggested starter costs
- review before creation

Done when:

- a first-time user can create a vehicle bucket without prior training
- the output includes enough data to power future accruals

#### PM-10 Costs Editor

Type: Product + Frontend

Support editing:

- time-based costs
- usage-based costs
- maintenance items
- `Other` manual cost items with comment

Done when:

- users can add, edit, and remove costs
- derived daily or per-unit values are visible
- copy makes clear that future allocations change while past history stays fixed

#### PM-11 Monthly Check-In

Type: Product + Design + Frontend

Build the core monthly workflow:

- enter usage
- review time-based accrual
- review usage-based accrual
- review the configured manual-extra allocation for the elapsed period
- review each expense's bucket-covered and out-of-pocket portions
- explicitly confirm any derived one-time out-of-pocket amount
- confirm the period result

Done when:

- the user can understand exactly why the suggested net bucket change exists
- confirming closes the current cycle and records an auditable event

#### PM-12 Item Dashboard

Type: Design + Frontend

Build the per-item detail view with:

- current bucket balance
- recent trend
- average posted allocation signal
- vehicle age and time tracked in the app
- trailing 12-month average monthly cost from allocations and paid-out-of-pocket amounts
- nearest active kilometer-based maintenance item and its remaining distance
- maintenance alerts
- recent activity

Done when:

- users can quickly understand the non-negative bucket balance and its recent movements

#### PM-13 Activity History

Type: Product + Frontend

Add a clear event history for:

- allocations
- expenses, including their bucket-covered and out-of-pocket funding split
- cost changes
- check-ins

Done when:

- users can reconstruct how the balance changed over time

### P1 Platform And Data

#### PM-14 Persistence Layer

Type: Engineering

Choose and implement the local persistence model for:

- tracked items
- costs
- check-ins
- expenses
- balances

Done when:

- the app survives reloads
- stored events support deterministic recalculation

#### PM-15 Calculation Engine

Type: Engineering

Implement the core calculator as a separate domain layer, not inline UI math.

Done when:

- accruals can be tested independently of the UI
- the same logic powers wizard estimates, dashboard summaries, and check-ins

#### PM-16 Seed Data And Demo Mode

Type: Engineering + Product

Create realistic starter data to support:

- empty state development
- design validation
- future demos

Done when:

- the product can be shown end-to-end without manual setup

#### PM-17 Tests For Money Logic

Type: Engineering

Add coverage for:

- time-based accrual formulas
- usage-based accrual formulas
- cost edits across time boundaries
- bucket balance calculations
- maintenance status thresholds

Done when:

- core money logic has regression protection

### P2 Expansion

#### PM-18 Additional Item Templates

Type: Product + Design

Expand first-class support beyond vehicles to:

- property
- pet
- bike
- boat

Current increment:

- Issue #118 adds property as a built-in creation template with recurring house costs and an editable monthly safety buffer.
- Property-specific profile, maintenance, and dashboard experiences remain deferred.

#### PM-19 Reminder System

Type: Product + Engineering

Add monthly reminders for pending check-ins and overdue maintenance review.

#### PM-20 Scenario Planning

Type: Product

Let users explore how cost changes or higher usage would change future allocations.

#### PM-21 Smarter Maintenance Modeling

Type: Product + Engineering

Support advanced maintenance derived from replacement intervals and replacement cost assumptions.

## Suggested First GitHub Issue Batch

When we turn this into repo issues, the first batch should be:

1. Define canonical asset and bucket data model
2. Write vehicle accrual and posting rules spec
3. Build calculation engine
4. Add money-logic regression tests
5. Build app shell and navigation
6. Build vehicle bucket creation wizard
7. Build time-based cost management
8. Build usage-based cost management
9. Build maintenance item management
10. Build `Other` manual item entry with comment
11. Build monthly vehicle check-in flow
12. Build workspace overview screen
13. Build vehicle dashboard
14. Add persistence and event history

## Proposed GitHub Issue Structure

Milestone:

- `MVP - Vehicle`

Recommended label families:

- `area:domain`
- `area:setup`
- `area:costs`
- `area:check-in`
- `area:overview`
- `area:history`
- `type:product`
- `type:frontend`
- `type:backend`
- `priority:p0`
- `priority:p1`

Recommended epics:

### Epic 1: Core vehicle asset, bucket, and accrual model

Purpose:

- Lock the source of truth for the vehicle-first MVP before UI work starts diverging

Child issues:

1. Define canonical data model for asset, bucket, cost, maintenance item, check-in, allocation event, and expense event
2. Write deterministic vehicle accrual and posting rules spec
3. Implement calculation engine for time-based and usage-based accruals
4. Add regression tests for money logic and balance reconstruction

### Epic 2: Vehicle bucket setup

Purpose:

- Make first-time setup fast and trustworthy for a vehicle owner

Child issues:

1. Build app shell and top-level navigation
2. Build vehicle bucket creation wizard
3. Add suggested starter costs for vehicles
4. Add initial empty states and seed/demo data

### Epic 3: Cost management

Purpose:

- Let users define the rules that drive future accruals without turning the app into bookkeeping software

Child issues:

1. Build time-based cost CRUD
2. Build usage-based cost CRUD
3. Build maintenance item CRUD
4. Build `Other` manual item entry with comment
5. Make future-only impact of cost edits explicit in the UI

### Epic 4: Monthly check-in

Purpose:

- Deliver the main habit loop of the product

Child issues:

1. Build monthly vehicle check-in flow
2. Support odometer entry and usage delta calculation
3. Review time-based accrual, usage-based accrual, expenses, and net bucket change
4. Confirm and post monthly accrual event

### Epic 5: Overview, dashboard, and history

Purpose:

- Help users understand the current bucket position, trust the math, and inspect what happened over time

Child issues:

1. Build workspace overview screen
2. Build vehicle dashboard
3. Persist assets, buckets, and event history
4. Show activity history and balance reconstruction

## Issue Template Guidance

Each GitHub issue should contain:

- `Why`
- `Scope`
- `Acceptance criteria`
- `Out of scope`
- `Dependencies`

Acceptance criteria should always be behavioral and testable, especially for:

- accrual formulas
- monthly posting rules
- future-only effect of cost edits
- bucket balance reconstruction from events

## Notes For Backlog Grooming

- Keep the product centered on future-cost smoothing
- Reject any feature that drifts into generic expense tracking unless it directly supports the bucket model
- Prefer one deeply trustworthy workflow over many shallow templates
- Auditability matters because users need to trust the math
