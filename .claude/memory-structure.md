# Claude Memory Structure

Use this file to route explicit "save this", "remember this", or "update the rules" requests to the right repo-local instruction file.

This repo uses `.claude/` for Claude-facing memory, `.claude/skills/` for specialized workflows, and `CLAUDE.md` files for lightweight repo guidance. It does not use `.github/memory-structure.md`.

## Routing Principles

1. Prefer updating an existing file over creating a new one.
2. Store feedback in the narrowest file that will still be reusable.
3. If the feedback is actually a product or architecture correction, route it to the source-of-truth doc instead of `.claude` memory.
4. If no existing target fits cleanly, propose a new file and ask before creating it.

## Existing Memory Targets

### Repo-wide collaboration guidance

Target:

- `CLAUDE.md`

Use for:

- top-level repo structure
- repo-wide workflow order
- shared constraints that apply across backend, frontend, and database work

### Backend module guidance

Target:

- `backend/CLAUDE.md`

Use for:

- backend-specific workflow and command updates
- backend module boundaries
- backend implementation guidance that is broader than a single Python rule file

### Frontend module guidance

Target:

- `frontend/CLAUDE.md`

Use for:

- frontend-specific workflow and command updates
- frontend module boundaries
- frontend architectural guidance that is broader than a single task-specific skill

### Database and migration guidance

Target:

- `backend/alembic/CLAUDE.md`

Use for:

- Postgres runtime workflow
- Alembic migration workflow
- database-specific command or wiring guidance

### Backend Python style and tooling

Target:

- `.claude/rules/python-style.md`

Use for:

- formatting, linting, typing, docstring, and pytest preferences
- Python syntax preferences
- backend test style preferences

### Backend architecture and implementation patterns

Target:

- `.claude/rules/python-patterns.md`

Use for:

- service and repository layering
- FastAPI route design
- schema validation rules
- dependency injection patterns
- backend naming or orchestration guidance

### Backend anti-patterns and "never do this again" lessons

Target:

- `.claude/rules/python-anti-patterns.md`

Use for:

- bug-prevention rules
- recurring mistakes
- patterns to avoid

### Issue-planning behavior

Target:

- `.claude/skills/allocio-issue-planner/SKILL.md`

Use for:

- how implementation plans should be structured
- what planning output sections are required
- how frontend and backend requirements should be explained
- issue-planning workflow changes

### Code-review behavior

Target:

- `.claude/skills/allocio-code-review/SKILL.md`

Use for:

- review scope rules
- severity definitions
- review checklist updates
- output format changes

### Feedback-routing behavior

Target:

- `.claude/skills/allocio-feedback-memory/SKILL.md`

Use for:

- how explicit memory updates should be handled
- contradiction checking workflow
- approval and patch-preview requirements

### PR-prep workflow behavior

Target:

- `.claude/skills/allocio-pr-prep/SKILL.md`

Use for:

- how pre-PR memory and instruction audits should run
- what files the PR-prep audit should inspect
- how staged-change drift versus existing repo drift should be reported

## Source-Of-Truth Docs, Not Memory Files

Use these when the feedback is correcting product or architecture facts rather than agent behavior:

- `docs/domain-model.md`
- `docs/vehicle-rules.md`
- `docs/product-backlog.md`
- `docs/technical-stack.md`

Examples:

- a domain field should exist or not exist
- a vehicle rule is wrong
- the MVP stack decision changed
- a backlog epic or issue structure is wrong

## No Matching Target

If feedback does not fit the files above:

1. Propose the most likely new file under `.claude/rules/`, `.claude/skills/`, or the relevant `CLAUDE.md`.
2. Explain why the existing files are not a good fit.
3. Ask before creating the new file.

Common future cases that may justify a new file:

- frontend-wide React conventions
- cross-cutting workflow preferences for Claude collaboration
- deployment or ops conventions not covered by backend rules

## Required Workflow For Memory Updates

When handling an explicit memory-update request:

1. Read this file first.
2. Identify one or more candidate targets.
3. Read the target file before proposing an edit.
4. Check for duplicates, contradictions, or obsolete entries.
5. Generalize the feedback if possible so it is reusable.
6. Show the user the exact proposed addition and location.
7. Apply only after approval.
