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
    python tools/code_map.py --diff main...HEAD --format markdown
    python tools/code_map.py --write-overview docs/code-map.md
    python tools/code_map.py --check-overview docs/code-map.md
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
import re
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
    if args.write_overview:
        return _command_write_overview(Path(args.write_overview))
    if args.check_overview:
        return _command_check_overview(Path(args.check_overview))
    print("No command given. See --help.", file=sys.stderr)
    return 1


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Allocio deterministic code map.")
    parser.add_argument("--write", metavar="PATH", help="Write the code map to PATH.")
    parser.add_argument("--check", metavar="PATH", help="Fail if PATH is stale versus the working tree.")
    parser.add_argument("--check-staged", dest="check_staged", metavar="PATH", help="Fail if staged PATH is stale versus staged source.")
    parser.add_argument("--staged", action="store_true", help="Render HEAD-versus-index structural Markdown.")
    parser.add_argument("--diff", metavar="RANGE", help="Render structural Markdown for a base...head range.")
    parser.add_argument("--format", choices=["markdown"], help="Output format for --staged and --diff.")
    parser.add_argument("--write-overview", dest="write_overview", metavar="PATH", help="Write the human-readable architecture overview to PATH.")
    parser.add_argument("--check-overview", dest="check_overview", metavar="PATH", help="Fail if the overview PATH is stale versus the working tree.")
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


def _command_write_overview(path: Path) -> int:
    path.write_text(render_overview(build_map(REPO_ROOT)), encoding="utf-8")
    print(f"Wrote {path}")
    return 0


def _command_check_overview(path: Path) -> int:
    expected = render_overview(build_map(REPO_ROOT))
    if _read_text_or_empty(path) == expected:
        return 0
    print(f"{path} is stale versus the working tree.", file=sys.stderr)
    print(f"Run: python tools/code_map.py --write-overview {path}", file=sys.stderr)
    return 1


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
    """Render the marker-wrapped structural Markdown for a diff result."""
    lines = [MARKER_START, "## Structural Changes", ""]
    lines += [
        f"- **Compared range:** {context.compared_range}",
        f"- **Base commit:** `{context.base_commit}`",
        f"- **Head commit:** `{context.head_commit}`",
        "",
    ]
    lines += _files_section(diff)
    lines += _symbols_section("Backend symbols changed", diff, area="backend", exclude_kind="route")
    lines += _symbols_section("Frontend symbols changed", diff, area="frontend", exclude_kind=None)
    lines += _symbols_section("Tooling symbols changed", diff, area="tooling", exclude_kind="route")
    lines += _routes_section(diff)
    lines += _imports_section(diff)
    lines += _tests_section(diff)
    lines += _focus_section(diff)
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


def _symbols_section(title: str, diff: DiffResult, area: str, exclude_kind: str | None) -> list[str]:
    lines = [f"### {title}", ""]
    rows = []
    for status, change in _iter_changes(diff):
        if change.area != area or change.kind == exclude_kind:
            continue
        rows.append(_symbol_line(status, change))
    return lines + (sorted(rows) if rows else ["- None"]) + [""]


def _routes_section(diff: DiffResult) -> list[str]:
    lines = ["### Routes changed", ""]
    rows = [
        _symbol_line(status, change)
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
    return lines + (focus if focus else ["- No structural changes detected."]) + [""]


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


def _symbol_line(status: str, change: SymbolChange) -> str:
    location = f"{change.path}:{change.line}" if change.line else change.path
    return f"- `{status}` {change.kind} `{change.name}` — {location}"


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
# Human-readable architecture overview (docs/code-map.md)
# --------------------------------------------------------------------------- #


def render_overview(code_map: dict) -> str:
    """Render the deterministic architecture overview: per-area graph + outline."""
    python = f"{CANONICAL_PYTHON[0]}.{CANONICAL_PYTHON[1]}"
    lines = [
        "# Allocio Code Map",
        "",
        "<!-- Generated by `tools/code_map.py --write-overview` from parsed source. Do not edit by hand. -->",
        "",
        "Deterministic architecture overview — a module graph and a symbol outline per area, "
        "derived from Python `ast` and the TypeScript compiler. Regenerate with "
        f"`uv run --python {python} python tools/code_map.py --write-overview docs/code-map.md`.",
        "",
    ]
    lines += _overview_area("Backend", code_map["areas"]["backend"]["files"], "backend/")
    lines += _overview_area("Frontend", code_map["areas"]["frontend"]["files"], "frontend/")
    lines += _overview_area("Tooling", code_map["areas"]["tooling"]["files"], "")
    return "\n".join(lines).rstrip("\n") + "\n"


def _overview_area(title: str, files: list[dict], prefix: str) -> list[str]:
    if not files:
        return []
    lines = [f"## {title}", ""]
    lines += _overview_graph(files, prefix)
    for entry in files:
        lines += _overview_file(entry)
    return lines


def _overview_file(entry: dict) -> list[str]:
    routes = entry.get("routes", [])
    classes = entry.get("classes", [])
    component_names = {component["name"] for component in entry.get("components", [])}
    functions = [fn for fn in entry.get("functions", []) if fn["name"] not in component_names]
    components = entry.get("components", [])
    if not (routes or classes or functions or components):
        return []
    lines = [f"### {entry['path']}", ""]
    for route in routes:
        lines.append(f"- **route** `{route['method'].upper()} {route['path']}` → {route['handler']}{_loc(route)}")
    for cls in classes:
        lines.append(f"- **class** `{cls['name']}`{_loc(cls)}")
        for method in cls.get("methods", []):
            lines.append(f"  - `{method['name']}()`{_loc(method)}")
    for function in functions:
        lines.append(f"- **fn** `{function['name']}`{_loc(function)}")
    for component in components:
        lines.append(f"- **component** `{component['name']}`{_loc(component)}")
    lines.append("")
    return lines


def _loc(symbol: dict) -> str:
    start = symbol.get("line_start")
    end = symbol.get("line_end")
    if start and end:
        return f" · L{start}–{end}"
    return ""


def _overview_graph(files: list[dict], prefix: str) -> list[str]:
    paths = {entry["path"] for entry in files}
    python_index = _python_module_index(files)
    edges = set()
    for entry in files:
        source = entry["path"]
        for specifier in entry.get("imports", []):
            target = _resolve_import(specifier, entry, paths, python_index)
            if target and target != source:
                edges.add((source, target))
    if not edges:
        return []
    nodes = sorted({node for edge in edges for node in edge})
    identifier = {node: _mermaid_id(node) for node in nodes}
    lines = ["```mermaid", "graph LR"]
    lines += _overview_graph_layers(nodes, identifier, prefix)
    for source, target in sorted(edges):
        lines.append(f"  {identifier[source]} --> {identifier[target]}")
    lines += ["```", ""]
    return lines


def _overview_graph_layers(nodes: list[str], identifier: dict[str, str], prefix: str) -> list[str]:
    grouped: dict[str, list[str]] = {}
    for node in nodes:
        grouped.setdefault(_layer_of(node), []).append(node)
    lines = []
    for layer in LAYER_ORDER:
        members = grouped.get(layer)
        if not members:
            continue
        lines.append(f"  subgraph {layer}")
        for node in sorted(members):
            lines.append(f'    {identifier[node]}["{_strip_prefix(node, prefix)}"]')
        lines.append("  end")
    return lines


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


def _mermaid_id(path: str) -> str:
    return "n_" + re.sub(r"[^0-9A-Za-z]", "_", path)


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


if __name__ == "__main__":
    sys.exit(main())
