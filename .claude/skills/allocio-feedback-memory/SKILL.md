---
name: allocio-feedback-memory
description: Use when the user explicitly asks to update memory, save feedback, remember a preference, or route a correction to the right repo-local instruction file. Reads `.claude/memory-structure.md`, checks for contradictions and duplicates, shows the exact proposed patch, and only applies the change after user approval.
---

# Allocio Feedback Memory

## Overview

Route explicit feedback to the correct repo-local memory file. This skill is for deliberate memory updates, not for normal conversational corrections handled inline.

This repository uses Claude-facing memory in `.claude/` and specialized workflow instructions in `.claude/skills/`. Read `.claude/memory-structure.md` before drafting any update.

## When To Use

Use this skill when the user says things like:

- `save this to memory`
- `remember this`
- `update the rules with this`
- `route this correction to the right file`
- `what file should this feedback go into?`

Do not use this skill just because the user corrected something during normal work. Ordinary corrections should be applied inline unless the user explicitly asks to save them.

## Workflow

### 1. Read the memory map

- Read `.claude/memory-structure.md`.
- Identify every plausible target file before choosing one.
- If the feedback is actually a product or architecture correction, route it to the source-of-truth doc listed there instead of a memory file.

### 2. Read the target file

- Read the candidate file before proposing any change.
- Check whether:
  - the feedback already exists
  - an existing entry contradicts it
  - an old rule would become obsolete

If contradictions exist, present them and ask which direction to keep before drafting the patch.

### 3. Generalize the feedback

For each piece of feedback, check:

- Is it abstract enough to help on future work?
- If not, can it be rewritten into a reusable rule without losing the important constraint?
- Would saving the generalized form reduce the chance of repeating the mistake?

Do not store one-off task notes as durable memory unless the user explicitly wants that.

### 4. Draft the exact change

Show the user exactly what you propose to add and where.

Use this format:

```markdown
## Target: .claude/rules/python-patterns.md
## Section: Layering
## Add after line 24:

- Keep new FastAPI endpoints thin; move orchestration into service classes.
```

If the best action is to update or replace an existing bullet, show the before and after text explicitly.

### 5. Apply only on approval

- Do not write the change until the user confirms.
- After approval, edit only the approved instruction or doc files.
- Re-read the edited section if needed to avoid corrupting nearby structure.

## Routing Rules

- Backend coding preferences usually belong in `.claude/rules/python-style.md`, `.claude/rules/python-patterns.md`, or `.claude/rules/python-anti-patterns.md`.
- Repo-wide workflow changes belong in `CLAUDE.md`.
- Backend workflow changes that are broader than a single Python rule usually belong in `backend/CLAUDE.md`.
- Frontend workflow changes belong in `frontend/CLAUDE.md`.
- Database and migration workflow changes belong in `backend/alembic/CLAUDE.md`.
- Planning workflow changes belong in `.claude/skills/allocio-issue-planner/SKILL.md`.
- Code-review workflow changes belong in `.claude/skills/allocio-code-review/SKILL.md`.
- Feedback-routing workflow changes belong in `.claude/skills/allocio-feedback-memory/SKILL.md`.
- PR-prep workflow changes belong in `.claude/skills/allocio-pr-prep/SKILL.md`.
- Product or architecture corrections belong in the relevant `docs/*.md` source-of-truth file, not in `.claude` memory.

If no existing file fits:

1. Propose the best new file path.
2. Explain why existing targets are insufficient.
3. Ask before creating it.

## Constraints

- Do not modify code files.
- Do not create instruction files without user approval.
- Do not delete instruction files without user approval.
- Avoid duplicates.
- Prefer small, precise edits over broad rewrites.

## Example Triggers

- `Use $allocio-feedback-memory to decide where this preference should be saved.`
- `Use $allocio-feedback-memory to review this correction and prepare the exact memory patch.`
- `Use $allocio-feedback-memory to update the code review rules with this new preference.`
