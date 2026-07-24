# AGENTS.md

Keep this file lightweight.

## Codex local development

When this checkout directory is named `allocio-codex`, use the isolated Codex stack:

- PostgreSQL: `allocio-codex-postgres` on port `5433`, database `allocio-codex`.
- Backend: port `8002`.
- Frontend: port `5175`, proxying `/api` to backend port `8002`.
- Playwright, when isolated concurrently: backend `8003`, frontend `5176`.
- Do not use ports `5432`, `8000`, or `5173`; they belong to the parallel `allocio` checkout.
- Use the checkout's ignored `.env` files for runtime configuration.

- Read `.claude/memory-structure.md` for repo-local memory and routing guidance.
- Check `.claude/skills/` for specialized workflow instructions such as issue planning, code review, feedback routing, and PR prep.
- Use the root and module `CLAUDE.md` files for general repo and module guidance.
