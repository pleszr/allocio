---
name: allocio-issue-planner
description: Use when the user asks to turn an Allocio GitHub issue, backlog item, or rough feature brief into an execution-ready implementation spec for another agent. Best for requests like "plan GitHub issue 23", "I want to work issue 19", or "draft frontend and backend requirements for this feature". Produces repo-specific requirements with separate frontend and backend sections, with frontend guidance written in more detail and in more explanatory React terms.
---

# Allocio Issue Planner

## Overview

Create execution-ready implementation specs for Allocio work. The output is a prompt or requirement set for another agent to execute, not the implementation itself.

Read [references/repo-context.md](references/repo-context.md) before finalizing the first plan in a thread.

## When To Use

- The user wants to plan work from a GitHub issue number.
- The user wants a feature brief converted into actionable frontend and backend requirements.
- The user wants acceptance criteria tightened so another agent can implement without clarification loops.
- The user wants extra explanation on the frontend side because the React architecture is not obvious.

Do not use this skill for direct implementation unless the user explicitly asks for planning only. Do not invent product behavior when the issue, docs, or code do not support it.

## Workflow

1. Gather issue context.
   - If the user gives a GitHub issue number, inspect it with `gh issue view <number>`.
   - If the issue clearly depends on a parent epic or linked issue, inspect that context too. Use it to shape naming and boundaries, not to silently widen scope.
2. Gather repo context.
   - Read `CLAUDE.md`.
   - Read only the relevant docs from [references/repo-context.md](references/repo-context.md).
   - Inspect the relevant frontend and backend modules before writing requirements.
3. Validate the ask.
   - Determine whether the task is frontend-only, backend-only, or cross-cutting.
   - Verify any library-specific behavior against official docs when it materially affects the plan.
   - Ask targeted follow-up questions only when a missing decision would change architecture, schema shape, API contract, or user-visible behavior.
4. Write the plan.
   - Return the sections in the exact order defined below.
   - Always call out both frontend and backend, even when one side is explicitly unchanged.
5. Final pass.
   - Remove vague terms such as "as needed", "if applicable", or "handle errors appropriately".
   - Replace placeholders with exact filenames, modules, routes, commands, and observable evidence.

## Frontend Planning Rules

- Frontend requirements must be more detailed than backend requirements.
- Write frontend requirements in plain language for someone who is still getting comfortable with React.
- Always explain:
  - the user-visible flow
  - the file or module ownership
  - the component boundaries
  - which component owns which state
  - how data is fetched or submitted
  - loading, empty, success, and error states
  - form validation and submission flow when forms exist
  - how the UI depends on current or planned backend contracts
- If you mention a React concept that is not obvious, add a short explanation of why it belongs there.
- Prefer the current lightweight app structure. Do not introduce routing, global state libraries, data-fetching libraries, or new UI frameworks unless the issue explicitly requires them.
- If the issue is backend-only, say so explicitly in the frontend section and explain why no frontend change is required.

## Backend Planning Rules

- Call out exact API routes, request and response schemas, service methods, repository changes, domain model updates, and migration work when relevant.
- Preserve the repo layering:
  - API router -> service -> repository/domain
- Reuse `Depends` providers in `backend/app/services/dependencies.py` when new services are introduced.
- Mention validation rules, error paths, and persistence or auditability implications.
- If a database change is required, name the affected model modules and the Alembic migration work.
- If the issue is frontend-only, say so explicitly in the backend section and explain why no backend change is required.

## Output Contract

Return sections in this exact order:

1. `Skills and rules`
2. `Goal`
3. `Scope`
4. `Frontend Functional Requirements`
5. `Backend Functional Requirements`
6. `Retry / Error Semantics`
7. `Infra Requirements`
8. `Tests`
9. `Out of Scope`
10. `Acceptance Criteria`

### Section Rules

- `Skills and rules`
  - Name the relevant repo instructions, docs, and skills the executing agent must use.
  - If backend files are in scope, explicitly call out `CLAUDE.md` and the Python rules under `.claude/rules/`.
- `Goal`
  - One outcome sentence.
- `Scope`
  - Exact files or modules allowed to change.
- `Frontend Functional Requirements`
  - Numbered, testable requirements grouped by file or module headings.
  - Always include this section. If empty, write `No frontend changes required.` and explain why.
- `Backend Functional Requirements`
  - Numbered, testable requirements grouped by file or module headings.
  - Always include this section. If empty, write `No backend changes required.` and explain why.
- `Retry / Error Semantics`
  - Distinguish recoverable failures, non-recoverable failures, and user-visible error handling.
- `Infra Requirements`
  - Call out routes, environment variables, auth/session implications, static asset build impacts, and DB migration or deployment implications.
- `Tests`
  - State the minimum required coverage.
  - If no new tests are required, give a concrete rationale instead of omitting the section.
- `Acceptance Criteria`
  - Use exact commands and observable evidence.

## Acceptance Criteria Rules

- Use repo-real commands from [references/repo-context.md](references/repo-context.md).
- For frontend work, include `cd frontend && npm run build`.
- For backend work, include `cd backend && uv run pytest`.
- When DB-backed verification matters, include `docker compose up -d postgres` before backend verification commands.
- Always include a staging step and require evidence that all intended files are staged without committing them.
- Do not require commands or tools that the repo does not support today.
- If the change spans frontend and backend, include verification for both sides.

## Ambiguity Rules

- Ask follow-up questions when missing information would change:
  - the domain behavior
  - the persistence model
  - the API contract
  - the component structure
  - the issue scope
- Do not ask questions that can be answered by reading the issue, docs, or code.
- Do not broaden scope beyond the issue the user asked to plan.

## Example Triggers

- `Use $allocio-issue-planner to plan GitHub issue 23.`
- `Use $allocio-issue-planner to turn issue 19 into an execution-ready prompt with detailed frontend guidance.`
- `Use $allocio-issue-planner to split this feature brief into explainy frontend requirements and backend requirements.`
