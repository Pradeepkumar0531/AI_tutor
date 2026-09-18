import { defineConfig, devices } from "@playwright/test";

import { E2E_BACKEND_ENV } from "./tests/e2e/global-setup";

export default defineConfig({
  testDir: "./tests/e2e",
  fullyParallel: true,
  globalSetup: "./tests/e2e/global-setup.ts",
  globalTeardown: "./tests/e2e/global-teardown.ts",
  use: {
    baseURL: process.env.PLAYWRIGHT_BASE_URL ?? "http://127.0.0.1:5173",
    trace: "on-first-retry",
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
  webServer: [
    {
      command: "npm run dev",
      url: "http://127.0.0.1:5173",
      reuseExistingServer: true,
    },
    {
      // E2E backend. Local/CI default is an isolated SQLite file (same models
      // and routes as production); point DATABASE_URL at Neon to run against
      // Postgres instead. Broker/storage point at the same isolated paths the
      // e2e worker uses (see global-setup.ts).
      command: "../backend/.venv/bin/uvicorn app.main:app --port 8000",
      url: "http://127.0.0.1:8000/api/v1/health",
      cwd: "../backend",
      reuseExistingServer: true,
      env: E2E_BACKEND_ENV,
    },
  ],
});
