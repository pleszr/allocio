import { defineConfig } from "@playwright/test";
import { E2E_DATABASE_URL, E2E_DB_NAME, PG_CONTAINER } from "./e2e/db";

// Full-stack browser e2e config. Playwright boots the FastAPI backend (pointed at the throwaway
// `allocio_e2e` database) and the Vite dev server, then drives real Chromium against them. Not run
// in CI — invoke locally with `npm run e2e` while Postgres is up (`docker compose up -d`).
//
// The stack runs on dedicated ports (backend 8001, frontend 5174) — deliberately off the
// default dev ports (8000/5173) so the suite can run alongside a running dev stack without a
// clash. The Vite dev server is told to proxy `/api` to the e2e backend via VITE_API_TARGET.
//
// DB provisioning lives in the backend command (not `globalSetup`): Playwright starts the
// webServer BEFORE globalSetup, but the backend's startup hook (dev-user ensure) needs a migrated
// database at boot. So the command drops/recreates and migrates the throwaway DB first, then
// launches uvicorn. `global-teardown.ts` still drops it after the run.
//
// The suite is stateful (each spec mutates the shared database), so it runs serially with a
// single worker rather than in parallel.

const BACKEND_PORT = 8001;
const FRONTEND_PORT = 5174;

// Fail fast with the exact fix when the always-on Postgres container is down.
const requirePostgres =
  `docker exec ${PG_CONTAINER} pg_isready -U allocio ` +
  `|| { echo "Postgres container '${PG_CONTAINER}' is not ready. Start it with: docker compose up -d"; exit 1; }`;
// Fresh throwaway DB (FORCE terminates any leftover connections from a previous run).
const provisionDb =
  `docker exec ${PG_CONTAINER} psql -U allocio -d postgres ` +
  `-c "DROP DATABASE IF EXISTS ${E2E_DB_NAME} WITH (FORCE)" -c "CREATE DATABASE ${E2E_DB_NAME}"`;
const backendCommand = `${requirePostgres} && ${provisionDb} && uv run alembic upgrade head && uv run uvicorn app.main:app --port ${BACKEND_PORT}`;

export default defineConfig({
  testDir: "./e2e",
  testMatch: "**/*.spec.ts",
  fullyParallel: false,
  workers: 1,
  reporter: "list",
  timeout: 30_000,
  globalTeardown: "./e2e/global-teardown.ts",
  use: {
    baseURL: `http://localhost:${FRONTEND_PORT}`,
    trace: "on-first-retry",
  },
  webServer: [
    {
      command: backendCommand,
      cwd: "../backend",
      url: `http://localhost:${BACKEND_PORT}/api/health`,
      reuseExistingServer: false,
      timeout: 120_000,
      // AUTH_DISABLED bypasses Google so `/auth/me` returns the dev user and the app renders past the
      // auth gate; the startup hook seeds DEV_USER_ID so the create-bucket step satisfies the asset FK.
      env: { DATABASE_URL: E2E_DATABASE_URL, AUTH_DISABLED: "true" },
    },
    {
      command: `npm run dev -- --port ${FRONTEND_PORT} --strictPort`,
      url: `http://localhost:${FRONTEND_PORT}`,
      reuseExistingServer: false,
      timeout: 120_000,
      env: { VITE_API_TARGET: `http://localhost:${BACKEND_PORT}` },
    },
  ],
});
