# Allocio Backend

FastAPI backend for Allocio. Python 3.14, SQLAlchemy 2.x, Alembic, psycopg 3, and `uv`.

## Structure

- `app/main.py` — FastAPI app composition and exception handlers
- `app/api/` — routers and API schema modules
- `app/services/` — use-case orchestration and `dependencies.py`
- `app/repository/` — persistence access
- `app/domain/` — domain and persistence models
- `app/common/` — shared exceptions, logger, and messages
- `alembic/` — schema migrations; see `alembic/CLAUDE.md`

## Commands

```sh
cd backend
uv sync
uv run alembic upgrade head
uv run uvicorn app.main:app --reload
uv run pytest
```

## Rules

- Follow `.claude/rules/python-style.md`, `.claude/rules/python-patterns.md`, and `.claude/rules/python-anti-patterns.md`.
- Preserve the current layering:
  - `app/api/` -> `app/services/` -> `app/repository/` / `app/domain/`
- Keep route handlers thin and move orchestration into service classes.
- Reuse `app/services/dependencies.py` for FastAPI `Depends` providers.
- Use typed app exceptions instead of raw `Exception`.
- If a backend change alters business rules, validate it against `docs/domain-model.md` and `docs/vehicle-rules.md`.
- If a backend change alters schema or persistence shape, coordinate it with an Alembic migration and the database guide.
