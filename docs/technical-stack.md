# Allocio Technical Stack And Infrastructure

Status: Chosen for MVP v1
Last updated: 2026-07-07

## Purpose

This document records the current stack and infrastructure choice for the MVP so product, engineering, and deployment decisions stay aligned.

This is the source of truth for:

- frontend stack
- backend stack
- database choice
- AWS hosting shape
- operational boundaries for the MVP

## Product Constraints Driving The Decision

- public marketing site with SEO-heavy pages
- web-only MVP
- expected scale in the first year is tens of users
- solo maintainer
- Python is the strongest implementation language
- low monthly infrastructure budget
- the product needs auditable, relational event history for money logic

## Chosen MVP Stack

### Frontend

- Public marketing site: server-rendered HTML templates from the Python app
- Product app: React + TypeScript
- Build tool for the product app: Vite

Reasoning:

- The public site needs SEO, so it should render as HTML on first load
- The authenticated product app is dashboard and workflow heavy, which is a good fit for React
- This keeps React where it adds value without forcing the entire product into a Node-hosted frontend stack

### Backend

- Python 3.14
- FastAPI
- SQLAlchemy 2.x
- Alembic for schema migrations

Reasoning:

- FastAPI fits the API and form-driven workflow well
- Python matches the strongest implementation skill in the project
- SQLAlchemy and Alembic keep the data layer portable between local development and future infrastructure changes

### Database

- PostgreSQL 16
- Hosted on the same AWS Lightsail instance as the application for MVP

Reasoning:

- PostgreSQL is the chosen database for the product
- The data model is relational and event-oriented, which fits PostgreSQL well
- Self-hosting PostgreSQL on the same box is the cost-controlled compromise for MVP
- Managed database options push the monthly floor too high for the current stage

### Auth

- MVP launch: Google Sign-In via server-side OAuth 2.0 Authorization-Code flow (Authlib), backed by a `users` table (issue #62)
- Session model: signed HTTP-only `SameSite=Lax` cookie (Starlette `SessionMiddleware` + `itsdangerous`); no bearer tokens, same-origin app and API
- Dev/e2e bypass: `AUTH_DISABLED=true` returns a synthetic dev user with no Google round-trip; when auth is enabled, missing `GOOGLE_CLIENT_ID`/`GOOGLE_CLIENT_SECRET`/`SESSION_SECRET` fail loud at startup
- Setup guide: `docs/google-auth-setup.md`

Reasoning:

- Google Sign-In removes password storage/hashing from MVP scope while keeping a secure baseline
- Server-side flow keeps tokens off the client; only a signed session cookie is exposed
- Revisit Cognito when Apple Sign-In or broader multi-provider identity requirements become real product needs

### Background Work

- Minimal host-level scheduled jobs for MVP
- Use cron or systemd timers for:
  - database backups
  - reminder or maintenance jobs if needed later

Reasoning:

- The MVP does not justify a queue or worker platform yet
- Keep background work simple until the product proves a real need for more infrastructure

## Chosen AWS Infrastructure

### Runtime Shape

- One Linux Lightsail instance
- One reverse proxy in front of the app
- One local PostgreSQL service on the same instance
- One FastAPI application service

Recommended operating system:

- Ubuntu 24.04 LTS

Recommended reverse proxy:

- Caddy or Nginx

Default recommendation:

- Caddy for simpler HTTPS and lower setup overhead on a solo-managed box

### Instance Size

Recommended starting point:

- Lightsail Linux/Unix instance with 2 GB RAM, 2 vCPU, and 60 GB SSD

Pricing note:

- AWS Lightsail pricing on May 12, 2026 lists the public IPv4 Linux/Unix 2 GB bundle at $12/month

Why this size:

- PostgreSQL on the same host makes the smaller 0.5 GB and 1 GB plans too tight for a comfortable production setup
- 2 GB is the minimum reasonable shape for app plus database on one box

## Storage Layout

Store data in these categories:

- PostgreSQL data directory on the instance disk
- application logs on the instance
- backups in S3
- future uploaded files in S3, not on the local instance disk

Reasoning:

- the instance disk is acceptable for the live database in MVP
- S3 should be the durable off-box backup target
- user-uploaded or generated files should not become coupled to the lifecycle of the app server

## Backup And Recovery Baseline

Minimum required setup:

- nightly `pg_dump`
- upload backup artifacts to S3
- daily or regular Lightsail snapshots
- a written restore procedure
- at least one tested restore before launch

Important boundary:

- snapshots are not enough on their own
- the MVP should have both database-level backups and instance-level snapshots

## Deployment Shape

Recommended MVP deployment model:

- FastAPI app served by `gunicorn` with `uvicorn` workers
- systemd-managed services for the app and PostgreSQL
- reverse proxy terminates HTTPS and forwards requests to the app
- React product app built into static assets and served by the Python app or reverse proxy

Reasoning:

- This keeps the runtime simple on a single VM
- It avoids introducing ECS, App Runner, or a container platform before the product needs one
- It is easier to debug and cheaper to run at this stage

## What We Are Explicitly Not Choosing For MVP

- App Runner + RDS
- ECS Fargate + RDS
- Lambda-first backend
- managed PostgreSQL
- Node-hosted SSR frontend as the primary app runtime

Reasoning:

- they either cost too much for the current stage
- or they add platform complexity that is not justified by expected traffic and team size

## Revisit Triggers

Revisit this architecture when any of the following becomes true:

- the app needs more than one application instance
- PostgreSQL resource pressure appears on the Lightsail box
- background jobs become frequent or business-critical
- social login becomes a launch requirement
- file storage becomes a first-class product capability
- traffic moves beyond the current low-volume assumption

At that point likely changes are:

- move PostgreSQL to RDS
- move app runtime to App Runner or ECS
- evaluate Cognito for broader identity support
- move any file handling fully to S3-backed workflows

## Developer Tooling

- A deterministic code map (`tools/code_map.py`, Python standard library only) generates `docs/code-map.json`, renders structural PR diffs (a badge-driven, layer-grouped Change Map), and writes a self-contained interactive architecture overview (`docs/code-map.html`: a per-area columnar module graph with hover, layer filtering, click-through, and a PR changed-only mode).
- TypeScript/TSX symbol extraction (`tools/ts_symbol_map.mjs`) reuses the frontend `typescript` dependency via the TypeScript compiler API; it adds no new runtime dependency.
- End-to-end workflow coverage is two-layered: a fast in-process API smoke test (`backend/tests/test_workflow_e2e.py`) replays the browser's request sequence and runs as a pre-commit hook, and a Playwright browser suite (`frontend/e2e/`, `@playwright/test`, TypeScript) drives the full stack on demand (`npm run e2e`) against a throwaway `allocio_e2e` database. Playwright is a local dev-only dependency; it is not run in CI and not part of the deployed runtime.
- These are development and review tools, not part of the deployed runtime stack.

## Where This Decision Lives

Use this file as the source of truth for the MVP stack choice.

Documentation placement rule:

- `README.md` should stay short and point to key docs
- `docs/technical-stack.md` should hold the stack and infrastructure decision
- future major architectural decisions can move into `docs/adr/` as formal ADRs if the repo grows
