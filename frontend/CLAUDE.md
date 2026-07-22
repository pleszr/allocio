# Allocio Frontend

React 18 + TypeScript + Vite product app for Allocio. Built as static assets, not Node-hosted SSR.

## Structure

- `src/main.tsx` — React bootstrap; imports the global stylesheet
- `src/App.tsx` — app root: local-state routing, workspace fetch, sidebar/topbar/tabs shell, OS light/dark theming
- `src/routes.ts` — the `Route` union used for local-state navigation (no React Router)
- `src/styles.css` — global stylesheet ported from the design; theming keys off `data-theme` / `data-density` on `<html>`
- `src/api/` — `types.ts` (TS mirrors of backend response/request shapes) and `client.ts` (typed `fetch` wrapper over `/api/*`)
- `src/components/` — presentational + chrome components (Icon, Sparkline, Illustrations, Sidebar, TopBar, Tabs, StateView)
- `src/screens/` — one file per screen (Home, Dashboard, Costs, CheckIn, NewBucket)
- `src/utils/` — pure helpers: `format.ts`, `assetType.ts`, `health.ts`, and the `useAsync` fetch hook. Do NOT name this `lib/` — the repo `.gitignore` ignores `lib/`.
- `vite.config.ts` — Vite config, dev server, and `/api` proxy to the backend
- `dist/` — production build output

## Commands

```sh
cd frontend
npm install
npm run dev
npm run build
npm run preview
```

## Rules

- Keep the app lightweight and aligned with the current Vite + React setup.
- Do not introduce React Router, global state libraries, data-fetching frameworks, or a UI framework unless the task clearly needs them.
- Fetch backend data through the typed client in `src/api/client.ts` (which hits `/api/*`); Vite proxies those requests to `http://localhost:8000` in local development. Add new endpoints there, not with ad-hoc `fetch`.
- Money/ratio fields are `Decimal` on the backend and Pydantic v2 serializes them as JSON **strings** (e.g. `"11341.58"`), while integers arrive as numbers. `client.ts` coerces the known Decimal keys back to numbers via a JSON reviver (`DECIMAL_KEYS`) so the app treats them as `number`. When you add a response with a new Decimal field, add its key to `DECIMAL_KEYS`.
- Backend auth is a fixed dev-user stub (`DEV_USER_ID`); there is no login. Do not build auth UI until real auth lands.
- Make loading, success, empty, and error states explicit in user-facing flows (see `src/components/StateView.tsx` and `src/utils/useAsync.ts`).
- Prefer straightforward component and state ownership over premature abstraction.
- If frontend behavior depends on business rules, validate it against `docs/domain-model.md` and `docs/vehicle-rules.md`.
