# Allocio Frontend

React 18 + TypeScript + Vite product app for Allocio. Built as static assets, not Node-hosted SSR.

## Structure

- `src/main.tsx` — React bootstrap
- `src/App.tsx` — current app root
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
- Fetch backend data through `/api/*`; Vite proxies those requests to `http://localhost:8000` in local development.
- Make loading, success, empty, and error states explicit in user-facing flows.
- Prefer straightforward component and state ownership over premature abstraction.
- If frontend behavior depends on business rules, validate it against `docs/domain-model.md` and `docs/vehicle-rules.md`.
