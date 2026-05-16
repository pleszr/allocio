---
paths:
  - "backend/**/*.py"
---

# Python anti-patterns (allocio backend)

Anti-patterns observed during the 2026-05-12 review of `pleszr/skyeGPT/skyegpt-backend`. Do NOT reproduce in allocio.

## Logging / output

- `print()` in production code (found in `chroma_client.py`, `mongo_client.py`, `documentation_link_generator.py`, `evaluator/skyegpt_client.py`, `markdown_2_vector_db.py`, `confluence_2_text.py`, `evaluator_utils.py`). Use the logger.
- `logger.info(msg, exc_info=True)` — use `logger.exception(msg)` which includes traceback.

## Type annotations

- `conversation_id: uuid` (the MODULE, not the type) — should be `uuid.UUID`. Pyright strict catches this.
- Mixed `Optional[X]` and `X | None` in the same codebase. Modern syntax everywhere.

## Config / secrets

- `os.getenv("MONGO_PASSWORD", "TODO")` with placeholder default — use pydantic-settings and fail loud on missing required env.
- `# noqa: E402` to work around `load_dotenv()` ordering — use pydantic-settings, no late imports needed.

## Database / clients

- Module-level global `_client` + `_init_client()` + `ensure_client` decorator pattern. Use FastAPI `lifespan` for startup/shutdown, `Depends` for injection.
- Mixing repository (`documentdb_client.py`) and raw driver (`mongo_specific/mongo_client.py`) with two separate `@_handle_mongo_errors` and `@ensure_client` decorator chains — pick one boundary.

## Error handling

- `raise Exception(f"...")` — always raise a typed domain exception.
- `raise e` to re-raise — use bare `raise` (preserves traceback semantics, idiomatic).
- `raise HTTPException(...) from None` to suppress chain — only when truly intentional.

## Bugs / smells

- Returning `None` implicitly when a function declares a non-Optional return type (skyeGPT: `_flatten_list` returns `None` when `nested_list` is empty). Pyright strict will catch.
- `# noinspection PyMethodMayBeStatic` repeated on 10+ methods — PyCharm-specific magic. If a method doesn't use `self`, make it `@staticmethod` or move it to a module-level function.

## Testing

- Deep `@patch` chains (5+ patches per test in skyeGPT's `test_asker_services.py`) — brittle. Prefer `app.dependency_overrides` + `httpx.AsyncClient`.
- Importing route handlers directly and calling them as functions (`from apis.asker_apis import create_conversation; await create_conversation(...)`) — bypasses real FastAPI dispatch (middleware, validation, dependency resolution). Use `TestClient` / `AsyncClient`.

## Docs

- Copy-paste docstrings across multiple functions (skyeGPT's `services/dependencies.py` had 4 functions with identical docstring bodies). Each docstring describes its function uniquely, or it's omitted.
- Module-level docstring that's just the file name re-stated (`"""Dependency providers for FastAPI services."""` on `dependencies.py`). Either drop it or add real signal.

**Why:** these patterns each caused real friction in skyeGPT (per the review). Pyright strict + ruff rules will catch most automatically; the rest need code review discipline.
