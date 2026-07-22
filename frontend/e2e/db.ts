// Shared throwaway-database identity for the e2e run. Imported by the Playwright config
// (to point the backend at it) and by global setup/teardown (to create and drop it).
//
// The e2e suite assumes the always-on local Postgres container from docker-compose.yml
// (container name `allocio-postgres`) is running. It never touches the `allocio` dev
// database: each run gets a fresh, isolated `allocio_e2e` database that is created before
// the tests and dropped after.

export const PG_CONTAINER = "allocio-postgres";
export const E2E_DB_NAME = "allocio_e2e";
export const E2E_DATABASE_URL = `postgresql+psycopg://allocio:allocio@localhost:5432/${E2E_DB_NAME}`;
