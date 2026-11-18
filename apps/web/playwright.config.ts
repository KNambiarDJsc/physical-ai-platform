import { defineConfig, devices } from "@playwright/test";

// Runs against an already started stack (scripts/dev_stack.py); it does not start or mock anything itself.
export default defineConfig({
  testDir: "./e2e",
  timeout: 180_000,
  retries: 0,
  reporter: [["list"]],
  use: {
    baseURL: process.env.PAP_WEB_URL ?? "http://127.0.0.1:3000",
    trace: "retain-on-failure",
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
});
