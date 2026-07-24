import copy
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import tools.code_map as cm  # noqa: E402


def _frontend_available() -> bool:
    if shutil.which("node") is None:
        return False
    return (REPO_ROOT / "frontend" / "node_modules" / "typescript").exists()


requires_frontend = pytest.mark.skipif(
    not _frontend_available(),
    reason="node or frontend/node_modules/typescript is unavailable; run: cd frontend && npm install",
)


def _py_entry(tmp_path: Path, rel: str, source: str) -> dict:
    path = tmp_path / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(source, encoding="utf-8")
    return cm._extract_python(path, rel)


def _map(backend=None, frontend=None, tooling=None) -> dict:
    return {
        "schema_version": cm.SCHEMA_VERSION,
        "generator": cm.GENERATOR,
        "areas": {
            "backend": {"files": backend or []},
            "frontend": {"files": frontend or []},
            "tooling": {"files": tooling or []},
        },
    }


# --------------------------------------------------------------------------- #
# Python symbol extraction
# --------------------------------------------------------------------------- #


def test_extracts_top_level_functions(tmp_path):
    entry = _py_entry(tmp_path, "backend/app/x.py", "def foo():\n    return 1\n\n\ndef bar():\n    return 2\n")
    assert [item["name"] for item in entry["functions"]] == ["bar", "foo"]


def test_extracts_classes_and_methods(tmp_path):
    source = "class Service:\n    def __init__(self):\n        self.ready = True\n\n    def do_work(self):\n        return 42\n"
    entry = _py_entry(tmp_path, "backend/app/service.py", source)

    assert [cls["name"] for cls in entry["classes"]] == ["Service"]
    method_names = [method["name"] for method in entry["classes"][0]["methods"]]
    assert method_names == ["__init__", "do_work"]


def test_extracts_fastapi_route_decorators(tmp_path):
    source = (
        "from fastapi import APIRouter\n\n"
        "router = APIRouter()\n\n\n"
        '@router.get("/things")\n'
        "def list_things():\n"
        "    return []\n\n\n"
        '@router.post("/things")\n'
        "def create_thing():\n"
        "    return {}\n"
    )
    entry = _py_entry(tmp_path, "backend/app/api/things.py", source)

    routes = {(route["method"], route["path"], route["handler"]) for route in entry["routes"]}
    assert routes == {("get", "/things", "list_things"), ("post", "/things", "create_thing")}


def test_hash_ignores_formatting_only_changes(tmp_path):
    tight = _py_entry(tmp_path, "a/tight.py", "def foo(x):\n    return x + 1\n")
    loose = _py_entry(tmp_path, "b/loose.py", "def foo(x):\n\n    return x   +   1  # a comment\n")
    assert tight["functions"][0]["hash"] == loose["functions"][0]["hash"]


def test_hash_changes_on_real_body_change(tmp_path):
    before = _py_entry(tmp_path, "a/b.py", "def foo(x):\n    return x + 1\n")
    after = _py_entry(tmp_path, "c/d.py", "def foo(x):\n    return x + 2\n")
    assert before["functions"][0]["hash"] != after["functions"][0]["hash"]


def test_class_hash_ignores_method_body_changes(tmp_path):
    before = _py_entry(tmp_path, "a/s.py", "class S:\n    def m(self):\n        return 1\n")
    after = _py_entry(tmp_path, "b/s.py", "class S:\n    def m(self):\n        return 999\n")
    assert before["classes"][0]["hash"] == after["classes"][0]["hash"]
    assert before["classes"][0]["methods"][0]["hash"] != after["classes"][0]["methods"][0]["hash"]


def test_parse_error_is_reported(tmp_path):
    path = tmp_path / "broken.py"
    path.write_text("def foo(:\n", encoding="utf-8")
    with pytest.raises(cm.ParseError) as excinfo:
        cm._extract_python(path, "backend/app/broken.py")
    assert "backend/app/broken.py" in str(excinfo.value)


# --------------------------------------------------------------------------- #
# Diff classification
# --------------------------------------------------------------------------- #


