# Allocio Frontend

React 18 + TypeScript + Vite product app for Allocio. Built as static assets, not Node-hosted SSR.

## Structure

- `src/main.tsx` — React bootstrap; side-effect-imports `./i18n` (once, before render) and the global stylesheet
- `src/i18n.ts` — react-i18next init module (default-exports the configured `i18n` instance) plus `resolveLanguage(code)`, the single choke point mapping a persisted `LanguageCode` onto a real UI locale (`hu` → `hu`, everything else incl. `en_hu_alloc` → `en`)
- `src/locales/en.json`, `src/locales/hu.json` — per-locale UI copy, namespaced by screen/component; the two files must have identical key sets
- `src/App.tsx` — app root: local-state routing, workspace fetch, sidebar/topbar/tabs shell, OS light/dark theming; applies the persisted language via `i18n.changeLanguage(resolveLanguage(prefs.language))` once settings resolve
- `src/routes.ts` — the `Route` union used for local-state navigation (no React Router)
- `src/styles.css` — global stylesheet ported from the design; theming keys off `data-theme` / `data-density` on `<html>`
- `src/api/` — `types.ts` (TS mirrors of backend response/request shapes) and `client.ts` (typed `fetch` wrapper over `/api/*`)
- `src/components/` — presentational + chrome components (Icon, Sparkline, Illustrations, Sidebar, TopBar, Tabs, StateView)
- `src/screens/` — one file per screen (Home, Dashboard, Costs, CheckIn, NewBucket)
- `src/utils/` — pure helpers: `format.ts` (currency-agnostic number/date helpers), `assetType.ts`, `health.ts`, and the `useAsync` fetch hook, plus `currency.tsx` — the `CurrencyProvider` React context and `useCurrency()` hook that own money rendering (the display currency symbol and its placement). Money must be rendered through `useCurrency()`'s `fmt`, not a hardcoded symbol. Do NOT name this `lib/` — the repo `.gitignore` ignores `lib/`.
- `vite.config.ts` — Vite config, dev server, and `/api` proxy to the backend (proxy target defaults to `http://localhost:8000`, overridable via `VITE_API_TARGET`)
- `e2e/` — Playwright browser end-to-end tests (`*.spec.ts`) plus `global-teardown.ts` and the shared throwaway-DB identity in `db.ts`; config is `playwright.config.ts`. The throwaway DB is provisioned (dropped, recreated, migrated) inside the backend `webServer` command — not `globalSetup` — because Playwright starts the webServer before global setup, and the backend's startup hook needs a migrated DB at boot
- `dist/` — production build output

## Commands

```sh
cd frontend
npm install
npm run dev
npm run build
npm run preview
npm run e2e   # Playwright browser e2e; needs Postgres up (docker compose up -d)
```

### End-to-end tests

- `npm run e2e` runs the Playwright suite in `e2e/`. It boots its own isolated stack — the FastAPI backend on port 8001 and the Vite dev server on port 5174 (off the default dev ports, so it runs alongside a running dev stack) — and drives real Chromium against them.
- The suite requires the always-on local Postgres container (`docker compose up -d`); it creates and drops a throwaway `allocio_e2e` database per run and never touches the `allocio` dev database. If Postgres is down, the backend command fails fast with the command to start it. The e2e backend runs with `AUTH_DISABLED=true` so the app renders past the auth gate without Google.
- Not run in CI. The fast API-level counterpart (`backend/tests/test_workflow_e2e.py`) runs as a pre-commit hook.
- Selectors prefer user-facing roles and text; add a `data-testid` only where no good role/text handle exists (currently just the bucket-name input).

## Rules

- Keep the app lightweight and aligned with the current Vite + React setup.
- Do not introduce React Router, global state libraries, data-fetching frameworks, or a UI framework unless the task clearly needs them.
- Fetch backend data through the typed client in `src/api/client.ts` (which hits `/api/*`); Vite proxies those requests to `http://localhost:8000` in local development (override with `VITE_API_TARGET`, as the e2e suite does). Add new endpoints there, not with ad-hoc `fetch`.
- Money/ratio fields are `Decimal` on the backend and Pydantic v2 serializes them as JSON **strings** (e.g. `"11341.58"`), while integers arrive as numbers. `client.ts` coerces the known Decimal keys back to numbers via a JSON reviver (`DECIMAL_KEYS`) so the app treats them as `number`. When you add a response with a new Decimal field, add its key to `DECIMAL_KEYS`.
- Auth is a Google Sign-In flow gated at the app root (`App.tsx`): `api.getMe()` decides between a spinner, `SignInScreen`, or the workspace. A `401` from any call means "not signed in"; login is a full-page navigation to `/api/auth/login` (not a `fetch`), and logout calls `api.logout()` then reloads. Under `AUTH_DISABLED` the backend returns a synthetic dev user so the app renders past the gate without Google.
- All user-facing UI copy is localized with react-i18next: call `const { t } = useTranslation()` and render `t('<namespace>.<key>')` — never hardcode display strings in JSX. Adding a string means adding one key to BOTH `src/locales/en.json` and `hu.json` (identical key sets) and calling `t()`; never branch on the language in a component (`if (language === ...)`), and never bake English pluralization (`? "s" : ""`) into a string — use i18next's native `_one`/`_other` plural keys. Dynamic API/domain data (asset names, cost/maintenance labels, currency amounts) is NOT translated; only static UI chrome is. The only language switch points are `resolveLanguage` and `i18n.changeLanguage`.
- Make loading, success, empty, and error states explicit in user-facing flows (see `src/components/StateView.tsx` and `src/utils/useAsync.ts`).
- Prefer straightforward component and state ownership over premature abstraction.
- If frontend behavior depends on business rules, validate it against `docs/domain-model.md` and `docs/vehicle-rules.md`.
