import { defineConfig } from "@playwright/test"

export const PORT = 8771

export default defineConfig({
  testDir: "e2e",
  testMatch: /.*\.spec\.ts/,
  globalSetup: "./e2e/global-setup.ts",
  globalTeardown: "./e2e/global-teardown.ts",
  timeout: 60_000,
  expect: { timeout: 15_000 },
  fullyParallel: false,
  workers: 1,
  reporter: [["list"], ["html", { open: "never" }]],
  use: {
    baseURL: `http://127.0.0.1:${PORT}`,
    channel: "chrome",
    headless: true,
    viewport: { width: 1600, height: 1000 },
    screenshot: "only-on-failure",
    trace: "retain-on-failure",
  },
})