def test_diff_classifies_added_symbol(tmp_path):
    base = _map(backend=[_py_entry(tmp_path, "a.py", "def foo():\n    return 1\n")])
    head = _map(backend=[_py_entry(tmp_path, "b.py", "def foo():\n    return 1\n\n\ndef bar():\n    return 2\n")])
    # Normalize both entries to the same repo path so they compare as one file.
    base["areas"]["backend"]["files"][0]["path"] = "backend/app/x.py"
    head["areas"]["backend"]["files"][0]["path"] = "backend/app/x.py"

    diff = cm.diff_maps(base, head, ["backend/app/x.py"])
    assert [change.name for change in diff.added] == ["bar"]
    assert diff.removed == []
    assert diff.modified == []


def test_diff_classifies_removed_symbol():
    foo = {"path": "backend/app/x.py", "language": "python", "imports": [], "functions": [{"name": "foo", "line_start": 1, "line_end": 2, "hash": "aaa"}], "classes": [], "routes": []}
    empty = {"path": "backend/app/x.py", "language": "python", "imports": [], "functions": [], "classes": [], "routes": []}
    diff = cm.diff_maps(_map(backend=[foo]), _map(backend=[empty]), ["backend/app/x.py"])
    assert [change.name for change in diff.removed] == ["foo"]


def test_diff_classifies_modified_symbol():
    def entry(hash_value):
        return {"path": "backend/app/x.py", "language": "python", "imports": [], "functions": [{"name": "foo", "line_start": 1, "line_end": 2, "hash": hash_value}], "classes": [], "routes": []}

    diff = cm.diff_maps(_map(backend=[entry("aaa")]), _map(backend=[entry("bbb")]), ["backend/app/x.py"])
    assert [change.name for change in diff.modified] == ["foo"]
    assert diff.added == []
    assert diff.removed == []


def test_diff_classifies_file_only_change():
    entry = {"path": "backend/app/x.py", "language": "python", "imports": [], "functions": [{"name": "foo", "line_start": 1, "line_end": 2, "hash": "aaa"}], "classes": [], "routes": []}
    diff = cm.diff_maps(_map(backend=[entry]), _map(backend=[entry]), ["backend/app/x.py", "README.md"])
    assert diff.added == []
    assert diff.modified == []
    assert diff.file_only == ["README.md", "backend/app/x.py"]


def test_diff_reports_import_changes():
    before = {"path": "backend/app/x.py", "language": "python", "imports": ["os"], "functions": [], "classes": [], "routes": []}
    after = {"path": "backend/app/x.py", "language": "python", "imports": ["sys"], "functions": [], "classes": [], "routes": []}
    diff = cm.diff_maps(_map(backend=[before]), _map(backend=[after]), ["backend/app/x.py"])
    assert diff.import_changes[0].added == ["sys"]
    assert diff.import_changes[0].removed == ["os"]


# --------------------------------------------------------------------------- #
# Staged / index behaviour (git-backed)
# --------------------------------------------------------------------------- #


@pytest.fixture
def temp_repo(tmp_path, monkeypatch):
    repo = tmp_path / "repo"
    (repo / "backend" / "app").mkdir(parents=True)
    (repo / "docs").mkdir()
    _git_init(repo)
    monkeypatch.setattr(cm, "REPO_ROOT", repo)
    return repo


def _git_init(repo: Path) -> None:
    for args in (
        ["init", "-q"],
        ["config", "user.email", "test@example.com"],
        ["config", "user.name", "test"],
    ):
        subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True)


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True)


def _commit_source(repo: Path, source: str) -> None:
    (repo / "backend" / "app" / "svc.py").write_text(source, encoding="utf-8")
    (repo / "docs" / "code-map.json").write_text(cm.dump_map(cm.build_map(repo)), encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "seed")


@requires_frontend
def test_check_staged_passes_when_source_and_map_agree(temp_repo, capsys):
    _commit_source(temp_repo, "def foo():\n    return 1\n")

    (temp_repo / "backend" / "app" / "svc.py").write_text("def foo():\n    return 2\n", encoding="utf-8")
    (temp_repo / "docs" / "code-map.json").write_text(cm.dump_map(cm.build_map(temp_repo)), encoding="utf-8")
    _git(temp_repo, "add", "-A")

    assert cm._command_check_staged(Path("docs/code-map.json")) == 0


