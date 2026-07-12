---
name: pr-prep
description: Mandatory before opening a PR in this repository (before `gh pr create`). Audits staged changes and proposes updates to repo-local instruction files such as `CLAUDE.md`, `.claude/rules/*.md`, and `.claude/memory-structure.md`. Also flags skill drift and broader documentation drift. Applies the drift fixes directly to those instruction/doc files; it is conservative (adds or corrects stale guidance, and does not delete existing guidance unless the diff plainly contradicts it).
---

# Allocio PR Prep

## Overview

Audit staged changes before opening a PR and check whether the repository's instruction files still match the codebase. This skill applies memory and documentation maintenance directly to instruction and documentation files.

This audit is the step between committing on a feature branch and running `gh pr create` (see `CLAUDE.md` Git Workflow). It applies its edits directly; the surrounding workflow then commits and pushes them and creates the PR.

Read `.claude/memory-structure.md` first.

## When To Use

- Before opening a PR
- When staged changes may have invalidated instructions or conventions
- When files, modules, routes, or public helpers were renamed, added, or removed
- When you suspect repo-local instructions have drifted from the actual codebase

This skill applies changes directly to instruction and documentation files. It never edits application source, tests, or generated files (`docs/code-map.json`, `docs/code-map.html`), and it never auto-edits skill files (it only flags skill drift — see section 5).

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
uv run --python 3.14 python tools/code_map.py --check-overview-html docs/code-map.html
uv run --python 3.14 python tools/code_map.py --staged --format markdown
uv run --python 3.14 python tools/code_map.py --overview-html-diff origin/main...HEAD
```

- `--check docs/code-map.json` must pass. If it fails, run `uv run --python 3.14 python tools/code_map.py --write docs/code-map.json && git add docs/code-map.json` and re-stage before continuing.
- `--check-overview-html docs/code-map.html` must pass. If it fails, run `uv run --python 3.14 python tools/code_map.py --write-overview-html docs/code-map.html && git add docs/code-map.html` and re-stage.
- `--staged --format markdown` is the staged-change review surface: read it to confirm the staged symbol, route, import, and component changes match intent before committing.
- `--overview-html-diff origin/main...HEAD` prints the githack proxy link that opens the interactive overview in changed-only mode for this PR's head branch (an orientation aid for the PR body; not CI-verified).

The PR-range structural Change Map is no longer produced here: the `structural-diff` CI workflow generates it and posts it as a sticky PR comment. Do not put a `Structural Changes` section in the PR body.

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

### 7. Apply the changes

Edit the instruction and documentation files directly. Be conservative: add or correct guidance that the diff made stale; do not delete existing guidance unless the diff plainly contradicts it.

After editing, report what you changed, grouped by file:

```markdown
## Updated: .claude/rules/python-patterns.md
- ADDED: note that new API handlers must keep orchestration in service classes
- CORRECTED: stale reference to an old repository helper name

## Updated: .claude/memory-structure.md
- ADDED: new skill routing entry for the staged workflow helper

## Flagged skill drift (not auto-edited): .claude/skills/code-review/SKILL.md
- References a file path that no longer exists

## Existing repo drift: CLAUDE.md
- Mentions a startup command that no longer matches the current backend entrypoint
```

Skill files are flagged, not auto-edited (see section 5). If no update is needed for an audited file, say `No changes needed.` when that is useful for clarity.

### 8. Stage the edits

- Stage the instruction and documentation files you edited so the surrounding workflow includes them in the commit and PR.
- Do not edit application source, tests, or generated files.

## PR Body Requirements

The surrounding workflow creates the PR after this audit is approved. The PR body it produces must include:

- An `## Architecture overview` line linking to the interactive overview for this PR's head branch via the githack proxy: `https://raw.githack.com/pleszr/allocio/<head-branch>/docs/code-map.html` (append the `#chg=...` fragment from `uv run --python 3.14 python tools/code_map.py --overview-html-diff origin/main...HEAD` to open it in changed-only mode). GitHub renders committed `.html` as source, so this proxy link — not a repo-relative path — is what renders the live page. This link is not CI-verified — it is an orientation aid.
- A `## Requirements` section containing the full contents of any issue-planner requirements file used for the implementation (see `CLAUDE.md`). That temporary file under `.claude/plans/` must be deleted before the final commit or PR unless Roland asks to keep it.

## What This Skill Does Not Do

- It does not create the PR. The surrounding workflow runs `git commit`, `git push`, and `gh pr create` after this audit applies its edits.
- It does not commit or push changes itself.
- It does not modify application source, tests, or generated files (`docs/code-map.json`, `docs/code-map.html`).
- It does not auto-edit skill files; it only flags skill drift.

## Example Triggers

- `Use $pr-prep before I open a PR for these staged changes.`
- `Use $pr-prep to audit the staged diff for memory or doc drift.`
- `Use $pr-prep to tell me whether CLAUDE.md or .claude rules need updates before PR.`
