import process from "node:process";
import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd());
  const port = Number(process.env.VITE_DEV_PORT ?? env.VITE_DEV_PORT ?? "5173");
  if (!Number.isInteger(port) || port <= 0 || port > 65_535) {
    throw new Error("VITE_DEV_PORT must be an integer between 1 and 65535");
  }

  return {
    plugins: [react()],
    server: {
      port,
      strictPort: true,
      proxy: {
        // Defaults to the local backend; clone-local development and the e2e suite
        // override it to point at their isolated backend via VITE_API_TARGET.
        "/api":
          process.env.VITE_API_TARGET ??
          env.VITE_API_TARGET ??
          "http://localhost:8000",
      },
    },
  };
});