@requires_frontend
def test_check_staged_fails_when_map_is_stale(temp_repo, capsys):
    _commit_source(temp_repo, "def foo():\n    return 1\n")

    # Stage a source change but leave the staged map untouched.
    (temp_repo / "backend" / "app" / "svc.py").write_text("def foo():\n    return 2\n", encoding="utf-8")
    _git(temp_repo, "add", "backend/app/svc.py")

    assert cm._command_check_staged(Path("docs/code-map.json")) == 1
    assert "does not match" in capsys.readouterr().err


@requires_frontend
def test_staged_markdown_reports_symbol_changes_versus_head(temp_repo):
    _commit_source(temp_repo, "def foo():\n    return 1\n")

    (temp_repo / "backend" / "app" / "svc.py").write_text("def foo():\n    return 42\n", encoding="utf-8")
    _git(temp_repo, "add", "backend/app/svc.py")

    base_map = cm._map_at_ref("HEAD")
    with cm._materialize_index() as root:
        head_map = cm.build_map(root)
    changed = cm._changed_files(["diff", "--cached", "--name-only"])
    diff = cm.diff_maps(base_map, head_map, changed)

    assert [change.name for change in diff.modified] == ["foo"]


# --------------------------------------------------------------------------- #
# Change Map (render_markdown)
# --------------------------------------------------------------------------- #


def _change_map(tmp_path, base_path, base_src, head_path, head_src, changed):
    base_entry = _py_entry(tmp_path, base_path, base_src)
    head_entry = _py_entry(tmp_path, head_path, head_src)
    base_entry["path"] = head_entry["path"] = changed[0]
    diff = cm.diff_maps(_map(backend=[base_entry]), _map(backend=[head_entry]), changed)
    context = cm.MarkdownContext(compared_range="main...HEAD", base_commit="a", head_commit="b")
    return cm.render_markdown(diff, context)


def test_change_map_promotes_focus_and_uses_badges(tmp_path):
    md = _change_map(
        tmp_path,
        "a.py", "def foo():\n    return 1\n",
        "b.py", "def foo():\n    return 1\n\n\ndef bar():\n    return 2\n",
        ["backend/app/api/x.py"],
    )
    assert md.startswith(cm.MARKER_START)
    assert md.rstrip().endswith(cm.MARKER_END)
    # Review focus is promoted above the file/symbol detail.
    assert md.index("Suggested human review focus") < md.index("Files changed")
    # Symbols are grouped under their architectural layer with a badge.
    assert "### API changes" in md
    assert "🟢 **Added** function `bar`" in md


def test_change_map_groups_modified_and_removed_by_layer(tmp_path):
    modified = _change_map(
        tmp_path,
        "a.py", "def foo():\n    return 1\n",
        "b.py", "def foo():\n    return 2\n",
        ["backend/app/services/s.py"],
    )
    assert "### Services changes" in modified
    assert "🟡 **Modified** function `foo`" in modified


def test_change_map_routes_section_lists_route_badges(tmp_path):
    base_entry = {"path": "backend/app/api/r.py", "language": "python", "imports": [], "functions": [], "classes": [], "routes": []}
    head_entry = _py_entry(
        tmp_path,
        "backend/app/api/r.py",
        'from fastapi import APIRouter\n\nrouter = APIRouter()\n\n\n@router.get("/things")\ndef list_things():\n    return []\n',
    )
    diff = cm.diff_maps(_map(backend=[base_entry]), _map(backend=[head_entry]), ["backend/app/api/r.py"])
    md = cm.render_markdown(diff, cm.MarkdownContext("main...HEAD", "a", "b"))
    assert "### Routes changed" in md
    assert "🟢 **Added** route `GET /things`" in md


def test_change_map_lists_import_changes():
    before = {"path": "backend/app/services/s.py", "language": "python", "imports": ["os"], "functions": [], "classes": [], "routes": []}
    after = {"path": "backend/app/services/s.py", "language": "python", "imports": ["sys"], "functions": [], "classes": [], "routes": []}
    diff = cm.diff_maps(_map(backend=[before]), _map(backend=[after]), ["backend/app/services/s.py"])
    md = cm.render_markdown(diff, cm.MarkdownContext("main...HEAD", "a", "b"))
    assert "### Imports changed" in md
    assert "backend/app/services/s.py: +`sys` -`os`" in md


