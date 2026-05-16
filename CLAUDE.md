# Allocio

Predictive cost-allocation app for smoothing irregular future vehicle costs into regular savings allocations. MVP scope, solo maintainer, low-ops architecture.

## Modules

- `backend/` — FastAPI API, services, repositories, domain models, and backend tests. See `backend/CLAUDE.md`.
- `frontend/` — React 18 + TypeScript + Vite product app. See `frontend/CLAUDE.md`.
- `backend/alembic/` plus `docker-compose.yml` — PostgreSQL migrations and local database runtime. See `backend/alembic/CLAUDE.md`.
- `docs/` — source-of-truth product, domain, and architecture docs.

## Source Of Truth

- `docs/domain-model.md` — canonical vehicle-first entity model, defaults, and auditability rules
- `docs/vehicle-rules.md` — accrual formulas, maintenance thresholds, and check-in behavior
- `docs/technical-stack.md` — stack and infrastructure decisions
- `docs/product-backlog.md` — backlog structure and issue decomposition

## MVP Constraints

- Single Lightsail VM by default. Do not suggest App Runner, ECS, Lambda, RDS, or Cognito unless a documented revisit trigger has fired.
- Python-first backend, React/Vite product app, PostgreSQL for relational and auditable money logic.
- Vehicle is the only first-class `asset.type` in MVP.
- Use `asset` for the tracked thing and `bucket` for the virtual savings container.

## Build And Run

See the referenced module `CLAUDE.md` files for exact commands. The normal local development and full-stack verification order is:

1. Start Postgres.
2. Apply database migrations.
3. Start the backend.
4. Start the frontend.
5. Optional: run backend tests and a frontend production build.

## Agent Guidance

- `AGENTS.md` exists only as a lightweight pointer file for non-Claude agents.
- Use `.claude/memory-structure.md` for explicit memory routing and long-lived instruction updates.
- Specialized workflows such as issue planning, code review, feedback routing, and PR prep live under `.claude/skills/`.
