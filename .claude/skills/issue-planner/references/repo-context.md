# Allocio Repo Context

Read this file before finalizing the first plan in a thread.

## Source Of Truth Docs

Read these unless the issue is obviously unrelated:

- `CLAUDE.md`
- `docs/technical-stack.md`

Read these when the issue touches vehicle rules, money logic, persistence shape, or user-facing domain terminology:

- `docs/domain-model.md`
- `docs/vehicle-rules.md`

Read this when the issue is about scope, decomposition, or how repo issues are written:

- `docs/product-backlog.md`

## Stack And Constraints

- Frontend product app: React 18 + TypeScript + Vite
- Public marketing site: server-rendered HTML from the Python app when it exists
- Backend: Python 3.13 + FastAPI + SQLAlchemy 2.x + Alembic
- Backend toolchain: `uv`, `pytest`
- Database: PostgreSQL 16
- Deployment target: single AWS Lightsail VM for MVP, not managed AWS services by default
- Product scope: vehicle-first MVP

Implications for planning:

- Do not default to React Router, Redux, TanStack Query, form frameworks, or design systems unless the issue clearly needs them.
- Do not default to App Runner, ECS, Lambda, RDS, or Cognito for MVP plans.
- Keep frontend structure simple and aligned with the current codebase.
- Keep backend changes inside the existing router -> service -> repository/domain layering.

## Code Map

### Frontend

- `frontend/src/main.tsx`
  - React bootstrap
- `frontend/src/App.tsx`
  - Current product app root
  - Shows the existing fetch-and-render pattern
- `frontend/package.json`
  - Available frontend commands

### Backend

- `backend/app/main.py`
  - FastAPI app composition and exception handlers
- `backend/app/api/`
  - HTTP routers
- `backend/app/api/schemas/`
  - Request and response schema modules
- `backend/app/services/`
  - Use-case orchestration and dependency providers
- `backend/app/repository/`
  - Persistence access
- `backend/app/domain/`
  - Domain and persistence models
- `backend/alembic/`
  - Schema migrations
- `backend/pyproject.toml`
  - Backend dependencies and test tooling

## Existing Repo Conventions

- Backend Python files are governed by `CLAUDE.md` and `.claude/rules/python-*.md`.
- Backend plans should preserve the current layering:
  - router -> service -> repository/domain
- New backend service classes should use `Depends` providers in `backend/app/services/dependencies.py`.
- Plans should prefer extending current patterns over introducing new architecture.
- Frontend plans should explain component and state decisions in plain language, not only in React shorthand.

## Verification Commands

Use only commands that exist in this repo today.

### Database

- `docker compose up -d postgres`

### Backend

- `cd backend && uv sync`
- `cd backend && uv run alembic upgrade head`
- `cd backend && uv run pytest`
- `cd backend && uv run uvicorn app.main:app --reload`

### Frontend

- `cd frontend && npm install`
- `cd frontend && npm run build`
- `cd frontend && npm run dev`

### Git Evidence

- `git add <changed-files>`
- `git diff --cached --name-only`
- `git status --short`

## Current Testing Reality

As of 2026-05-15:

- There are no project-specific backend test files checked into the repo yet.
- There is no frontend test runner configured yet.

Implications for planning:

- Do not invent frontend test commands.
- If a plan requires new tests, specify where they should be added and still keep the runnable acceptance commands grounded in the current toolchain.
- When no new tests are required, say why explicitly.

## GitHub Issue Guidance

`docs/product-backlog.md` says GitHub issues should contain:

- `Why`
- `Scope`
- `Acceptance criteria`
- `Out of scope`
- `Dependencies`

When an issue is thin, use that structure to identify what is missing. Do not quietly fill product gaps with guesses.
