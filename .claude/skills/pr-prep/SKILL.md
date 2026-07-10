---
name: pr-prep
description: Mandatory before opening a PR in this repository (before `gh pr create`). Audits staged changes and proposes updates to repo-local instruction files such as `CLAUDE.md`, `.claude/rules/*.md`, and `.claude/memory-structure.md`. Also flags skill drift and broader documentation drift. Does not auto-write anything; it presents proposed changes for user approval first.
---

# Allocio PR Prep

## Overview

Audit staged changes before opening a PR and check whether the repository's instruction files still match the codebase. This skill proposes memory and documentation maintenance; it does not write changes until the user approves them.

This audit is the mandatory step between committing on a feature branch and running `gh pr create` (see `CLAUDE.md` Git Workflow). The skill itself stays audit-only: the surrounding workflow performs the push and PR creation after the proposals here are approved.

Read `.claude/memory-structure.md` first.

## When To Use

- Before opening a PR
- When staged changes may have invalidated instructions or conventions
- When files, modules, routes, or public helpers were renamed, added, or removed
- When you suspect repo-local instructions have drifted from the actual codebase

Use this skill to propose changes only. Do not auto-edit any instruction or doc file in this workflow.

## Workflow

### 1. Gather staged changes

Run:

```bash
git diff --staged --stat
git diff --staged --name-only
git diff --staged
```

Then run the deterministic structural checks. These are required before commit. The generator must run under Python 3.14, so always invoke it via `uv run --python 3.14`:

```bash
uv run --python 3.14 python tools/code_map.py --check docs/code-map.json
uv run --python 3.14 python tools/code_map.py --check-overview docs/code-map.md
uv run --python 3.14 python tools/code_map.py --staged --format markdown
uv run --python 3.14 python tools/code_map.py --diff main...HEAD --format markdown
```

- `--check docs/code-map.json` must pass. If it fails, run `uv run --python 3.14 python tools/code_map.py --write docs/code-map.json && git add docs/code-map.json` and re-stage before continuing.
- `--check-overview docs/code-map.md` must pass. If it fails, run `uv run --python 3.14 python tools/code_map.py --write-overview docs/code-map.md && git add docs/code-map.md` and re-stage.
- `--staged --format markdown` is the staged-change review surface: read it to confirm the staged symbol, route, import, and component changes match intent before committing.
- `--diff main...HEAD --format markdown` produces the PR structural section. Capture its full output, including the `<!-- structural-changes:start -->` / `<!-- structural-changes:end -->` markers.

Identify:

- new files, modules, classes, or directories
- deleted or renamed files or symbols
- new shared helpers or public entry points
- route or schema changes
- new patterns that may deserve convention updates
- technology or tooling version changes

### 2. Audit the memory map

- Read `.claude/memory-structure.md`.
- Verify that every memory or instruction file it names still exists.
- Check whether staged changes introduced a new instruction-bearing file that should be referenced there.
- Check whether existing routing guidance has become misleading because the codebase or skill set changed.

### 3. Audit repo instruction files

Audit these first because they are the closest equivalent to module instructions in this repository:

- `CLAUDE.md`
- `backend/CLAUDE.md`
- `frontend/CLAUDE.md`
- `backend/alembic/CLAUDE.md`
- `.claude/rules/python-style.md`
- `.claude/rules/python-patterns.md`
- `.claude/rules/python-anti-patterns.md`
- `.claude/memory-structure.md`

For each relevant file:

1. Compare it against the current source tree, not just the diff.
2. Check whether staged changes made any instruction stale.
3. Look for:
   - renamed or deleted paths still referenced
   - patterns that changed but are still documented the old way
   - new conventions that emerged and should be recorded
   - tech-version changes not reflected in instructions
   - rules that now contradict the actual codebase

### 4. Audit source-of-truth docs

Check whether the staged changes imply updates to:

- `docs/technical-stack.md`
- `docs/domain-model.md`
- `docs/vehicle-rules.md`
- `docs/product-backlog.md`

Use these only when the staged changes altered product, architecture, or scope facts. Do not treat them as generic memory files.

### 5. Audit skills

Inspect `.claude/skills/*/SKILL.md` and any obviously referenced local files.

Check whether a skill:

- references files or paths that changed
- assumes a pattern the codebase no longer follows
- has stale examples because of renamed files or workflow changes

In this workflow:

- flag skill drift
- do not propose skill edits unless the user explicitly asks for them

### 6. Audit repository-wide drift

Do not limit the audit to staged changes. Look across the current repository for places where instructions may already be stale from earlier work.

Call these out separately as existing drift so the user can distinguish:

- changes caused by the current staged diff
- older inconsistencies that predated the current PR

### 7. Present proposed changes

Group output by file.

Use this format:

```markdown
## Proposed: .claude/rules/python-patterns.md
- ADD: note that new API handlers must keep orchestration in service classes
- REMOVE: stale reference to an old repository helper name

## Proposed: .claude/memory-structure.md
- ADD: new skill routing entry for the staged workflow helper

## Flagged skill drift: .claude/skills/code-review/SKILL.md
- References a file path that no longer exists

## Existing repo drift: CLAUDE.md
- Mentions a startup command that no longer matches the current backend entrypoint
```

If no update is needed for an audited file, say `No changes needed.` when that is useful for clarity.

### 8. Wait for approval

- Do not write any changes until the user approves them.
- Apply only the approved instruction or doc changes.

## PR Body Requirements

The surrounding workflow creates the PR after this audit is approved. The PR body it produces must include:

- A `## Structural Changes` section containing the output of `uv run --python 3.14 python tools/code_map.py --diff main...HEAD --format markdown` pasted verbatim, including the `<!-- structural-changes:start -->` and `<!-- structural-changes:end -->` markers. The `structural-diff` workflow re-generates this section and fails the PR if the body does not match it exactly. The section embeds the head commit SHA and head-relative line numbers, so generate it from the final pushed `HEAD` and only then set the PR body. The workflow runs on `edited` pull-request events, so updating the body to match the pushed commit re-triggers the check.
- A `## Requirements` section containing the full contents of any issue-planner requirements file used for the implementation (see `CLAUDE.md`). That temporary file under `.claude/plans/` must be deleted before the final commit or PR unless Roland asks to keep it.

## What This Skill Does Not Do

- It does not create the PR. The surrounding workflow runs `git push` and `gh pr create` after this audit's proposals are approved.
- It does not commit changes.
- It does not modify code files.
- It does not auto-write to instruction or doc files.
- It does not silently update skill files in this workflow.

## Example Triggers

- `Use $pr-prep before I open a PR for these staged changes.`
- `Use $pr-prep to audit the staged diff for memory or doc drift.`
- `Use $pr-prep to tell me whether CLAUDE.md or .claude rules need updates before PR.`
