"""Verify a PR body contains the generated structural-changes section verbatim.

The expected Markdown (produced by ``tools/code_map.py --diff ... --format
markdown``) is read from stdin or a file. The PR body is read from a file or the
``PR_BODY`` environment variable. The check passes only when the exact block
between the structural-change markers appears in the PR body.

Usage:
    python tools/code_map.py --diff main...HEAD --format markdown \
        | python tools/verify_pr_structural_section.py --pr-body pr_body.md
    python tools/verify_pr_structural_section.py --expected expected.md --pr-body pr_body.md
"""
from __future__ import annotations

import argparse
import os
import sys

MARKER_START = "<!-- structural-changes:start -->"
MARKER_END = "<!-- structural-changes:end -->"


def main(argv: list[str] | None = None) -> int:
    """Compare the expected structural section against the PR body."""
    args = _parse_args(argv)
    try:
        expected = _extract_block(_read_expected(args))
        pr_body = _read_pr_body(args)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    if expected in _normalize(pr_body):
        print("PR body contains the exact structural-changes section.")
        return 0

    print("PR body is missing or differs from the generated structural-changes section.", file=sys.stderr)
    print(f"Required markers: {MARKER_START} ... {MARKER_END}", file=sys.stderr)
    print(_diff(expected, pr_body), file=sys.stderr)
    return 1


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Verify the PR structural-changes section.")
    parser.add_argument("--expected", metavar="PATH", help="Expected Markdown file. Defaults to stdin.")
    parser.add_argument("--pr-body", dest="pr_body", metavar="PATH", help="PR body file. Defaults to $PR_BODY.")
    return parser.parse_args(argv)


def _read_expected(args: argparse.Namespace) -> str:
    if args.expected:
        return _read_file(args.expected)
    data = sys.stdin.read()
    if not data.strip():
        raise ValueError("No expected Markdown provided on stdin or via --expected.")
    return data


def _read_pr_body(args: argparse.Namespace) -> str:
    if args.pr_body:
        return _read_file(args.pr_body)
    body = os.environ.get("PR_BODY")
    if body is None:
        raise ValueError("No PR body provided via --pr-body or $PR_BODY.")
    return body


def _extract_block(text: str) -> str:
    normalized = _normalize(text)
    start = normalized.find(MARKER_START)
    end = normalized.find(MARKER_END)
    if start == -1 or end == -1 or end < start:
        raise ValueError(f"Expected Markdown is missing the markers {MARKER_START} / {MARKER_END}.")
    return normalized[start : end + len(MARKER_END)]


def _diff(expected: str, pr_body: str) -> str:
    import difflib

    expected_lines = expected.splitlines()
    actual_block = _slice_markers(_normalize(pr_body))
    diff = difflib.unified_diff(
        actual_block.splitlines(),
        expected_lines,
        fromfile="pr-body",
        tofile="expected",
        lineterm="",
    )
    return "\n".join(diff) or "PR body does not contain the structural markers at all."


def _slice_markers(text: str) -> str:
    start = text.find(MARKER_START)
    end = text.find(MARKER_END)
    if start == -1 or end == -1 or end < start:
        return ""
    return text[start : end + len(MARKER_END)]


def _normalize(text: str) -> str:
    return text.replace("\r\n", "\n").replace("\r", "\n")


def _read_file(path: str) -> str:
    with open(path, encoding="utf-8") as handle:
        return handle.read()


if __name__ == "__main__":
    sys.exit(main())
