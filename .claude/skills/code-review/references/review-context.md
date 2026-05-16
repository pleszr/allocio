# Allocio Review Context

Read this file before finalizing the first review in a thread.

## Repo Docs To Check

- `CLAUDE.md`
- `.claude/rules/python-style.md`
- `.claude/rules/python-patterns.md`
- `.claude/rules/python-anti-patterns.md`

Read these when the reviewed change touches product rules or persistence semantics:

- `docs/technical-stack.md`
- `docs/domain-model.md`
- `docs/vehicle-rules.md`

## Stack

- Frontend: React 18 + TypeScript + Vite
- Backend: Python 3.13 + FastAPI + SQLAlchemy 2.x + Alembic
- Database: PostgreSQL 16
- Deployment target: single Lightsail VM for MVP

Review implications:

- Do not judge the code against Lambda or Java conventions; those are out of scope here.
- Do judge backend changes against the current FastAPI -> service -> repository/domain structure.
- Do judge frontend changes against the current lightweight React app structure instead of assuming a larger SPA stack.

## Diff Collection

Prefer the narrowest tool that matches the requested scope.

### Local changes

- `git diff --stat`
- `git diff`
- `git diff --cached`
- `git status --short`

### PR review

- Use GitHub CLI if available for PR metadata or diff context.
- If PR access is not available, review the provided patch or the local branch diff.

## Review Hotspots

### Backend

Check these especially hard:

- route definitions in `backend/app/api/`
- schema contracts in `backend/app/api/schemas/`
- dependency wiring in `backend/app/services/dependencies.py`
- orchestration logic in `backend/app/services/`
- query and persistence behavior in `backend/app/repository/`
- domain and event-history assumptions in `backend/app/domain/`
- schema changes under `backend/alembic/`

Backend-specific risks to flag:

- layering violations
- weak validation
- missing typed exceptions
- bad migration safety
- incorrect future-only edit behavior
- event-history or balance reconstruction breakage

### Frontend

Check these especially hard:

- state ownership
- data fetching and submission flow
- loading and error handling
- assumptions about backend payloads
- overengineering relative to the current app

Frontend-specific risks to flag:

- hidden stale state
- missing user-visible error handling
- fetch flows that ignore non-2xx responses
- unnecessary new libraries or global state

## Current Testing Reality

As of 2026-05-15:

- no frontend test runner is configured yet
- no project-specific backend tests are checked in yet

Review implications:

- missing automated coverage is often a real risk, but do not invent test commands that the repo cannot run
- if you recommend new tests, name the file area and behavior to cover

## Output Expectations

- Findings first
- Use file and line references when available
- Do not pad the review with praise
- If there are no findings, say so plainly and mention any remaining confidence limits
