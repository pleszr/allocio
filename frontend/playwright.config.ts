import { defineConfig } from "@playwright/test";
import { E2E_DATABASE_URL } from "./e2e/db";

// Full-stack browser e2e config. Playwright boots the FastAPI backend (pointed at the
// throwaway `allocio_e2e` database created in global setup) and the Vite dev server, then
// drives real Chromium against them. Not run in CI — invoke locally with `npm run e2e`
// while Postgres is up (`docker compose up -d`).
//
// The stack runs on dedicated ports (backend 8001, frontend 5174) — deliberately off the
// default dev ports (8000/5173) so the suite can run alongside a running dev stack without a
// clash. The Vite dev server is told to proxy `/api` to the e2e backend via VITE_API_TARGET.
//
// The suite is stateful (each spec mutates the shared database), so it runs serially with a
// single worker rather than in parallel.

const BACKEND_PORT = 8001;
const FRONTEND_PORT = 5174;

export default defineConfig({
  testDir: "./e2e",
  testMatch: "**/*.spec.ts",
  fullyParallel: false,
  workers: 1,
  reporter: "list",
  timeout: 30_000,
  globalSetup: "./e2e/global-setup.ts",
  globalTeardown: "./e2e/global-teardown.ts",
  use: {
    baseURL: `http://localhost:${FRONTEND_PORT}`,
    trace: "on-first-retry",
  },
  webServer: [
    {
      command: `uv run uvicorn app.main:app --port ${BACKEND_PORT}`,
      cwd: "../backend",
      url: `http://localhost:${BACKEND_PORT}/api/health`,
      reuseExistingServer: false,
      timeout: 120_000,
      env: { DATABASE_URL: E2E_DATABASE_URL },
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
