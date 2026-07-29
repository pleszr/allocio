# Allocio Backend

FastAPI backend for Allocio. Python 3.14, SQLAlchemy 2.x, Alembic, psycopg 3, and `uv`.

## Structure

- `app/main.py` — FastAPI app composition and exception handlers
- `app/api/` — routers and API schema modules
- `app/services/` — use-case orchestration; `dependencies.py` holds `get_*_service()` and other `Depends` providers
- `app/repository/` — persistence access
- `app/domain/` — domain and persistence models
- `app/common/` — shared exceptions, logger, and messages
- `alembic/` — schema migrations; see `alembic/CLAUDE.md`
- `scripts/` — one-off, run-once data scripts (e.g. personal data imports). Not part of the `app/` layering and not scanned by `tools/code_map.py`; run as a module (`uv run python -m scripts.<name>`) so `app.*` imports resolve

## Commands

```sh
cd backend
uv sync
uv run alembic upgrade head
uv run uvicorn app.main:app --reload
uv run pytest
```

- The full backend pytest suite runs in CI on every push and PR (`.github/workflows/backend-tests.yml`), against a real Postgres service container. Frontend Playwright e2e (`frontend/e2e/`) does not run in CI.

### Workflow smoke test

- `tests/test_workflow_e2e.py` replays the browser's full create-bucket -> add-cost -> check-in request sequence in-process (via `TestClient`, against real Postgres using the transactional-rollback fixture in `conftest.py`). It guards the frontend/backend contract that isolated per-endpoint tests miss.
- It runs as a pre-commit hook (`api-workflow-test` in `.pre-commit-config.yaml`) when `backend/app/` or the test changes, so Postgres must be up (`docker compose up -d`) to commit those changes. Keep it green and extend it when a workflow gains or changes an API call. Its browser counterpart is `frontend/e2e/`.

## Rules

- Follow `.claude/rules/python-style.md`, `.claude/rules/python-patterns.md`, and `.claude/rules/python-anti-patterns.md`.
- Preserve the current layering:
  - `app/api/` -> `app/services/` -> `app/repository/` / `app/domain/`
- Keep route handlers thin and move orchestration into service classes.
- Put FastAPI `Depends` providers in `app/services/dependencies.py`.
- Use typed app exceptions instead of raw `Exception`.
- If a backend change alters business rules, validate it against `docs/domain-model.md` and `docs/vehicle-rules.md`.
- If a backend change alters schema or persistence shape, coordinate it with an Alembic migration and the database guide.
