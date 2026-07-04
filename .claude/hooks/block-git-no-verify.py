#!/usr/bin/env python3
"""PreToolUse(Bash) hook: veto `git commit --no-verify` / `-n`.

Claude Code pipes the hook payload JSON on stdin; the proposed shell command is at
.tool_input.command. Exiting 2 blocks the tool call and feeds stderr back to the model.

We tokenize the command with shlex so a quoted commit message that merely mentions
"-n" or "--no-verify" (e.g. git commit -m "fix -n handling") is NOT treated as a bypass.
"""

import json
import shlex
import sys


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except Exception:
        return 0  # unparseable payload -> don't interfere

    command = payload.get("tool_input", {}).get("command", "") or ""
    if "commit" not in command:
        return 0

    try:
        tokens = shlex.split(command)
    except ValueError:
        tokens = command.split()

    # 'commit' must appear as a real token (the git subcommand), not inside a quoted string.
    if "commit" not in tokens:
        return 0

    # -n is git commit's short form of --no-verify. Any short-flag cluster containing 'n'
    # (e.g. -n, -an, -nm) is a bypass; long flags other than --no-verify are ignored.
    bypass = "--no-verify" in tokens or any(
        tok.startswith("-") and not tok.startswith("--") and "n" in tok
        for tok in tokens
    )
    if not bypass:
        return 0

    sys.stderr.write(
        "Blocked: this 'git commit' uses --no-verify/-n, which skips the gitleaks "
        "pre-commit secret scan. Do not bypass it. If the commit is genuinely blocked "
        "by a gitleaks finding, stop and surface the finding to Roland.\n"
    )
    return 2


if __name__ == "__main__":
    sys.exit(main())
