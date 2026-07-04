#!/usr/bin/env python3
"""PreToolUse(Bash) hook: veto commits/merges on main and any push targeting main.

Policy: Claude may branch, commit, push, and open PRs autonomously, but never
to main. Blocked cases:
  - `git commit` or `git merge` while HEAD is on main
  - `git push` with a refspec targeting main (e.g. `push origin main`,
    `push origin feature:main`, `push origin --delete main`)
  - bare `git push` / `git push origin HEAD` while HEAD is on main

Claude Code pipes the hook payload JSON on stdin; the proposed shell command is
at .tool_input.command. Exiting 2 blocks the tool call and feeds stderr back to
the model. Tokenized with shlex so quoted strings that merely mention main or a
subcommand are not treated as matches.
"""

from __future__ import annotations

import json
import shlex
import subprocess
import sys

PROTECTED = {"main"}
ON_MAIN_BLOCKED_SUBCOMMANDS = {"commit", "merge"}


def current_branch() -> str | None:
    try:
        out = subprocess.run(
            ["git", "symbolic-ref", "--short", "-q", "HEAD"],
            capture_output=True,
            text=True,
            timeout=5,
        )
    except Exception:
        return None
    return out.stdout.strip() or None


def push_targets_protected(tokens: list[str]) -> bool:
    for tok in tokens:
        if tok in PROTECTED:
            return True
        # refspec form src:dst — only the destination matters
        if ":" in tok and not tok.startswith("-"):
            dst = tok.rsplit(":", 1)[-1]
            if dst in PROTECTED:
                return True
    return False


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except Exception:
        return 0  # unparseable payload -> don't interfere

    command = payload.get("tool_input", {}).get("command", "") or ""
    if "git" not in command:
        return 0

    try:
        tokens = shlex.split(command)
    except ValueError:
        tokens = command.split()

    if "git" not in tokens:
        return 0

    subcommands = ON_MAIN_BLOCKED_SUBCOMMANDS | {"push"}
    if not subcommands.intersection(tokens):
        return 0

    if ON_MAIN_BLOCKED_SUBCOMMANDS.intersection(tokens):
        branch = current_branch()
        if branch in PROTECTED:
            sys.stderr.write(
                f"Blocked: HEAD is on '{branch}'. Never commit or merge on main. "
                "Create a feature branch first: git checkout -b <branch-name>\n"
            )
            return 2

    if "push" in tokens:
        if push_targets_protected(tokens):
            sys.stderr.write(
                "Blocked: this push targets main. Push the feature branch and "
                "open a PR instead; never push to main.\n"
            )
            return 2
        # A push with no refspec (or refspec HEAD) pushes the current branch.
        positionals = [
            tok for tok in tokens[tokens.index("push") + 1 :] if not tok.startswith("-")
        ]
        refspecs = positionals[1:]  # first positional is the remote
        if not refspecs or "HEAD" in refspecs:
            branch = current_branch()
            if branch in PROTECTED:
                sys.stderr.write(
                    f"Blocked: HEAD is on '{branch}' and this push has no explicit "
                    "refspec, so it would push main. Work on a feature branch.\n"
                )
                return 2

    return 0


if __name__ == "__main__":
    sys.exit(main())
