import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import tools.code_map as cm  # noqa: E402
import tools.verify_pr_structural_section as verify  # noqa: E402


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
# PR structural-section verification
# --------------------------------------------------------------------------- #


def _sample_markdown() -> str:
    context = cm.MarkdownContext(compared_range="main...HEAD", base_commit="abc123", head_commit="def456")
    diff = cm.diff_maps(_map(), _map(), [])
    return cm.render_markdown(diff, context)


def test_verify_passes_when_pr_body_contains_section(tmp_path):
    markdown = _sample_markdown()
    expected = tmp_path / "expected.md"
    body = tmp_path / "body.md"
    expected.write_text(markdown, encoding="utf-8")
    body.write_text(f"# Title\n\nIntro.\n\n{markdown}\n", encoding="utf-8")

    assert verify.main(["--expected", str(expected), "--pr-body", str(body)]) == 0


def test_verify_fails_when_section_missing(tmp_path, capsys):
    expected = tmp_path / "expected.md"
    body = tmp_path / "body.md"
    expected.write_text(_sample_markdown(), encoding="utf-8")
    body.write_text("# Title\n\nNo structural section here.\n", encoding="utf-8")

    assert verify.main(["--expected", str(expected), "--pr-body", str(body)]) == 1
    assert cm.MARKER_START in capsys.readouterr().err


def test_verify_fails_when_section_tampered(tmp_path):
    markdown = _sample_markdown()
    expected = tmp_path / "expected.md"
    body = tmp_path / "body.md"
    expected.write_text(markdown, encoding="utf-8")
    tampered = markdown.replace("main...HEAD", "main...OTHER")
    body.write_text(f"# Title\n\n{tampered}\n", encoding="utf-8")

    assert verify.main(["--expected", str(expected), "--pr-body", str(body)]) == 1


# --------------------------------------------------------------------------- #
# Architecture overview (docs/code-map.md)
# --------------------------------------------------------------------------- #


def test_overview_renders_area_outline(tmp_path):
    entry = _py_entry(
        tmp_path,
        "backend/app/api/things.py",
        'from fastapi import APIRouter\n\nrouter = APIRouter()\n\n\n@router.get("/things")\ndef list_things():\n    return []\n',
    )
    md = cm.render_overview(_map(backend=[entry]))
    assert "## Backend" in md
    assert "### backend/app/api/things.py" in md
    assert "`GET /things` → list_things" in md
    assert "**fn** `list_things`" in md


def test_overview_backend_module_graph_edge(tmp_path):
    service = _py_entry(tmp_path, "backend/app/services/s.py", "from app.domain.x import X\n\n\ndef go():\n    return X()\n")
    domain = _py_entry(tmp_path, "backend/app/domain/x.py", "class X:\n    pass\n")
    md = cm.render_overview(_map(backend=[domain, service]))
    assert "```mermaid" in md
    assert "n_backend_app_services_s_py --> n_backend_app_domain_x_py" in md


def test_overview_frontend_component_and_relative_import():
    app = {"path": "frontend/src/App.tsx", "language": "typescript", "imports": ["react"], "exports": ["App", "default"],
           "functions": [{"name": "App", "line_start": 9, "line_end": 42, "hash": "h"}], "classes": [],
           "components": [{"name": "App", "line_start": 9, "line_end": 42, "hash": "h"}]}
    main = {"path": "frontend/src/main.tsx", "language": "typescript", "imports": ["./App", "react"], "exports": [],
            "functions": [], "classes": [], "components": []}
    md = cm.render_overview(_map(frontend=[app, main]))
    assert "## Frontend" in md
    assert "**component** `App`" in md
    assert "n_frontend_src_main_tsx --> n_frontend_src_App_tsx" in md
    # App is a component, not also listed as a bare function
    assert "**fn** `App`" not in md


def test_overview_is_deterministic(tmp_path):
    entry = _py_entry(tmp_path, "backend/app/svc.py", "class S:\n    def m(self):\n        return 1\n")
    code_map = _map(backend=[entry])
    assert cm.render_overview(code_map) == cm.render_overview(code_map)


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
