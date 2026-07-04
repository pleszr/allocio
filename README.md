# allocio

Allocio is a predictive cost-allocation app that helps users smooth irregular future costs into regular savings allocations.

Docs:

- [Product backlog](docs/product-backlog.md)
- [Technical stack and infrastructure](docs/technical-stack.md)

## Local development

Prerequisites: Docker, Node 20+, and [uv](https://docs.astral.sh/uv/) (`brew install uv`). uv will install Python 3.13 on first use.

### Secret scanning (one-time setup)

Commits are scanned for secrets by [gitleaks](https://github.com/gitleaks/gitleaks) via a pre-commit hook. After cloning:

```sh
brew install gitleaks   # one-time: install the scanner
make setup              # install pre-commit and activate the hook in this clone
```

The same scan runs in CI on every push and pull request. If a commit is blocked, treat it as a real finding and remove the secret — do not bypass the hook.

The repo has three pieces that run in three terminals: Postgres (Docker), the FastAPI backend, and the Vite frontend.

### 1. Start Postgres

```sh
docker compose up -d postgres
```

### 2. Backend (FastAPI on :8000)

```sh
cd backend
uv sync
uv run alembic upgrade head      # creates the greetings table and seeds 'hello world'
uv run uvicorn app.main:app --reload
```

Sanity-check: `curl http://localhost:8000/api/greeting` should return `{"id":1,"message":"hello world"}`.

### 3. Frontend (Vite on :5173)

```sh
cd frontend
npm install
npm run dev
```

Open http://localhost:5173 — the page fetches `/api/greeting` (proxied to the backend) and shows the message from Postgres.

### Tearing down

```sh
docker compose down              # stop Postgres, keep data
docker compose down -v           # stop Postgres and delete the volume
```
