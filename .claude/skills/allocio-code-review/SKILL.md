---
name: allocio-code-review
description: Use this ALWAYS when asked to review code in this repository. Use when asked to review uncommitted changes, staged diffs, pull request diffs, or pasted code snippets, including code written by another model or agent. Prioritize correctness, regressions, security, FastAPI and SQLAlchemy reliability, React and TypeScript maintainability, and test impact. Do not modify code unless explicitly asked.
---

# Allocio Code Review

## Overview

Review code changes in Allocio with a findings-first review format. Focus on bugs, regressions, security, architecture fit, maintainability, and missing verification rather than rewriting the code.

Read [references/review-context.md](references/review-context.md) before finalizing the first review in a thread.

## Typical Inputs

- `there are uncommitted changes, code review them`
- `review the staged diff`
- `review PR 18`
- `review this snippet: ...`
- `review the code another agent just wrote`

## Scope Rules

1. Review every changed line in the requested scope.
2. Use surrounding code only for context.
3. Rate only the requested scope, not unrelated files or methods.
4. Do not apply code changes directly.
5. If the user asks for a review and the scope is ambiguous, narrow it before reviewing. If the scope is obvious from local changes, use that scope without asking.

## Workflow

1. Identify review mode.
   - `diff mode`: uncommitted, staged, or PR diff
   - `snippet mode`: pasted code only
2. Identify source.
   - `user-authored`
   - `ai-authored`
   - `unknown`
   - If the source is unknown, apply the stricter `ai-authored` validation to risky API or framework usage instead of asking by default.
3. Gather context.
   - Read the diff or snippet first.
   - Read only the minimal surrounding code needed to validate behavior.
   - Read the relevant docs from [references/review-context.md](references/review-context.md) when domain rules, persistence rules, or review standards matter.
4. Run checks in order.
   - Correctness and regression risk
   - Security and privacy
   - Backend reliability for FastAPI, SQLAlchemy, Alembic, and persistence behavior
   - Frontend reliability for React, TypeScript, fetch flow, and user-visible states
   - Idiomatic stack usage
   - Maintainability
   - Orphaned symbols
   - Testing impact
5. Validate claims.
   - If a finding depends on framework or library behavior, verify it against official docs or the current repo code before stating it as a defect.
6. Produce the review.
   - Findings first, ordered by severity.
   - Keep summaries brief.
   - If there are no findings, say that explicitly and mention residual risk or testing gaps.

## Review Checks

### 1. Correctness And Regression Risk

- Does the code do what the changed route, component, service, or migration claims to do?
- Does the change break existing control flow, persistence assumptions, or public API behavior?
- Are domain rules in `docs/domain-model.md` or `docs/vehicle-rules.md` violated?
- For money logic or posting flows, does the change preserve auditability and deterministic reconstruction?

### 2. Security And Privacy

- Missing authn or authz checks
- Request validation gaps
- SQL injection or unsafe query composition
- Leaking secrets, stack traces, or sensitive business data
- Unsafe logging of user input or internal values
- Insecure cookie, session, or password handling if auth code is touched

### 3. Backend Reliability

Apply when reviewing `backend/` changes.

- FastAPI route contract mismatches
- Missing or weak Pydantic validation
- Incorrect dependency injection or service wiring
- Repository and service layer violations
- Broken transaction boundaries or persistence assumptions
- Incorrect Alembic migration shape, unsafe data backfills, or schema drift
- Error mapping that leaks low-level exceptions instead of typed app errors
- Domain changes that fail to preserve future-only edits or event-history rules

### 4. Frontend Reliability

Apply when reviewing `frontend/` changes.

- Wrong component boundaries or state ownership
- Data fetching that can leave stale, partial, or contradictory UI state
- Missing loading, empty, success, or error states
- Form flows that allow invalid submission or unclear recovery
- Assumptions about backend payloads that do not match actual contracts
- React anti-patterns that make the UI harder to reason about than necessary
- New dependencies or architecture that are disproportionate to the current app

### 5. Idiomatic Stack Usage

- Backend: Python 3.13, FastAPI, SQLAlchemy, Alembic, `uv`, and repo layering
- Frontend: React 18, TypeScript, Vite, current lightweight app structure
- Prefer existing repo conventions over introducing new patterns without a strong reason
- Treat claims about best practices as suspect until validated when they rely on unstable framework behavior

### 6. Maintainability

- Clarity, naming, coupling, and complexity
- DRY and KISS
- Whether the code reads at a consistent level of abstraction
- Whether helpers and modules follow the repo’s service, repository, and domain split
- Whether frontend code stays understandable for future feature work

### 7. Orphaned Symbols

- After renames or call-site changes, check whether the old symbol still has consumers.
- Flag dead paths, stale schema fields, and unused exports when they were clearly left behind by the change.

### 8. Testing Impact

- Identify where coverage is now required because behavior changed.
- Prefer behavioral verification over shallow implementation testing.
- Respect the current repo reality:
  - no frontend test runner is configured yet
  - no project-specific backend tests are checked in yet
- If tests are missing, explain the risk concretely rather than asking for generic coverage.

## AI-Authored Code Rules

When the code is AI-authored or possibly AI-authored:

- Verify referenced APIs, classes, config keys, and route shapes actually exist.
- Flag hallucinated framework patterns and nonexistent repo abstractions.
- Treat imported helpers, schema names, env vars, and migration expectations as untrusted until verified.
- Be stricter about overengineering, needless new dependencies, and accidental architecture drift.

## Output Format

Return sections in this order:

1. `Scope`
2. `Findings`
3. `Open questions`
4. `Quality score`

### Findings Format

List findings ordered by severity `P0` to `P3`. Each finding must include:

- `Location` (`path:line` when available)
- `Issue`
- `Why it matters`
- `Recommended fix`

`Recommended fix` explains the change that should be made, but does not apply it.

If there are no findings, say `No findings.` and still include any testing or confidence caveats in `Quality score` or `Open questions`.

## Severity

- `P0`: release-blocking bug, security issue, or data-loss risk
- `P1`: high-impact correctness or reliability issue
- `P2`: medium-impact maintainability, performance, or testability issue
- `P3`: minor clarity or style issue

## Scoring Rubric

- `1-3`: unsafe or fundamentally incorrect
- `4-5`: major issues, not ready
- `6-7`: workable with important fixes needed
- `8-9`: solid, minor issues
- `10`: production-ready with no material concerns found

## Example Triggers

- `Use $allocio-code-review to review the uncommitted changes in this repo.`
- `Use $allocio-code-review to review the staged backend changes for correctness and migration risk.`
- `Use $allocio-code-review to review this React snippet and call out state-management problems.`
