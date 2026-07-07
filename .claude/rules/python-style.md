---
paths:
  - "backend/**/*.py"
---

# Python style rules (allocio backend)

Derived 2026-05-12 from a full review of `pleszr/skyeGPT/skyegpt-backend` (58 source files, 4,746 LOC, 178 functions, 38 classes) plus explicit user choices.

## Tooling

- Formatter: `ruff format` (NOT Black — fewer tools, same output)
- Linter: `ruff check` with selects: `E, F, W, I, B, C4, UP, D101, D102, D103, D107, TCH, RUF`
- Type checker: Pyright in `strict` mode on `app/`
- Import linter: `import-linter` or `tach` to enforce layering (see `python-patterns.md`)
- Line length: 120
- Target: py314
- Docstring convention: Google (`[tool.ruff.lint.pydocstyle] convention = "google"`)
- Ruff `ignore`: `E203`, `D203`, `D213`
- Per-file ignores: `app/api/**/*.py` → `B008`; `tests/**/*.py` → `D101,D102,D103`; `alembic/versions/*` → `D,E,F`
- `[tool.ruff.format] skip-magic-trailing-comma = true`

## Type hints

- Modern syntax ONLY: `str | None`, `list[X]`, `dict[str, X]`. Never `Optional`, `List`, `Dict` from `typing`. The `UP` ruff rule auto-rewrites legacy syntax.
- Use `uuid.UUID` as the type — NEVER `uuid` (the module) as an annotation. Pyright strict catches this.
- Prefer `Literal[...]` over `Enum` for closed string sets that rarely change. Declare as `TypeAlias`:
  ```python
  VoteType: TypeAlias = Literal["positive", "negative", "not_specified"]
  ```

## Docstrings

Enforce only what paid off in the reviewed codebase. Pydocstyle codes enabled:

- `D101` — public class (was 100% covered in skyeGPT)
- `D102` — public method
- `D103` — public top-level function
- `D107` — `__init__`

Codes intentionally NOT enabled:

- `D100` — module docstrings degraded into low-signal boilerplate in skyeGPT
- `D104` — `__init__.py` packages
- Private functions (`_*`) — no rule (skyeGPT was only 59% covered, inconsistent value)
- Nested closures inside decorators (`wrapper`, `replacer`) — exempt
- Test files — exempt entirely

**Never copy-paste identical docstrings across functions** (skyeGPT's `dependencies.py` had 4 functions with the same body). Each docstring describes its function uniquely, or it's omitted.

## Pytest

- `[tool.pytest.ini_options]` → `asyncio_default_fixture_loop_scope = "function"` (important for async test stability)
- Prefer `httpx.AsyncClient` + `app.dependency_overrides` over `@patch` chains. Tests call routes via the FastAPI dispatcher, not by importing handler functions directly.
