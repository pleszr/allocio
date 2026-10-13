# Allocio Database And Migrations

Database runtime and migration guidance for Allocio. PostgreSQL 16 in local development, wired into the backend through SQLAlchemy and Alembic.

## Scope

- `docker-compose.yml` — local Postgres runtime
- `backend/app/config.py` — database URL settings
- `backend/app/db.py` — SQLAlchemy engine, base, and session factory
- `backend/alembic/env.py` — Alembic configuration and metadata registration
- `backend/alembic/versions/` — schema migrations

## Commands

```sh
docker compose up -d postgres
cd backend && uv run alembic upgrade head
docker compose down
docker compose down -v
```

## Current Wiring

- Local default database URL: `postgresql+psycopg://allocio:allocio@localhost:5432/allocio`
- Local Postgres container name: `allocio-postgres`
- Parallel checkouts may override the Compose container, host port, and database with
  `POSTGRES_CONTAINER_NAME`, `POSTGRES_PORT`, and `POSTGRES_DB`; point `DATABASE_URL` at the same
  isolated database before running migrations.
- Alembic reads the database URL from `app.config.settings`.
- Alembic uses `app.db.Base.metadata` and currently imports model modules in `env.py` so their tables are registered.

## Rules

- Schema changes must ship with matching Alembic migration changes.
- When adding new SQLAlchemy models, ensure Alembic can see their metadata during migration runs.
- Keep database changes aligned with `docs/domain-model.md` and `docs/vehicle-rules.md`, especially for auditability and future-only edit behavior.
- Stay on PostgreSQL for MVP. Do not propose managed database services by default.
