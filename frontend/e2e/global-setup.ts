// Playwright global setup: prepare an isolated, migrated Postgres database for the run.
//
// Steps:
//   1. Verify the always-on `allocio-postgres` container is up and accepting connections.
//      If it is not, fail loudly with the exact command to start it — the suite does not
//      manage Postgres itself (per the project's "Postgres runs all the time" convention).
//   2. Drop and recreate the throwaway `allocio_e2e` database (FORCE terminates any leftover
//      connections from a previous run).
//   3. Run Alembic migrations against it so the schema matches the app.
//
// The backend server that Playwright boots is pointed at this database via DATABASE_URL in
// playwright.config.ts, so the tests exercise a real, clean stack end to end.

import { execFileSync } from "node:child_process";
import { fileURLToPath } from "node:url";
import { dirname, resolve } from "node:path";
import { E2E_DATABASE_URL, E2E_DB_NAME, PG_CONTAINER } from "./db";

const BACKEND_DIR = resolve(dirname(fileURLToPath(import.meta.url)), "..", "..", "backend");

function psql(sql: string): void {
  execFileSync("docker", ["exec", PG_CONTAINER, "psql", "-U", "allocio", "-d", "postgres", "-c", sql], {
    stdio: "pipe",
  });
}

export default function globalSetup(): void {
  // 1. Require the always-on Postgres container.
  try {
    execFileSync("docker", ["exec", PG_CONTAINER, "pg_isready", "-U", "allocio"], { stdio: "pipe" });
  } catch {
    throw new Error(
      `Postgres container "${PG_CONTAINER}" is not running or not ready.\n` +
        `The e2e suite needs the local database up. Start it with:\n\n  docker compose up -d\n`,
    );
  }

  // 2. Fresh throwaway database.
  psql(`DROP DATABASE IF EXISTS ${E2E_DB_NAME} WITH (FORCE)`);
  psql(`CREATE DATABASE ${E2E_DB_NAME}`);

  // 3. Migrate it to head. Alembic reads DATABASE_URL via app settings.
  execFileSync("uv", ["run", "alembic", "upgrade", "head"], {
    cwd: BACKEND_DIR,
    stdio: "inherit",
    env: { ...process.env, DATABASE_URL: E2E_DATABASE_URL },
  });
}