def test_change_map_empty_diff_reports_no_changes():
    diff = cm.diff_maps(_map(), _map(), [])
    md = cm.render_markdown(diff, cm.MarkdownContext("main...HEAD", "a", "b"))
    assert "No structural changes detected." in md


def test_overview_diff_payload_buckets_added_vs_modified():
    added = {"path": "backend/app/n.py", "language": "python", "imports": [], "functions": [{"name": "foo", "line_start": 1, "line_end": 2, "hash": "a"}], "classes": [], "routes": []}
    diff = cm.diff_maps(_map(), _map(backend=[added]), ["backend/app/n.py"])
    payload = cm._overview_diff_payload(diff)
    assert payload["added"] == ["backend/app/n.py"]
    assert payload["modified"] == []
    assert payload["removed"] == []


def test_overview_diff_payload_marks_existing_file_with_added_symbol_as_modified():
    before = {"path": "backend/app/n.py", "language": "python", "imports": [], "functions": [], "classes": [], "routes": []}
    after = {
        "path": "backend/app/n.py",
        "language": "python",
        "imports": [],
        "functions": [{"name": "foo", "line_start": 1, "line_end": 2, "hash": "a"}],
        "classes": [],
        "routes": [],
    }
    diff = cm.diff_maps(_map(backend=[before]), _map(backend=[after]), ["backend/app/n.py"])

    assert cm._overview_diff_payload(diff) == {
        "added": [],
        "modified": ["backend/app/n.py"],
        "removed": [],
        "symbols": {
            "added": [
                {
                    "path": "backend/app/n.py",
                    "kind": "function",
                    "name": "foo",
                    "line": 1,
                }
            ],
            "modified": [],
            "removed": [],
        },
    }


def test_overview_diff_payload_includes_file_only_product_modules():
    entry = {"path": "frontend/src/api/types.ts", "language": "typescript", "imports": [], "functions": [], "classes": [], "components": []}
    diff = cm.diff_maps(_map(frontend=[entry]), _map(frontend=[entry]), ["frontend/src/api/types.ts", "docs/domain-model.md"])

    assert cm._overview_diff_payload(diff) == {
        "added": [],
        "modified": ["frontend/src/api/types.ts"],
        "removed": [],
        "symbols": {"added": [], "modified": [], "removed": []},
    }


def test_overview_diff_payload_includes_method_changes():
    before = {
        "path": "backend/app/services/s.py",
        "language": "python",
        "imports": [],
        "functions": [],
        "classes": [
            {
                "name": "Service",
                "line_start": 1,
                "line_end": 3,
                "hash": "class",
                "methods": [
                    {"name": "run", "line_start": 2, "line_end": 3, "hash": "before"},
                ],
            }
        ],
        "routes": [],
    }
    after = copy.deepcopy(before)
    after["classes"][0]["methods"][0]["hash"] = "after"
    diff = cm.diff_maps(_map(backend=[before]), _map(backend=[after]), [before["path"]])

    payload = cm._overview_diff_payload(diff)

    assert payload["symbols"]["modified"] == [
        {
            "path": "backend/app/services/s.py",
            "kind": "method",
            "name": "Service.run",
            "line": 2,
        }
    ]


# --------------------------------------------------------------------------- #
# Interactive HTML architecture review
# --------------------------------------------------------------------------- #


def test_overview_html_is_deterministic(tmp_path):
    entry = _py_entry(tmp_path, "backend/app/services/s.py", "class S:\n    def m(self):\n        return 1\n")
    code_map = _map(backend=[entry])
    assert cm.render_overview_html(code_map) == cm.render_overview_html(code_map)


def test_overview_html_is_self_contained(tmp_path):
    entry = _py_entry(tmp_path, "backend/app/services/s.py", "def go():\n    return 1\n")
    html = cm.render_overview_html(_map(backend=[entry]))
    assert "<script src=" not in html
    assert "<link " not in html
    assert "@import" not in html
    # No external resources are fetched (the only http URL is the inert SVG namespace).
    assert 'src="http' not in html
    assert 'href="http' not in html


