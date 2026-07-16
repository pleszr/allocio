---
paths:
  - "backend/**/*.py"
---

# Python patterns (allocio backend)

Architectural patterns for `backend/app/`. Derived 2026-05-12 from a full review of `pleszr/skyeGPT/skyegpt-backend`.

## Newspaper method + stepdown rule (Clean Code Ch. 3 + 5)

The top of a file, function, or class reads like an **orchestration layer** — a short list of named steps that describes the algorithm at the highest level of abstraction, almost like pseudo-code. A reader should grasp what the code does in one glance, without diving into details.

**Principles (from Robert C. Martin, Clean Code):**

- **Stepdown rule** — every function is followed by those at the next level of abstraction. The program reads top-down as a sequence of "to do X, we do A, then B, then C" paragraphs.
- **Single Level of Abstraction Per Function (SLAP)** — all statements within a function are at one level of abstraction. Never mix orchestration (calling well-named helpers) with low-level details (loops, raw I/O, library plumbing) in the same function.
- **Newspaper metaphor** — a source file reads like a newspaper article: headline + lead at the top, detail below. High-level concepts up top, lowest-level details at the bottom.

**Consequences (the mechanical rules):**

- In every file: module docstring (if present) → imports → module-level constants → public functions/classes (orchestration, high-level first, in call order) → private helpers (`_*`) at the bottom.
- Inside a class: `__init__` → public methods (orchestration layer) → private methods (lower-abstraction helpers).
- A top-level public method whose body is a long stretch of low-level operations is a smell — extract named helpers until the body reads as steps.

**Why:** the public surface of a service or module should be self-documenting. Readers should be able to read the top of a class and predict its behavior before reading any helper. Mixing levels of abstraction forces every reader to context-switch between intent and implementation on every line.

## Layering (strict dependency direction)

```
app/api/      ──► app/services/      ──► app/domain/
                                    ──► app/repository/  ──► (SQLAlchemy)
                                    ──► app/common/
```

- `app/api/` may import from `app/services/`, `app/common/`, `app/api/schemas/`
- `app/services/` may import from `app/domain/`, `app/repository/`, `app/common/`. NEVER from `app/api/`.
- `app/domain/` may import from stdlib + pydantic ONLY. No FastAPI, no SQLAlchemy.
- `app/repository/` may import from `app/domain/` + SQLAlchemy. NEVER from `app/services/` or `app/api/`.
- `app/common/` may import from stdlib + 3rd-party libs only.

**Per layer:**

- `app/api/` — FastAPI routers, request/response Pydantic schemas in `app/api/schemas/{requests,responses}.py`
- `app/services/` — orchestration / use cases (service classes + `dependencies.py` with `get_*_service()` providers)
- `app/domain/` — entities, value objects, domain rules. Pydantic models with RICH METHODS (e.g. `Budget.allocate()`) — NOT anemic data bags
- `app/repository/` — SQLAlchemy models + query functions. Maps rows ↔ domain entities
- `app/common/` — cross-cutting: `logger.py`, `exceptions.py`, `decorators.py`, `message_bundle.py`, `constants.py`

**MVP shortcut:** if a domain entity maps 1:1 to a SQLAlchemy model, the model itself CAN live in `app/domain/` as the entity. Split into separate ORM-model + domain-entity once any domain field doesn't map directly.

**Enforce with `import-linter` or `tach`** — don't rely on discipline.

## OpenAPI documentation (mandatory on every endpoint)

```python
@handle_unknown_errors                      # error-handling decorator goes OUTERMOST
@router.post(
    "/budgets",
    summary="Create a new budget",                              # ≤80 chars
    description="""Creates a budget for the authenticated user.
    The budget starts in 'draft' state until allocations are added.""",
    response_model=BudgetResponse,                              # OR response_class= for non-JSON
    status_code=status.HTTP_201_CREATED,                        # NEVER magic numbers
    responses={
        201: {"description": "Budget created."},
        422: {"description": "Validation error in request body."},
        500: {"description": message_bundle.INTERNAL_ERROR},
    },
)
async def create_budget(...): ...
```

- Always use `fastapi.status.HTTP_*` constants, never magic numbers
- Decorator order matters: error-handling decorators OUTSIDE `@router.*` so they wrap the handler
- For streaming endpoints, add explicit `content`/`example` to `responses[200]`

## Pydantic validators (mandatory on request/response schemas)

- Every `Field` on a request body MUST have `description=`
- Add `examples=` for non-trivial formats
- `pattern=` for regex (with `json_schema_extra={"error_messages": {"pattern": "..."}}` for friendly errors)
- `max_length=` on free-text strings (DoS protection — skyeGPT used 4000)
- Use `@field_validator("name")` with `@classmethod` for single-field rules
- Use `@model_validator(mode="after")` for cross-field rules
- Domain entities: `model_config = ConfigDict(validate_by_name=True, validate_by_alias=True)` for DB round-tripping (e.g. mapping `_id` ↔ `id`)

## RESTful API naming

- Plural collection nouns: `/budgets`, `/users`, `/allocations`
- Item path: `{collection}/{resource_id}` with the id named explicitly (`/budgets/{budget_id}`, NOT `/budgets/{budget}`)
- Sub-resources nested: `/budgets/{budget_id}/allocations`
- HTTP verb conveys action: `POST`=create, `GET`=read, `PUT`=replace, `PATCH`=partial update, `DELETE`=delete
- Kebab-case for multi-word paths: `/cost-categories`, `/savings-goals`
- **No verbs in paths.** Login → `POST /sessions`. Logout → `DELETE /sessions/{session_id}`. Import → `POST /imports`.
- Pragmatic exception for non-CRUD operations: `POST /budgets/{budget_id}/actions/recalculate` — only when no resource model fits
- `201 Created` + `Location` header on creation
- `204 No Content` on DELETE success

**skyeGPT violations to avoid:** `/ask/response/stream`, `/setup/import`, `/evaluate/response`, `/ask/conversation` (singular). Anti-examples.

## Other patterns to adopt

- **`message_bundle.py`** — centralized error/system string constants (mini-i18n module). Reference: skyeGPT's `common/message_bundle.py`
- **Service classes + `Depends` providers** — `app/services/dependencies.py` with `get_*_service()` factory functions wired via `Depends`. Enables test overrides via `app.dependency_overrides`
- **Service-layer DTOs for structured inputs** — pass flat scalar request fields to a service as plain method parameters (see `CostService`, `ExpenseService`). When a request body carries a variable-length list or nested object, the router instead maps it into a small frozen dataclass defined in the *service* module (e.g. `check_in_service.ExpenseDraft`) and passes that. This keeps `app/api/` off `app/domain/` and `app/services/` off `app/api/` while still giving the service typed inputs — never hand a Pydantic request schema or a domain object across that boundary
- **Logger wrapper** — `app/common/logger.py` wraps stdlib `logging` with `info/debug/warning/error/exception/critical`. Swap to logfire later if needed
- **Custom exception hierarchy** — single `AllocioException` base, typed children (`NotFoundError`, `ValidationError`, etc.) in `app/common/exceptions.py`
- **Error-handling decorators** — `@handle_unknown_errors` etc. in `app/common/decorators.py`. Apply ABOVE `@router.*`
- **Repository-layer error mapping** — decorator at the repo boundary that converts low-level `ValueError, TypeError, AttributeError, KeyError, IntegrityError` etc. into domain exceptions (pattern: skyeGPT's `@handle_store_errors`)
