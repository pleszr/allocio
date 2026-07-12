"""Deterministic source-derived code map and structural PR diff for Allocio.

Extracts a machine-readable structural map of the repository from parsed source
(Python via ``ast``, TypeScript/TSX via ``tools/ts_symbol_map.mjs``) and renders
staged- and PR-range structural diffs. The committed map lives at
``docs/code-map.json`` and must stay byte-stable across repeated runs on the same
source tree, so nothing here embeds timestamps or commit SHAs into the map.

Commands:
    python tools/code_map.py --write docs/code-map.json
    python tools/code_map.py --check docs/code-map.json
    python tools/code_map.py --check-staged docs/code-map.json
    python tools/code_map.py --staged --format markdown
    python tools/code_map.py --diff origin/main...HEAD --format markdown
    python tools/code_map.py --write-overview-html docs/code-map.html
    python tools/code_map.py --check-overview-html docs/code-map.html
    python tools/code_map.py --overview-html-diff origin/main...HEAD
"""
from __future__ import annotations

import argparse
import ast
import base64
import hashlib
import json
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath

SCHEMA_VERSION = 1
GENERATOR = "tools/code_map.py"
CANONICAL_PYTHON = (3, 14)
REPO_ROOT = Path(__file__).resolve().parent.parent
NODE_SCRIPT = REPO_ROOT / "tools" / "ts_symbol_map.mjs"

MARKER_START = "<!-- structural-changes:start -->"
MARKER_END = "<!-- structural-changes:end -->"

HTTP_METHODS = {"get", "post", "put", "patch", "delete", "head", "options", "trace"}
_HASH_WIDTH = 16

# Architectural layers for the overview module graph. Path segment -> subgraph
# title; LAYER_ORDER fixes the left-to-right cluster order so the render is stable.
LAYER_SEGMENTS = (
    ("app/api/", "API"),
    ("app/services/", "Services"),
    ("app/repository/", "Repository"),
    ("app/domain/", "Domain"),
    ("app/common/", "Common"),
    ("alembic/", "Migrations"),
    ("src/pages/", "Pages"),
    ("src/components/", "Components"),
    ("src/hooks/", "Hooks"),
    ("src/context/", "State"),
    ("src/api/", "API"),
)
LAYER_ORDER = (
    "App", "Pages", "Components", "Hooks", "State",
    "API", "Services", "Repository", "Domain", "Common", "Migrations", "Tooling", "Other",
)

# Interactive HTML overview (docs/code-map.html). The page links each node to its
# source on GitHub and is reachable from a PR via the githack proxy over the head
# branch. Repo confirmed public as pleszr/allocio.
GITHUB_BLOB_BASE = "https://github.com/pleszr/allocio/blob/main/"
GITHUB_RAW_PROXY_BASE = "https://raw.githack.com/pleszr/allocio/"
OVERVIEW_HTML_PATH = "docs/code-map.html"
# Default to product code only: the tooling area (the code map's own churny
# helpers) is collapsed out of the graph. Flip to include it.
OVERVIEW_INCLUDE_TOOLING = False

# Status badges for the PR-body Change Map (render_markdown).
STATUS_BADGES = {
    "Added": "🟢 **Added**",
    "Removed": "🔴 **Removed**",
    "Modified": "🟡 **Modified**",
}


class CodeMapError(Exception):
    """A recoverable or reportable failure while building the code map."""


class ParseError(CodeMapError):
    """A source file could not be parsed. Non-recoverable for this run."""


# --------------------------------------------------------------------------- #
# Entry point
# --------------------------------------------------------------------------- #


def main(argv: list[str] | None = None) -> int:
    """Dispatch a code-map command and return a process exit code."""
    args = _parse_args(argv)
    try:
        _require_canonical_python()
        return _dispatch(args)
    except CodeMapError as exc:
        print(str(exc), file=sys.stderr)
        return 1


def _require_canonical_python() -> None:
    if sys.version_info[:2] == CANONICAL_PYTHON:
        return
    want = f"{CANONICAL_PYTHON[0]}.{CANONICAL_PYTHON[1]}"
    have = f"{sys.version_info.major}.{sys.version_info.minor}"
    raise CodeMapError(
        f"code_map.py must run under Python {want} for reproducible symbol hashes "
        f"(found {have}). Run: uv run --python {want} python tools/code_map.py ..."
    )


def _dispatch(args: argparse.Namespace) -> int:
    if args.write:
        return _command_write(Path(args.write))
    if args.check:
        return _command_check(Path(args.check))
    if args.check_staged:
        return _command_check_staged(Path(args.check_staged))
    if args.staged:
        return _command_markdown_staged()
    if args.diff:
        return _command_markdown_diff(args.diff)
    if args.write_overview_html:
        return _command_write_overview_html(Path(args.write_overview_html))
    if args.check_overview_html:
        return _command_check_overview_html(Path(args.check_overview_html))
    if args.overview_html_diff:
        return _command_overview_html_diff(args.overview_html_diff)
    print("No command given. See --help.", file=sys.stderr)
    return 1


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Allocio deterministic code map.", allow_abbrev=False)
    parser.add_argument("--write", metavar="PATH", help="Write the code map to PATH.")
    parser.add_argument("--check", metavar="PATH", help="Fail if PATH is stale versus the working tree.")
    parser.add_argument("--check-staged", dest="check_staged", metavar="PATH", help="Fail if staged PATH is stale versus staged source.")
    parser.add_argument("--staged", action="store_true", help="Render HEAD-versus-index structural Markdown.")
    parser.add_argument("--diff", metavar="RANGE", help="Render structural Markdown for a base...head range.")
    parser.add_argument("--format", choices=["markdown"], help="Output format for --staged and --diff.")
    parser.add_argument("--write-overview-html", dest="write_overview_html", metavar="PATH", help="Write the interactive HTML architecture overview to PATH.")
    parser.add_argument("--check-overview-html", dest="check_overview_html", metavar="PATH", help="Fail if the HTML overview PATH is stale versus the working tree.")
    parser.add_argument("--overview-html-diff", dest="overview_html_diff", metavar="RANGE", help="Print a githack proxy URL that opens the HTML overview in changed-only mode for a base...head range.")
    return parser.parse_args(argv)