def test_overview_html_embeds_pr_changes_and_exact_head_links(tmp_path):
    entry = _py_entry(tmp_path, "backend/app/services/s.py", "def go():\n    return 1\n")
    html = cm.render_overview_html(
        _map(backend=[entry]),
        change_map={
            "added": [],
            "modified": ["backend/app/services/s.py"],
            "removed": [],
            "symbols": {
                "added": [],
                "modified": [
                    {
                        "path": "backend/app/services/s.py",
                        "kind": "function",
                        "name": "go",
                        "line": 1,
                    }
                ],
                "removed": [],
            },
        },
        blob_base="https://github.com/pleszr/allocio/blob/abc123/",
    )

    assert '"modified": ["backend/app/services/s.py"]' in html
    assert '"name": "go", "path": "backend/app/services/s.py"' in html
    assert '"blobBase": "https://github.com/pleszr/allocio/blob/abc123/"' in html
    assert '"removedBlobBase": "https://github.com/pleszr/allocio/blob/abc123/"' in html
    assert 'id="changedOnly" checked' in html
    assert "show only changes in this PR" in html
    assert "show only changed symbols" in html
    assert "symbolHref(node.path, symbol.line, status)" in html
    assert "location.hash" not in html


def test_overview_html_excludes_init_tests_and_tooling(tmp_path):
    api = _py_entry(
        tmp_path,
        "backend/app/api/things.py",
        'from fastapi import APIRouter\n\nrouter = APIRouter()\n\n\n@router.get("/things")\ndef list_things():\n    return []\n',
    )
    init = _py_entry(tmp_path, "backend/app/api/__init__.py", "")
    test_file = _py_entry(tmp_path, "backend/tests/test_things.py", "def test_x():\n    assert True\n")
    tool = _py_entry(tmp_path, "tools/code_map.py", "def helper():\n    return 1\n")
    html = cm.render_overview_html(_map(backend=[api, init, test_file], tooling=[tool]))
    assert "app/api/things.py" in html
    assert "__init__.py" not in html
    assert "test_things.py" not in html
    assert "code_map.py" not in html


def test_overview_payload_groups_layers_and_edges(tmp_path):
    service = _py_entry(tmp_path, "backend/app/services/s.py", "from app.domain.x import X\n\n\ndef go():\n    return X()\n")
    domain = _py_entry(tmp_path, "backend/app/domain/x.py", "class X:\n    pass\n")
    payload = cm._overview_html_payload(_map(backend=[domain, service]))
    backend = next(area for area in payload["areas"] if area["title"] == "Backend")
    # LAYER_ORDER places Services before Domain.
    assert backend["layers"] == ["Services", "Domain"]
    assert ["backend/app/services/s.py", "backend/app/domain/x.py"] in backend["edges"]


def test_overview_payload_frontend_component_not_duplicated_as_fn():
    app = {"path": "frontend/src/App.tsx", "language": "typescript", "imports": ["react"], "exports": ["App", "default"],
           "functions": [{"name": "App", "line_start": 9, "line_end": 42, "hash": "h"}], "classes": [],
           "components": [{"name": "App", "line_start": 9, "line_end": 42, "hash": "h"}]}
    main = {"path": "frontend/src/main.tsx", "language": "typescript", "imports": ["./App", "react"], "exports": [],
            "functions": [], "classes": [], "components": []}
    payload = cm._overview_html_payload(_map(frontend=[app, main]))
    frontend = next(area for area in payload["areas"] if area["title"] == "Frontend")
    app_node = next(node for node in frontend["nodes"] if node["path"] == "frontend/src/App.tsx")
    kinds = {(symbol["kind"], symbol["name"]) for symbol in app_node["symbols"]}
    assert ("component", "App") in kinds
    assert ("function", "App") not in kinds
    assert ["frontend/src/main.tsx", "frontend/src/App.tsx"] in frontend["edges"]


