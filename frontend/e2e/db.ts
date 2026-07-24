import process from "node:process";
import { fileURLToPath } from "node:url";
import { loadEnv } from "vite";

// Shared throwaway-database identity for the e2e run. Imported by the Playwright config
// (to point the backend at it) and by global teardown (to drop it).
//
// Defaults target the normal local stack. Clone-local `.env.local` values can point the
// suite at a separately named container and host port without affecting another checkout.

const FRONTEND_ROOT = fileURLToPath(new URL("../", import.meta.url));
const fileEnv = loadEnv("development", FRONTEND_ROOT, "");
const env = { ...fileEnv, ...process.env };

function readPort(name: string, fallback: number): number {
  const raw = env[name];
  if (raw === undefined) return fallback;

  const port = Number(raw);
  if (!Number.isInteger(port) || port <= 0 || port > 65_535) {
    throw new Error(`${name} must be an integer between 1 and 65535`);
  }
  return port;
}

function readName(name: string, fallback: string, pattern: RegExp): string {
  const value = env[name] ?? fallback;
  if (!pattern.test(value)) {
    throw new Error(`${name} has an invalid value`);
  }
  return value;
}

export const PG_CONTAINER = readName(
  "E2E_PG_CONTAINER",
  "allocio-postgres",
  /^[A-Za-z0-9][A-Za-z0-9_.-]*$/,
);
export const PG_HOST_PORT = readPort("E2E_PG_PORT", 5432);
export const E2E_DB_NAME = readName(
  "E2E_DB_NAME",
  "allocio_e2e",
  /^[A-Za-z_][A-Za-z0-9_]*$/,
);
export const E2E_BACKEND_PORT = readPort("E2E_BACKEND_PORT", 8001);
export const E2E_FRONTEND_PORT = readPort("E2E_FRONTEND_PORT", 5174);
export const E2E_DATABASE_URL =
  `postgresql+psycopg://allocio:allocio@localhost:${PG_HOST_PORT}/${E2E_DB_NAME}`;