# --------------------------------------------------------------------------- #
# Commands
# --------------------------------------------------------------------------- #


def _command_write(path: Path) -> int:
    code_map = build_map(REPO_ROOT)
    path.write_text(dump_map(code_map), encoding="utf-8")
    print(f"Wrote {path}")
    return 0


def _command_check(path: Path) -> int:
    expected = dump_map(build_map(REPO_ROOT))
    actual = _read_text_or_empty(path)
    if actual == expected:
        return 0
    print(f"{path} is stale versus the working tree.", file=sys.stderr)
    print(f"Run: python tools/code_map.py --write {path}", file=sys.stderr)
    return 1


def _command_check_staged(path: Path) -> int:
    rel = _repo_relative(path)
    with _materialize_index() as root:
        expected = dump_map(build_map(root))
    actual = _git_show(f":{rel}") or ""
    if actual == expected:
        return 0
    print(f"Staged {rel} does not match the staged source files.", file=sys.stderr)
    print(f"Run: python tools/code_map.py --write {rel} && git add {rel}", file=sys.stderr)
    return 1


def _command_markdown_staged() -> int:
    base_map = _map_at_ref("HEAD")
    with _materialize_index() as root:
        head_map = build_map(root)
    changed = _changed_files(["diff", "--cached", "--name-only"])
    diff = diff_maps(base_map, head_map, changed)
    context = MarkdownContext(
        compared_range="HEAD...:index (staged)",
        base_commit=_rev_parse("HEAD"),
        head_commit="index (staged)",
    )
    print(render_markdown(diff, context))
    return 0


def _command_write_overview_html(path: Path) -> int:
    path.write_text(render_overview_html(build_map(REPO_ROOT)), encoding="utf-8")
    print(f"Wrote {path}")
    return 0


def _command_check_overview_html(path: Path) -> int:
    expected = render_overview_html(build_map(REPO_ROOT))
    if _read_text_or_empty(path) == expected:
        return 0
    print(f"{path} is stale versus the working tree.", file=sys.stderr)
    print(f"Run: uv run --python 3.14 python tools/code_map.py --write-overview-html {path}", file=sys.stderr)
    return 1


def _command_overview_html_diff(range_expr: str) -> int:
    left, right = _split_range(range_expr)
    base_ref = _merge_base(left, right)
    base_map = _map_at_ref(base_ref)
    head_map = _map_at_ref(right)
    changed = _changed_files(["diff", "--name-only", base_ref, right])
    diff = diff_maps(base_map, head_map, changed)
    print(_overview_html_diff_url(diff))
    return 0


def _command_markdown_diff(range_expr: str) -> int:
    left, right = _split_range(range_expr)
    base_ref = _merge_base(left, right)
    base_map = _map_at_ref(base_ref)
    head_map = _map_at_ref(right)
    changed = _changed_files(["diff", "--name-only", base_ref, right])
    diff = diff_maps(base_map, head_map, changed)
    context = MarkdownContext(
        compared_range=range_expr,
        base_commit=base_ref,
        head_commit=_rev_parse(right),
    )
    print(render_markdown(diff, context))
    return 0


# --------------------------------------------------------------------------- #
# Map construction
# --------------------------------------------------------------------------- #


def build_map(root: Path) -> dict:
    """Build the structural map for the source tree rooted at ``root``."""
    return {
        "schema_version": SCHEMA_VERSION,
        "generator": GENERATOR,
        "areas": {
            "backend": {"files": _python_area(root, ["backend/app", "backend/alembic/versions"])},
            "frontend": {"files": _frontend_area(root)},
            "tooling": {"files": _python_area(root, ["tools"])},
        },
    }


def dump_map(code_map: dict) -> str:
    """Serialize a code map to stable JSON text with a trailing newline."""
    return json.dumps(code_map, indent=2, sort_keys=False) + "\n"


def _python_area(root: Path, prefixes: list[str]) -> list[dict]:
    files = []
    for prefix in prefixes:
        for path in sorted((root / prefix).rglob("*.py")):
            if "__pycache__" in path.parts:
                continue
            rel = path.relative_to(root).as_posix()
            files.append(_extract_python(path, rel))
    files.sort(key=lambda entry: entry["path"])
    return files


def _extract_python(path: Path, rel: str) -> dict:
    text = path.read_text(encoding="utf-8")
    try:
        tree = ast.parse(text, filename=rel)
    except SyntaxError as exc:
        raise ParseError(f"Python AST parse failed: {rel}: stage=parse: {exc}") from exc

    functions: list[dict] = []
    classes: list[dict] = []
    routes: list[dict] = []
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            functions.append(_symbol(node))
            routes.extend(_routes_from_function(node))
        elif isinstance(node, ast.ClassDef):
            classes.append(_class_entry(node))

    return {
        "path": rel,
        "language": "python",
        "imports": _python_imports(tree),
        "functions": sorted(functions, key=lambda item: item["name"]),
        "classes": sorted(classes, key=lambda item: item["name"]),
        "routes": sorted(routes, key=lambda item: (item["path"], item["method"])),
    }


def _class_entry(node: ast.ClassDef) -> dict:
    methods = [
        _symbol(member)
        for member in node.body
        if isinstance(member, (ast.FunctionDef, ast.AsyncFunctionDef))
    ]
    return {
        "name": node.name,
        "line_start": node.lineno,
        "line_end": getattr(node, "end_lineno", node.lineno),
        "hash": _class_shell_hash(node),
        "methods": sorted(methods, key=lambda item: item["name"]),
    }


def _routes_from_function(node: ast.FunctionDef | ast.AsyncFunctionDef) -> list[dict]:
    routes = []
    for decorator in node.decorator_list:
        if not (isinstance(decorator, ast.Call) and isinstance(decorator.func, ast.Attribute)):
            continue
        if decorator.func.attr not in HTTP_METHODS:
            continue
        routes.append(
            {
                "method": decorator.func.attr,
                "path": _first_string_arg(decorator),
                "handler": node.name,
                "line_start": node.lineno,
                "line_end": getattr(node, "end_lineno", node.lineno),
                "hash": _node_hash(node),
            }
        )
    return routes