def test_overview_payload_nests_methods_under_their_class(tmp_path):
    entry = _py_entry(
        tmp_path,
        "backend/app/services/s.py",
        "class Service:\n    def run(self):\n        return 1\n",
    )

    payload = cm._overview_html_payload(_map(backend=[entry]))
    backend = next(area for area in payload["areas"] if area["title"] == "Backend")
    service = backend["nodes"][0]["symbols"][0]

    assert service["kind"] == "class"
    assert service["name"] == "Service"
    assert service["methods"] == [
        {
            "kind": "method",
            "name": "run",
            "qualified_name": "Service.run",
            "line": 2,
        }
    ]


def test_overview_map_keeps_removed_modules_from_the_base():
    removed = {
        "path": "backend/app/services/removed.py",
        "language": "python",
        "imports": [],
        "functions": [{"name": "gone", "line_start": 1, "line_end": 2, "hash": "a"}],
        "classes": [],
        "routes": [],
    }

    base_map = _map(backend=[removed])
    head_map = _map()
    diff = cm.diff_maps(base_map, head_map, [removed["path"]])
    preview = cm._overview_map_with_removed_structure(base_map, head_map, diff)

    assert preview["areas"]["backend"]["files"] == [removed]


def test_overview_map_restores_removed_classes_and_methods():
    path = "backend/app/services/s.py"
    base = {
        "path": path,
        "language": "python",
        "imports": [],
        "functions": [],
        "classes": [
            {
                "name": "OldService",
                "line_start": 1,
                "line_end": 3,
                "hash": "old-class",
                "methods": [
                    {"name": "retire", "line_start": 2, "line_end": 3, "hash": "retire"},
                ],
            },
            {
                "name": "Service",
                "line_start": 5,
                "line_end": 10,
                "hash": "service",
                "methods": [
                    {"name": "keep", "line_start": 6, "line_end": 7, "hash": "keep"},
                    {"name": "remove", "line_start": 9, "line_end": 10, "hash": "remove"},
                ],
            },
        ],
        "routes": [],
    }
    head = copy.deepcopy(base)
    head["classes"] = [copy.deepcopy(base["classes"][1])]
    head["classes"][0]["methods"] = [copy.deepcopy(base["classes"][1]["methods"][0])]
    base_map = _map(backend=[base])
    head_map = _map(backend=[head])
    diff = cm.diff_maps(base_map, head_map, [path])

    preview = cm._overview_map_with_removed_structure(base_map, head_map, diff)
    preview_classes = preview["areas"]["backend"]["files"][0]["classes"]

    assert [cls["name"] for cls in preview_classes] == ["OldService", "Service"]
    service = next(cls for cls in preview_classes if cls["name"] == "Service")
    assert [method["name"] for method in service["methods"]] == ["keep", "remove"]


@requires_frontend
def test_write_overview_html_diff_uses_committed_pr_range(temp_repo):
    _commit_source(temp_repo, "def foo():\n    return 1\n")
    base_sha = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=temp_repo,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    (temp_repo / "backend" / "app" / "svc.py").write_text("def foo():\n    return 2\n", encoding="utf-8")
    _git(temp_repo, "add", "backend/app/svc.py")
    _git(temp_repo, "commit", "-q", "-m", "change")
    head_sha = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=temp_repo,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    output = temp_repo / "preview.html"

    assert cm._command_write_overview_html_diff("HEAD^...HEAD", output) == 0

    html = output.read_text(encoding="utf-8")
    assert '"modified": ["backend/app/svc.py"]' in html
    assert f'"blobBase": "https://github.com/pleszr/allocio/blob/{head_sha}/"' in html
    assert f'"removedBlobBase": "https://github.com/pleszr/allocio/blob/{base_sha}/"' in html


# --------------------------------------------------------------------------- #
# TypeScript extractor smoke test
# --------------------------------------------------------------------------- #


@requires_frontend
def test_ts_symbol_map_smoke():
    result = subprocess.run(
        ["node", str(REPO_ROOT / "tools" / "ts_symbol_map.mjs")],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    import json

    entries = {entry["path"]: entry for entry in json.loads(result.stdout)}
    app = entries["frontend/src/App.tsx"]
    assert "App" in app["exports"]
    assert any(component["name"] == "App" for component in app["components"])
