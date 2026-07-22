import process from "node:process";
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      // Defaults to the local backend; the e2e suite overrides it to point at its
      // isolated backend instance via VITE_API_TARGET.
      "/api": process.env.VITE_API_TARGET ?? "http://localhost:8000",
    },
  },
});