def _first_string_arg(call: ast.Call) -> str:
    if call.args and isinstance(call.args[0], ast.Constant) and isinstance(call.args[0].value, str):
        return call.args[0].value
    return ""


def _symbol(node: ast.FunctionDef | ast.AsyncFunctionDef) -> dict:
    return {
        "name": node.name,
        "line_start": node.lineno,
        "line_end": getattr(node, "end_lineno", node.lineno),
        "hash": _node_hash(node),
    }


def _python_imports(tree: ast.Module) -> list[str]:
    specifiers = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                specifiers.add(alias.name)
        elif isinstance(node, ast.ImportFrom):
            specifiers.add("." * (node.level or 0) + (node.module or ""))
    return sorted(specifiers)


def _node_hash(node: ast.AST) -> str:
    return _hash(ast.dump(node, include_attributes=False))


def _class_shell_hash(node: ast.ClassDef) -> str:
    shell = {
        "name": node.name,
        "bases": [ast.dump(base) for base in node.bases],
        "keywords": [ast.dump(keyword) for keyword in node.keywords],
        "decorators": [ast.dump(decorator) for decorator in node.decorator_list],
        "body": [
            ast.dump(statement)
            for statement in node.body
            if not isinstance(statement, (ast.FunctionDef, ast.AsyncFunctionDef))
        ],
    }
    return _hash(json.dumps(shell, sort_keys=True))


def _hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:_HASH_WIDTH]


