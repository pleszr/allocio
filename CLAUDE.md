# Response Style

Never open responses with filler phrases like "Great question!", "Of course!", "Certainly!", or similar warmups. Start every response with the actual answer. No preamble, no acknowledgment of the question.

Match response length to task complexity. Simple questions get direct, short answers. Complex tasks get full, detailed responses. Never pad responses with restatements of the question or closing sentences that repeat what you just said.

Before any significant task, show me 2-3 ways you could approach this work. Wait for me to choose before proceeding. Exception: when executing an already-approved issue-planner spec or following a defined skill workflow, proceed without re-presenting options.

If you are uncertain about any fact, statistic, date, or piece of technical information: say so explicitly before including it. Never fill gaps in your knowledge with plausible-sounding information. When in doubt, say so.

About me: Roland Plesz / Role: Software Engineer / Background in: Software Engineer/Leadership. Strong in: Python, Insurance. Still learning: python parallel threads. Adjust the depth of every response to match this. Never over-explain what I already know. Never skip context I need.

# Working Principles

1. Ask, don't assume. If something is unclear, ask before writing a single line. Never make silent assumptions about intent, architecture, or requirements.

2. Simplest solution first. Always implement the simplest thing that could work. Do not add abstractions or flexibility that weren't explicitly requested.

3. Don't touch unrelated code. If a file or function is not directly part of the current task, do not modify it, even if you think it could be improved.

4. Flag uncertainty explicitly. If you are not confident about an approach or technical detail, say so before proceeding. Confidence without certainty causes more damage than admitting a gap.

# Allocio

Predictive cost-allocation app for smoothing irregular future vehicle costs into regular savings allocations. MVP scope, solo maintainer, low-ops architecture.

## Modules

- `backend/` — FastAPI API, services, repositories, domain models, and backend tests. See `backend/CLAUDE.md`.
- `frontend/` — React 18 + TypeScript + Vite product app. See `frontend/CLAUDE.md`.
- `backend/alembic/` plus `docker-compose.yml` — PostgreSQL migrations and local database runtime. See `backend/alembic/CLAUDE.md`.
- `docs/` — source-of-truth product, domain, and architecture docs.
- `tools/` — deterministic source-derived code map (`code_map.py`), TypeScript symbol extractor (`ts_symbol_map.mjs`), and PR structural-section verifier (`verify_pr_structural_section.py`).

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

## Git Workflow

- Claude may create feature branches, commit, push, and open PRs autonomously.
- Never commit, merge, or push to `main`. Always work on a feature branch and open a PR. Enforced by `.claude/hooks/block-git-main.py`.
- Run the `pr-prep` skill and get its proposals approved before `gh pr create`. It is audit-only; the git flow itself happens after approval.

## PR Requirements Artifacts

When work starts from an issue-planner requirements file under `.claude/plans/`, the PR body must include that file's contents under a `Requirements` section.

The requirements file is a temporary working artifact. Delete it before the final commit or PR unless Roland explicitly asks to keep it.

The PR body must also include a `Structural Changes` section pasted verbatim from `uv run --python 3.14 python tools/code_map.py --diff main...HEAD --format markdown`, including the `<!-- structural-changes:start -->` / `<!-- structural-changes:end -->` markers. The `structural-diff` CI workflow re-generates that section and fails the PR if the body does not match it exactly.

## Structural Code Map

- `docs/code-map.json` is a generated, deterministic map of backend, frontend, and tooling symbols. Symbol hashes are derived from the parsed AST, so the generator must run under Python 3.14 (the documented runtime) for reproducible output. Always invoke it via `uv run --python 3.14 python tools/code_map.py ...`, never the bare system `python3`.
- `docs/code-map.md` is the generated human-readable architecture overview (a per-area Mermaid module graph plus a symbol outline). It is derived from the same parsed source — deterministic, no LLM. Regenerate it alongside the JSON whenever source changes: `uv run --python 3.14 python tools/code_map.py --write-overview docs/code-map.md && git add docs/code-map.md`.
- Regenerate and re-stage the JSON map whenever backend, frontend, or tooling source changes: `uv run --python 3.14 python tools/code_map.py --write docs/code-map.json && git add docs/code-map.json`.
- Pre-commit hooks (`code-map-staged-check` and `code-map-overview-check` in `.pre-commit-config.yaml`) block commits when staged source and the staged `docs/code-map.json` or `docs/code-map.md` disagree; the `structural-diff` CI workflow re-checks both on pull requests. The hooks only validate — they never regenerate files.
- Review staged structural changes before commit with `uv run --python 3.14 python tools/code_map.py --staged --format markdown`.

## Secret Scanning

- Commits run a gitleaks secret scan via a pre-commit hook (`.pre-commit-config.yaml`); run `pre-commit install` once per clone. The same scan runs in CI (`.github/workflows/gitleaks.yml`).
- If a commit is blocked, treat it as a real finding. Do not bypass with `--no-verify` or `SKIP=gitleaks` without surfacing it to Roland first.

## Agent Guidance

- `AGENTS.md` exists only as a lightweight pointer file for non-Claude agents.
- Use `.claude/memory-structure.md` for explicit memory routing and long-lived instruction updates.
- Specialized workflows such as issue planning, code review, feedback routing, and PR prep live under `.claude/skills/`.
