# Allocio

Allocio is a predictive cost-allocation app that helps users smooth irregular future costs into regular savings allocations. MVP scope, solo maintainer, tens of users expected in the first year.

## Repo layout

- `backend/` — Python 3.13 FastAPI app, managed with `uv`. Alembic migrations in `backend/alembic/`.
- `frontend/` — React 18 + TypeScript + Vite. Built into static assets; served by the Python app or reverse proxy.
- `docs/` — `product-backlog.md`, `technical-stack.md`, `domain-model.md`. Use `domain-model.md` as the source of truth for vehicle-first product entities and defaults.
- `docker-compose.yml` — local Postgres only.

## Tech stack

**Backend:** Python 3.13, FastAPI, SQLAlchemy 2.x, Alembic, psycopg 3 (binary), pydantic-settings. Managed with `uv` (lockfile committed, no `requirements.txt`). Tests with pytest + httpx.

**Frontend:** Two pieces — public marketing site is server-rendered HTML from the Python app (for SEO); product app is React 18 + TypeScript + Vite. No Node-hosted SSR.

**Database:** PostgreSQL 16, self-hosted on the same AWS Lightsail box for MVP. Local dev runs Postgres via `docker compose up -d postgres`.

**Auth:** App-managed email/password, Argon2id hashing, secure HTTP-only cookie sessions. Cognito explicitly deferred until social login is a real requirement.

**Infrastructure:** One AWS Lightsail Linux VM (2 GB RAM / 2 vCPU / 60 GB SSD, ~$12/mo), Ubuntu 24.04 LTS, Caddy reverse proxy, gunicorn + uvicorn workers under systemd, local PostgreSQL on the same host. Backups: nightly `pg_dump` to S3 + Lightsail snapshots.

## MVP constraints (apply to all suggestions)

- Single-VM deployment. Do NOT suggest App Runner, ECS, Lambda, RDS, or Cognito by default — they each push the monthly floor too high for MVP scale.
- Solo maintainer. Optimize for low operational complexity, not for scalability beyond a few hundred users.
- The data model is relational and event-oriented (money logic needs an auditable history). Stay on PostgreSQL.
- Revisit triggers are listed in `docs/technical-stack.md` — only argue for managed services when one of those triggers fires.

## Current domain decisions

- Vehicle is the only first-class `asset.type` in MVP.
- Use `asset` for the tracked thing and `bucket` for the virtual savings container.
- `docs/domain-model.md` is the source of truth for entity shape, defaults, and auditability rules.
- `usage_based_cost` is one adjustable per-kilometer reserve per vehicle, not a per-part table of accrual rows.
- `maintenance_item` may be due by kilometers, by elapsed months, or by whichever threshold is reached first.
- Tire choice is captured on each check-in and used for tire-specific maintenance tracking.
- System-defined cost and maintenance rows should have a user-facing `label` and an internal `technical_key`.
- Default time-based vehicle rows are: seasonal tire change, vehicle inspection, mandatory liability insurance, theft CASCO, parking CASCO, vehicle tax, motorway vignette.
- Default maintenance rows stay on the current simplified set in `docs/domain-model.md`, and `Annual service` is maintenance-only in MVP.
- `Other` should exist by default as a manual maintenance catch-all item, but should not drive recommendation logic by default.
- Defer these workbook concepts for later: vehicle depreciation, alternative vehicle cost, out-of-pocket payments, and extra safety buffer.

## Local development

Three terminals: Postgres (Docker), FastAPI backend, Vite frontend. Full setup in `README.md`. Quick form:

```sh
docker compose up -d postgres
cd backend && uv sync && uv run alembic upgrade head && uv run uvicorn app.main:app --reload
cd frontend && npm install && npm run dev
```

Sanity check: `curl http://localhost:8000/api/greeting` → `{"id":1,"message":"hello world"}`.

## Coding rules

Path-scoped rules live in `.claude/rules/`. They load automatically when you read matching files.

- `.claude/rules/python-style.md` — ruff/pyright config, modern type hints, docstring policy, pytest async config. Loads on `backend/**/*.py`.
- `.claude/rules/python-patterns.md` — newspaper method + stepdown rule, layering (api → service → domain ← repository), OpenAPI docs, Pydantic validators, RESTful naming, service-class + Depends pattern. Loads on `backend/**/*.py`.
- `.claude/rules/python-anti-patterns.md` — observed mistakes to avoid (print() in prod, `uuid` as type, global singletons, deep @patch chains, etc.). Loads on `backend/**/*.py`.

The rules were derived from a full review of `pleszr/skyeGPT/skyegpt-backend` on 2026-05-12 (58 source files, 4,746 LOC) plus explicit user-chosen improvements.

## Docs

- [Product backlog](docs/product-backlog.md)
- [Technical stack and infrastructure](docs/technical-stack.md)
- [Domain model](docs/domain-model.md)