def _frontend_area(root: Path) -> list[dict]:
    if not NODE_SCRIPT.exists():
        raise CodeMapError(f"Missing {NODE_SCRIPT}. Cannot extract frontend symbols.")
    result = subprocess.run(
        ["node", str(NODE_SCRIPT), "--root", str(root)],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise CodeMapError(result.stderr.strip() or "tools/ts_symbol_map.mjs failed.")
    entries = json.loads(result.stdout)
    entries.sort(key=lambda entry: entry["path"])
    return entries


# --------------------------------------------------------------------------- #
# Structural diff
# --------------------------------------------------------------------------- #


@dataclass
class SymbolChange:
    """A single added, removed, or modified structural symbol."""

    area: str
    kind: str
    name: str
    path: str
    line: int | None


@dataclass
class ImportChange:
    """Added and removed import specifiers for one file."""

    path: str
    added: list[str]
    removed: list[str]


@dataclass
class DiffResult:
    """The deterministic classification of two code maps over changed files."""

    added: list[SymbolChange] = field(default_factory=list)
    removed: list[SymbolChange] = field(default_factory=list)
    modified: list[SymbolChange] = field(default_factory=list)
    file_only: list[str] = field(default_factory=list)
    import_changes: list[ImportChange] = field(default_factory=list)
    changed_files: list[str] = field(default_factory=list)


@dataclass
class MarkdownContext:
    """Provenance shown in the rendered structural Markdown header."""

    compared_range: str
    base_commit: str
    head_commit: str


def diff_maps(base_map: dict, head_map: dict, changed_files: list[str]) -> DiffResult:
    """Classify structural changes between two maps over git-changed files."""
    base_symbols, base_imports = _index_map(base_map)
    head_symbols, head_imports = _index_map(head_map)

    result = DiffResult()
    _classify_symbols(base_symbols, head_symbols, result)
    result.import_changes = _classify_imports(base_imports, head_imports)

    touched = {change.path for change in result.added + result.removed + result.modified}
    touched.update(change.path for change in result.import_changes)
    git_changed = set(changed_files)
    result.changed_files = sorted(git_changed | touched)
    result.file_only = sorted(path for path in git_changed if path not in touched)
    return result


def _classify_symbols(base: dict, head: dict, result: DiffResult) -> None:
    for key in sorted(set(base) | set(head)):
        in_base = key in base
        in_head = key in head
        if in_head and not in_base:
            result.added.append(_change_from(head[key]))
        elif in_base and not in_head:
            result.removed.append(_change_from(base[key]))
        elif base[key]["hash"] != head[key]["hash"]:
            result.modified.append(_change_from(head[key]))


def _classify_imports(base: dict, head: dict) -> list[ImportChange]:
    changes = []
    for path in sorted(set(base) | set(head)):
        before = set(base.get(path, []))
        after = set(head.get(path, []))
        added = sorted(after - before)
        removed = sorted(before - after)
        if added or removed:
            changes.append(ImportChange(path=path, added=added, removed=removed))
    return changes


def _change_from(info: dict) -> SymbolChange:
    return SymbolChange(
        area=info["area"],
        kind=info["kind"],
        name=info["name"],
        path=info["path"],
        line=info.get("line_start"),
    )


def _index_map(code_map: dict) -> tuple[dict, dict]:
    symbols: dict[tuple, dict] = {}
    imports: dict[str, list[str]] = {}
    for area, payload in code_map["areas"].items():
        for entry in payload["files"]:
            path = entry["path"]
            imports[path] = entry.get("imports", [])
            _index_file_symbols(area, entry, symbols)
    return symbols, imports


def _index_file_symbols(area: str, entry: dict, symbols: dict) -> None:
    path = entry["path"]
    for function in entry.get("functions", []):
        _put(symbols, area, path, "function", function["name"], function)
    for component in entry.get("components", []):
        _put(symbols, area, path, "component", component["name"], component)
    for cls in entry.get("classes", []):
        _put(symbols, area, path, "class", cls["name"], cls)
        for method in cls.get("methods", []):
            qualname = f"{cls['name']}.{method['name']}"
            _put(symbols, area, path, "method", qualname, method)
    for route in entry.get("routes", []):
        qualname = f"{route['method'].upper()} {route['path']}"
        _put(symbols, area, path, "route", qualname, route)


def _put(symbols: dict, area: str, path: str, kind: str, name: str, source: dict) -> None:
    symbols[(area, path, kind, name)] = {
        "area": area,
        "path": path,
        "kind": kind,
        "name": name,
        "hash": source["hash"],
        "line_start": source.get("line_start"),
    }


# --------------------------------------------------------------------------- #
# Markdown rendering
# --------------------------------------------------------------------------- #


def render_markdown(diff: DiffResult, context: MarkdownContext) -> str:
    """Render the marker-wrapped structural Change Map for a diff result."""
    lines = [MARKER_START, "## Structural Changes", ""]
    lines += [
        f"- **Compared range:** {context.compared_range}",
        f"- **Base commit:** `{context.base_commit}`",
        f"- **Head commit:** `{context.head_commit}`",
        "",
    ]
    lines += _focus_section(diff)
    lines += _files_section(diff)
    lines += _layer_symbol_sections(diff)
    lines += _routes_section(diff)
    lines += _imports_section(diff)
    lines += _tests_section(diff)
    lines.append(MARKER_END)
    return "\n".join(lines)


def _files_section(diff: DiffResult) -> list[str]:
    lines = ["### Files changed", ""]
    if not diff.changed_files:
        return lines + ["- None", ""]
    file_only = set(diff.file_only)
    for path in diff.changed_files:
        suffix = " (File-only)" if path in file_only else ""
        lines.append(f"- {path}{suffix}")
    lines.append("")
    return lines


def _layer_symbol_sections(diff: DiffResult) -> list[str]:
    grouped: dict[str, list[str]] = {}
    for status, change in _iter_changes(diff):
        if change.kind == "route":
            continue
        grouped.setdefault(_layer_of(change.path), []).append(_badge_line(status, change))
    lines: list[str] = []
    for layer in LAYER_ORDER:
        rows = grouped.get(layer)
        if not rows:
            continue
        lines += [f"### {layer} changes", ""] + sorted(rows) + [""]
    if not lines:
        lines = ["### Symbol changes", "", "- None", ""]
    return lines


def _routes_section(diff: DiffResult) -> list[str]:
    lines = ["### Routes changed", ""]
    rows = [
        _badge_line(status, change)
        for status, change in _iter_changes(diff)
        if change.kind == "route"
    ]
    return lines + (sorted(rows) if rows else ["- None"]) + [""]


def _imports_section(diff: DiffResult) -> list[str]:
    lines = ["### Imports changed", ""]
    if not diff.import_changes:
        return lines + ["- None", ""]
    for change in diff.import_changes:
        added = " ".join(f"+`{name}`" for name in change.added)
        removed = " ".join(f"-`{name}`" for name in change.removed)
        detail = " ".join(part for part in (added, removed) if part)
        lines.append(f"- {change.path}: {detail}")
    lines.append("")
    return lines


def _tests_section(diff: DiffResult) -> list[str]:
    lines = ["### Tests changed or missing", ""]
    tests = [path for path in diff.changed_files if _is_test_file(path)]
    if tests:
        lines += [f"- Changed: {path}" for path in tests]
    else:
        lines.append("- No test files changed.")
    if not tests and _has_backend_symbol_changes(diff):
        lines.append("- Backend symbol changes are not covered by any changed test.")
    lines.append("")
    return lines


def _focus_section(diff: DiffResult) -> list[str]:
    lines = ["### Suggested human review focus", ""]
    focus = _review_focus(diff)
    if focus:
        body = focus
    elif _has_any_change(diff):
        body = ["- No specific focus flagged; review the changes below."]
    else:
        body = ["- No structural changes detected."]
    return lines + body + [""]


def _has_any_change(diff: DiffResult) -> bool:
    return bool(diff.added or diff.removed or diff.modified or diff.import_changes)


def _review_focus(diff: DiffResult) -> list[str]:
    focus = []
    routes = [change for change in diff.modified + diff.added + diff.removed if change.kind == "route"]
    if routes:
        focus.append("- Verify API contract changes for the routes listed above.")
    if diff.removed:
        focus.append("- Removed symbols may leave orphaned call sites; check for dead references.")
    if any(change.kind == "component" for change in diff.added + diff.modified):
        focus.append("- Re-check loading, empty, success, and error states for changed React components.")
    if not any(_is_test_file(path) for path in diff.changed_files) and _has_backend_symbol_changes(diff):
        focus.append("- Add or update backend tests for the changed backend symbols.")
    return focus


def _badge_line(status: str, change: SymbolChange) -> str:
    location = f"{change.path}:{change.line}" if change.line else change.path
    return f"- {STATUS_BADGES[status]} {change.kind} `{change.name}` — {location}"


def _iter_changes(diff: DiffResult) -> list[tuple[str, SymbolChange]]:
    return (
        [("Added", change) for change in diff.added]
        + [("Removed", change) for change in diff.removed]
        + [("Modified", change) for change in diff.modified]
    )


def _has_backend_symbol_changes(diff: DiffResult) -> bool:
    return any(change.area == "backend" for change in diff.added + diff.removed + diff.modified)


def _is_test_file(path: str) -> bool:
    return "/tests/" in path or Path(path).name.startswith("test_")


# --------------------------------------------------------------------------- #
# Interactive HTML architecture overview (docs/code-map.html)
# --------------------------------------------------------------------------- #


def render_overview_html(code_map: dict) -> str:
    """Render the deterministic, self-contained interactive HTML overview.

    The document is byte-stable: the template is static and the embedded map is
    serialized with sorted keys. All layout is computed client-side from the
    embedded data, so nothing here depends on run order or environment.
    """
    payload = _overview_html_payload(code_map)
    return _OVERVIEW_HTML_TEMPLATE.replace("__CODE_MAP_JSON__", _embed_json(payload))


def _overview_html_payload(code_map: dict) -> dict:
    areas = [
        _overview_area_payload("Backend", code_map["areas"]["backend"]["files"], "backend/"),
        _overview_area_payload("Frontend", code_map["areas"]["frontend"]["files"], "frontend/"),
    ]
    if OVERVIEW_INCLUDE_TOOLING:
        areas.append(_overview_area_payload("Tooling", code_map["areas"]["tooling"]["files"], ""))
    return {"blobBase": GITHUB_BLOB_BASE, "areas": [area for area in areas if area["nodes"]]}


def _overview_area_payload(title: str, files: list[dict], prefix: str) -> dict:
    included = [entry for entry in files if _overview_include(entry["path"])]
    nodes = sorted((_overview_node(entry, prefix) for entry in included), key=lambda node: node["path"])
    paths = {entry["path"] for entry in included}
    layers = [layer for layer in LAYER_ORDER if any(node["layer"] == layer for node in nodes)]
    return {"title": title, "layers": layers, "nodes": nodes, "edges": _overview_edges(included, paths)}


def _overview_include(path: str) -> bool:
    """Keep product-facing modules; drop package markers and test files as graph noise."""
    if PurePosixPath(path).name == "__init__.py":
        return False
    return not _is_test_file(path)


def _overview_node(entry: dict, prefix: str) -> dict:
    symbols = _overview_symbols(entry)
    return {
        "path": entry["path"],
        "label": _strip_prefix(entry["path"], prefix),
        "layer": _layer_of(entry["path"]),
        "line": symbols[0]["line"] if symbols else None,
        "symbols": symbols,
    }


def _overview_symbols(entry: dict) -> list[dict]:
    handlers = {route["handler"] for route in entry.get("routes", [])}
    component_names = {component["name"] for component in entry.get("components", [])}
    symbols = [
        {"kind": "route", "name": f"{route['method'].upper()} {route['path']}", "line": route.get("line_start")}
        for route in entry.get("routes", [])
    ]
    symbols += [{"kind": "class", "name": cls["name"], "line": cls.get("line_start")} for cls in entry.get("classes", [])]
    symbols += [
        {"kind": "component", "name": component["name"], "line": component.get("line_start")}
        for component in entry.get("components", [])
    ]
    symbols += [
        {"kind": "fn", "name": fn["name"], "line": fn.get("line_start")}
        for fn in entry.get("functions", [])
        if fn["name"] not in handlers and fn["name"] not in component_names
    ]
    return sorted(symbols, key=lambda symbol: (symbol["line"] or 0, symbol["kind"], symbol["name"]))


def _overview_edges(files: list[dict], paths: set[str]) -> list[list[str]]:
    python_index = _python_module_index(files)
    edges = set()
    for entry in files:
        source = entry["path"]
        for specifier in entry.get("imports", []):
            target = _resolve_import(specifier, entry, paths, python_index)
            if target and target != source and target in paths:
                edges.add((source, target))
    return [list(edge) for edge in sorted(edges)]


def _overview_html_diff_url(diff: DiffResult) -> str:
    """Build the githack proxy URL that opens the HTML overview in changed-only mode."""
    payload = json.dumps(_overview_diff_payload(diff), sort_keys=True).encode("utf-8")
    encoded = base64.urlsafe_b64encode(payload).decode("ascii")
    branch = _git("rev-parse", "--abbrev-ref", "HEAD").strip()
    return f"{GITHUB_RAW_PROXY_BASE}{branch}/{OVERVIEW_HTML_PATH}#chg={encoded}"


def _overview_diff_payload(diff: DiffResult) -> dict:
    statuses: dict[str, set[str]] = {}
    for status, change in _iter_changes(diff):
        statuses.setdefault(change.path, set()).add(status)
    for change in diff.import_changes:
        statuses.setdefault(change.path, set()).add("Modified")
    added, removed, modified = [], [], []
    for path in sorted(statuses):
        marks = statuses[path]
        if marks == {"Added"}:
            added.append(path)
        elif marks == {"Removed"}:
            removed.append(path)
        else:
            modified.append(path)
    return {"added": added, "modified": modified, "removed": removed}


def _embed_json(payload: dict) -> str:
    text = json.dumps(payload, sort_keys=True)
    return text.replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")


def _layer_of(path: str) -> str:
    for segment, title in LAYER_SEGMENTS:
        if segment in path:
            return title
    if path.startswith("backend/app/"):
        return "Common"
    if path.startswith("frontend/src/"):
        return "App"
    if path.startswith("tools/"):
        return "Tooling"
    return "Other"


def _python_module_index(files: list[dict]) -> dict[str, str]:
    index = {}
    for entry in files:
        if entry.get("language") != "python":
            continue
        path = entry["path"]
        module = path[len("backend/"):] if path.startswith("backend/") else path
        module = module[:-3] if module.endswith(".py") else module
        module = module.replace("/", ".")
        if module.endswith(".__init__"):
            module = module[: -len(".__init__")]
        index[module] = path
    return index


def _resolve_import(specifier: str, entry: dict, paths: set[str], python_index: dict[str, str]) -> str | None:
    if entry.get("language") == "python":
        return python_index.get(specifier)
    return _resolve_relative_import(specifier, entry["path"], paths)


def _resolve_relative_import(specifier: str, from_path: str, paths: set[str]) -> str | None:
    if not specifier.startswith("."):
        return None
    target = PurePosixPath(from_path).parent / specifier
    parts: list[str] = []
    for part in target.parts:
        if part == "..":
            if parts:
                parts.pop()
        elif part != ".":
            parts.append(part)
    normalized = "/".join(parts)
    for candidate in (f"{normalized}.ts", f"{normalized}.tsx", f"{normalized}/index.ts", f"{normalized}/index.tsx", normalized):
        if candidate in paths:
            return candidate
    return None


def _strip_prefix(path: str, prefix: str) -> str:
    return path[len(prefix):] if prefix and path.startswith(prefix) else path


# --------------------------------------------------------------------------- #
# Git plumbing and workspaces
# --------------------------------------------------------------------------- #


class _Materialized:
    """Context manager exposing a temp tree of source files for one git source."""

    def __init__(self, files: dict[str, bytes]) -> None:
        self._files = files
        self._tmp: tempfile.TemporaryDirectory | None = None

    def __enter__(self) -> Path:
        self._tmp = tempfile.TemporaryDirectory(prefix="allocio-code-map-")
        root = Path(self._tmp.name)
        for rel, content in self._files.items():
            target = root / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(content)
        return root

    def __exit__(self, *_: object) -> None:
        if self._tmp is not None:
            self._tmp.cleanup()


def _map_at_ref(ref: str) -> dict:
    with _materialize_ref(ref) as root:
        return build_map(root)


def _materialize_ref(ref: str) -> _Materialized:
    files = {}
    for rel in _list_tree(ref):
        if _is_mapped_source(rel):
            files[rel] = _git_show_bytes(f"{ref}:{rel}")
    return _Materialized(files)


def _materialize_index() -> _Materialized:
    files = {}
    for rel in _list_index():
        if _is_mapped_source(rel):
            files[rel] = _git_show_bytes(f":{rel}")
    return _Materialized(files)


def _is_mapped_source(rel: str) -> bool:
    if rel.endswith(".py"):
        return (
            rel.startswith("backend/app/")
            or rel.startswith("backend/alembic/versions/")
            or rel.startswith("tools/")
        ) and "__pycache__" not in rel
    if rel.startswith("frontend/src/") and (rel.endswith(".ts") or rel.endswith(".tsx")):
        return not rel.endswith(".d.ts")
    return False


def _list_tree(ref: str) -> list[str]:
    return _git("ls-tree", "-r", "--name-only", ref).splitlines()


def _list_index() -> list[str]:
    return _git("ls-files").splitlines()


def _changed_files(diff_args: list[str]) -> list[str]:
    output = _git(*diff_args)
    return [line for line in output.splitlines() if line]


def _split_range(range_expr: str) -> tuple[str, str]:
    separator = "..." if "..." in range_expr else ".."
    left, _, right = range_expr.partition(separator)
    return left or "HEAD", right or "HEAD"


def _merge_base(left: str, right: str) -> str:
    return _git("merge-base", left, right).strip()


def _rev_parse(ref: str) -> str:
    return _git("rev-parse", ref).strip()


def _git(*args: str) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise CodeMapError(f"git {' '.join(args)} failed: {result.stderr.strip()}")
    return result.stdout


def _git_show(spec: str) -> str | None:
    result = subprocess.run(
        ["git", "show", spec],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return None
    return result.stdout


def _git_show_bytes(spec: str) -> bytes:
    result = subprocess.run(
        ["git", "show", spec],
        cwd=str(REPO_ROOT),
        capture_output=True,
    )
    if result.returncode != 0:
        raise CodeMapError(f"git show {spec} failed: {result.stderr.decode('utf-8', 'replace').strip()}")
    return result.stdout


def _repo_relative(path: Path) -> str:
    resolved = path if path.is_absolute() else (REPO_ROOT / path)
    return resolved.resolve().relative_to(REPO_ROOT).as_posix()


def _read_text_or_empty(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return ""


# --------------------------------------------------------------------------- #
# Static template for the interactive HTML overview
# --------------------------------------------------------------------------- #
# Fully static: the only substitution is `__CODE_MAP_JSON__`. All layout and
# interactivity are computed client-side, so the committed file stays byte-stable.

_OVERVIEW_HTML_TEMPLATE = '''<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Allocio architecture overview</title>
<style>
  :root {
    --bg: #0f1419; --col-bg: #151b23; --node-bg: #1c242e; --node-fg: #d7dee8;
    --muted: #7d8aa0; --stroke: #3a4658; --accent: #5b8def;
    --added: #3fb950; --modified: #d29922; --removed: #f85149;
  }
  * { box-sizing: border-box; }
  .hidden { display: none !important; }
  body { margin: 0; background: var(--bg); color: var(--node-fg);
    font-family: ui-sans-serif, -apple-system, "Segoe UI", Roboto, sans-serif; font-size: 14px; }
  a { color: var(--accent); }
  .topbar { position: sticky; top: 0; z-index: 5; display: flex; flex-wrap: wrap; gap: 14px;
    align-items: center; padding: 14px 20px; background: rgba(15,20,25,.92);
    backdrop-filter: blur(6px); border-bottom: 1px solid var(--stroke); }
  .title { font-weight: 700; letter-spacing: .3px; margin-right: 6px; }
  .hint { color: var(--muted); font-size: 12px; }
  .filters { display: flex; flex-wrap: wrap; gap: 6px; }
  .chip { border: 1px solid var(--stroke); background: var(--node-bg); color: var(--node-fg);
    border-radius: 999px; padding: 3px 11px; font-size: 12px; cursor: pointer; }
  .chip.off { color: var(--muted); text-decoration: line-through; opacity: .6; }
  .changed-toggle { display: inline-flex; align-items: center; gap: 6px; color: var(--muted); font-size: 12px; cursor: pointer; }
  .legend { display: flex; gap: 12px; color: var(--muted); font-size: 12px; }
  .legend span::before { content: ""; display: inline-block; width: 9px; height: 9px; border-radius: 2px;
    margin-right: 5px; vertical-align: middle; }
  .legend .l-added::before { background: var(--added); }
  .legend .l-modified::before { background: var(--modified); }
  .legend .l-removed::before { background: var(--removed); }
  main { padding: 8px 20px 60px; }
  .area { margin-top: 26px; }
  .area h2 { font-size: 13px; letter-spacing: 1.5px; text-transform: uppercase; color: var(--muted);
    margin: 0 0 10px; }
  .graph { position: relative; overflow-x: auto; padding-bottom: 6px; }
  svg.edges { position: absolute; top: 0; left: 0; overflow: visible; pointer-events: none; }
  .columns { display: inline-flex; gap: 60px; align-items: flex-start; min-width: 100%; padding: 4px; }
  .col { display: flex; flex-direction: column; gap: 16px; background: var(--col-bg); border-radius: 12px;
    padding: 12px; min-width: 190px; }
  .col-head { text-align: center; font-size: 11px; font-weight: 700; letter-spacing: 1.5px;
    color: var(--muted); text-transform: uppercase; }
  .node { position: relative; display: flex; align-items: center; gap: 8px; min-height: 40px;
    background: var(--node-bg); border: 1px solid var(--stroke); border-left: 4px solid var(--accent);
    border-radius: 10px; padding: 8px 12px; cursor: pointer; transition: opacity .12s, border-color .12s; }
  .node .lab { font-weight: 500; word-break: break-word; }
  .node:hover, .node.active { border-color: var(--accent); }
  .node.dim { opacity: .22; }
  .node.linked { border-color: var(--muted); }
  .node.hidden, .col.hidden { display: none; }
  .node.chg-added { border-left-color: var(--added); }
  .node.chg-modified { border-left-color: var(--modified); }
  .node.chg-removed { border-left-color: var(--removed); }
  path.edge { stroke: var(--stroke); stroke-width: 1.4; fill: none; opacity: .7; transition: opacity .12s, stroke .12s; }
  path.edge.edge-on { stroke: var(--accent); opacity: 1; }
  path.edge.edge-dim { opacity: .12; }
  .panel { position: fixed; top: 64px; right: 16px; width: 320px; max-height: 76vh; overflow: auto;
    background: var(--col-bg); border: 1px solid var(--stroke); border-radius: 12px; padding: 16px; z-index: 8;
    box-shadow: 0 10px 30px rgba(0,0,0,.4); }
  .panel.hidden { display: none; }
  .panel-close { position: absolute; top: 8px; right: 10px; background: none; border: none; color: var(--muted);
    font-size: 20px; cursor: pointer; line-height: 1; }
  .panel-title { font-weight: 700; margin-bottom: 2px; word-break: break-word; }
  .panel-sub { color: var(--muted); font-size: 12px; margin-bottom: 12px; word-break: break-word; }
  ul.symbols { list-style: none; margin: 0 0 12px; padding: 0; display: flex; flex-direction: column; gap: 5px; }
  ul.symbols li { font-size: 13px; }
  .kind { display: inline-block; min-width: 62px; font-size: 10px; text-transform: uppercase; letter-spacing: .5px;
    color: var(--muted); }
  .kind-route { color: var(--accent); }
  .kind-class { color: var(--modified); }
  .kind-component { color: var(--added); }
  .ln { color: var(--muted); font-size: 11px; }
  .panel-open { display: inline-block; margin-top: 4px; font-size: 13px; }
</style>
</head>
<body>
<div class="topbar">
  <span class="title">Allocio architecture</span>
  <span class="hint">hover a module to trace its dependencies · click to inspect</span>
  <div class="filters" id="filters"></div>
  <label class="changed-toggle hidden" id="changedWrap"><input type="checkbox" id="changedOnly"> only changed</label>
  <div class="legend hidden" id="legend"><span class="l-added">added</span><span class="l-modified">modified</span><span class="l-removed">removed</span></div>
</div>
<main id="areas"></main>
<aside class="panel hidden" id="panel">
  <button class="panel-close" id="panelClose" aria-label="Close">&times;</button>
  <div class="panel-title" id="panelTitle"></div>
  <div class="panel-sub" id="panelSub"></div>
  <ul class="symbols" id="panelSymbols"></ul>
  <a class="panel-open" id="panelOpen" target="_blank" rel="noopener">Open on GitHub &#8599;</a>
</aside>
<script>
window.__CODE_MAP__ = __CODE_MAP_JSON__;
(function () {
  "use strict";
  var data = window.__CODE_MAP__;
  var SVGNS = "http://www.w3.org/2000/svg";
  var enabled = new Set();
  var areas = [];
  var chg = parseChg();

  function esc(s) { return String(s).replace(/[&<>]/g, function (c) { return { "&": "&amp;", "<": "&lt;", ">": "&gt;" }[c]; }); }

  function b64urlDecode(s) {
    s = s.replace(/-/g, "+").replace(/_/g, "/");
    while (s.length % 4) { s += "="; }
    return atob(s);
  }
  function parseChg() {
    var m = location.hash.match(/chg=([^&]+)/);
    if (!m) { return null; }
    try {
      var obj = JSON.parse(b64urlDecode(decodeURIComponent(m[1])));
      var mk = function (a) { return new Set(Array.isArray(a) ? a : []); };
      var added = mk(obj.added), modified = mk(obj.modified), removed = mk(obj.removed);
      var all = new Set();
      [added, modified, removed].forEach(function (set) { set.forEach(function (p) { all.add(p); }); });
      return all.size ? { added: added, modified: modified, removed: removed, all: all } : null;
    } catch (e) { return null; }
  }

  function buildFilters() {
    var seen = [];
    data.areas.forEach(function (area) {
      area.layers.forEach(function (layer) { if (seen.indexOf(layer) < 0) { seen.push(layer); } });
    });
    var host = document.getElementById("filters");
    seen.forEach(function (layer) {
      enabled.add(layer);
      var chip = document.createElement("button");
      chip.className = "chip";
      chip.textContent = layer;
      chip.addEventListener("click", function () {
        if (enabled.has(layer)) { enabled.delete(layer); chip.classList.add("off"); }
        else { enabled.add(layer); chip.classList.remove("off"); }
        applyVisibility();
      });
      host.appendChild(chip);
    });
  }

  function chgClass(path) {
    if (!chg) { return ""; }
    if (chg.added.has(path)) { return "chg-added"; }
    if (chg.removed.has(path)) { return "chg-removed"; }
    if (chg.modified.has(path)) { return "chg-modified"; }
    return "";
  }

  function buildArea(areaData) {
    var section = document.createElement("section");
    section.className = "area";
    var h2 = document.createElement("h2");
    h2.textContent = areaData.title;
    section.appendChild(h2);

    var graph = document.createElement("div");
    graph.className = "graph";
    var svg = document.createElementNS(SVGNS, "svg");
    svg.setAttribute("class", "edges");
    graph.appendChild(svg);
    var columns = document.createElement("div");
    columns.className = "columns";
    graph.appendChild(columns);
    section.appendChild(graph);

    var nodeEls = {};
    var cols = [];
    areaData.layers.forEach(function (layer) {
      var col = document.createElement("div");
      col.className = "col";
      var head = document.createElement("div");
      head.className = "col-head";
      head.textContent = layer;
      col.appendChild(head);
      var colNodes = [];
      areaData.nodes.filter(function (n) { return n.layer === layer; }).forEach(function (node) {
        var el = document.createElement("div");
        el.className = "node " + chgClass(node.path);
        el.innerHTML = '<span class="lab">' + esc(node.label) + "</span>";
        el.addEventListener("mouseenter", function () { highlight(area, node.path); });
        el.addEventListener("mouseleave", function () { clearHighlight(area); });
        el.addEventListener("click", function () { openPanel(node); });
        col.appendChild(el);
        nodeEls[node.path] = el;
        colNodes.push({ el: el, path: node.path, layer: layer });
      });
      columns.appendChild(col);
      cols.push({ el: col, layer: layer, nodes: colNodes });
    });

    var edgeEls = areaData.edges.map(function (pair) {
      var path = document.createElementNS(SVGNS, "path");
      path.setAttribute("class", "edge");
      svg.appendChild(path);
      return { src: pair[0], tgt: pair[1], el: path };
    });

    var area = { data: areaData, graph: graph, svg: svg, nodeEls: nodeEls, cols: cols, edges: edgeEls };
    areas.push(area);
    document.getElementById("areas").appendChild(section);
  }

  function highlight(area, path) {
    var linked = new Set([path]);
    area.edges.forEach(function (e) {
      if (e.src === path) { linked.add(e.tgt); }
      if (e.tgt === path) { linked.add(e.src); }
    });
    Object.keys(area.nodeEls).forEach(function (p) {
      var el = area.nodeEls[p];
      el.classList.toggle("dim", !linked.has(p));
      el.classList.toggle("active", p === path);
      el.classList.toggle("linked", p !== path && linked.has(p));
    });
    area.edges.forEach(function (e) {
      var on = e.src === path || e.tgt === path;
      e.el.classList.toggle("edge-on", on);
      e.el.classList.toggle("edge-dim", !on);
    });
  }
  function clearHighlight(area) {
    Object.keys(area.nodeEls).forEach(function (p) { area.nodeEls[p].classList.remove("dim", "active", "linked"); });
    area.edges.forEach(function (e) { e.el.classList.remove("edge-on", "edge-dim"); });
  }

  function openPanel(node) {
    document.getElementById("panelTitle").textContent = node.label;
    document.getElementById("panelSub").textContent = node.layer + " \\u00b7 " + node.path;
    var list = document.getElementById("panelSymbols");
    list.innerHTML = "";
    if (!node.symbols.length) {
      var empty = document.createElement("li");
      empty.className = "ln";
      empty.textContent = "No top-level symbols.";
      list.appendChild(empty);
    }
    node.symbols.forEach(function (s) {
      var li = document.createElement("li");
      li.innerHTML = '<span class="kind kind-' + s.kind + '">' + s.kind + "</span> " + esc(s.name) +
        (s.line ? ' <span class="ln">L' + s.line + "</span>" : "");
      list.appendChild(li);
    });
    var open = document.getElementById("panelOpen");
    open.href = data.blobBase + node.path + (node.line ? "#L" + node.line : "");
    document.getElementById("panel").classList.remove("hidden");
  }

  function visible(path, layer) {
    if (!enabled.has(layer)) { return false; }
    if (document.getElementById("changedOnly").checked && chg && !chg.all.has(path)) { return false; }
    return true;
  }

  function applyVisibility() {
    areas.forEach(function (area) {
      area.cols.forEach(function (col) {
        var any = false;
        col.nodes.forEach(function (n) {
          var show = visible(n.path, n.layer);
          n.el.classList.toggle("hidden", !show);
          if (show) { any = true; }
        });
        col.el.classList.toggle("hidden", !any);
      });
    });
    drawEdges();
  }

  function drawEdges() {
    areas.forEach(function (area) {
      var box = area.graph.getBoundingClientRect();
      area.svg.setAttribute("width", area.graph.scrollWidth);
      area.svg.setAttribute("height", area.graph.scrollHeight);
      area.edges.forEach(function (e) {
        var s = area.nodeEls[e.src], t = area.nodeEls[e.tgt];
        var shown = s && t && !s.classList.contains("hidden") && !t.classList.contains("hidden") &&
          !s.closest(".col").classList.contains("hidden") && !t.closest(".col").classList.contains("hidden");
        if (!shown) { e.el.setAttribute("d", ""); return; }
        var sr = s.getBoundingClientRect(), tr = t.getBoundingClientRect();
        var x1 = sr.right - box.left, y1 = sr.top + sr.height / 2 - box.top;
        var x2 = tr.left - box.left, y2 = tr.top + tr.height / 2 - box.top;
        if (x2 < x1) { x1 = sr.left - box.left; }
        var dx = Math.max(40, Math.abs(x2 - x1) / 2);
        e.el.setAttribute("d", "M" + x1 + "," + y1 + " C" + (x1 + dx) + "," + y1 + " " + (x2 - dx) + "," + y2 + " " + x2 + "," + y2);
      });
    });
  }

  function initDiffMode() {
    if (!chg) { return; }
    document.getElementById("changedWrap").classList.remove("hidden");
    document.getElementById("legend").classList.remove("hidden");
    document.getElementById("changedOnly").addEventListener("change", applyVisibility);
  }

  data.areas.forEach(buildArea);
  buildFilters();
  initDiffMode();
  document.getElementById("panelClose").addEventListener("click", function () {
    document.getElementById("panel").classList.add("hidden");
  });
  var raf;
  window.addEventListener("resize", function () { clearTimeout(raf); raf = setTimeout(drawEdges, 120); });
  requestAnimationFrame(function () { requestAnimationFrame(applyVisibility); });
})();
</script>
</body>
</html>
'''


if __name__ == "__main__":
    sys.exit(main())
