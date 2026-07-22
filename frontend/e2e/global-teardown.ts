// Playwright global teardown: drop the throwaway database so a run leaves no residue.
// Best-effort — global setup recreates it from scratch anyway, so a teardown failure
// (e.g. a lingering connection) must not fail the test run.

import { execFileSync } from "node:child_process";
import { E2E_DB_NAME, PG_CONTAINER } from "./db";

export default function globalTeardown(): void {
  try {
    execFileSync(
      "docker",
      ["exec", PG_CONTAINER, "psql", "-U", "allocio", "-d", "postgres", "-c", `DROP DATABASE IF EXISTS ${E2E_DB_NAME} WITH (FORCE)`],
      { stdio: "pipe" },
    );
  } catch {
    // Ignore: the next run's setup drops and recreates the database regardless.
  }
}
