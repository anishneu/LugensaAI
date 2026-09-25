import { defineConfig } from "@playwright/test";

/**
 * Browser tests for the UI. They run against the real Vite dev server with every backend call mocked (see
 * e2e/fixtures.ts), so they need no backend, no keys and no network, and cannot spend a search credit.
 *
 * Locally: `npm run test:e2e` (set PW_CHANNEL=msedge or chrome to use an installed browser instead of downloading one).
 * In CI: `npx playwright install --with-deps chromium` first.
 */
export default defineConfig({
  testDir: "./e2e",
  timeout: 30_000,
  expect: { timeout: 8_000 },
  retries: process.env.CI ? 1 : 0,
  reporter: process.env.CI ? [["list"], ["html", { open: "never" }]] : "list",
  use: {
    baseURL: "http://localhost:5173",
    channel: process.env.PW_CHANNEL || undefined,
    trace: "retain-on-failure",
  },
  webServer: {
    command: "npm run dev -- --port 5173 --strictPort",
    url: "http://localhost:5173",
    reuseExistingServer: !process.env.CI,
    timeout: 60_000,
  },
});
