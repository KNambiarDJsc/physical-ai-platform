import { defineConfig, devices } from "@playwright/test";

// Runs against an already started stack (scripts/dev_stack.py); it does not start or mock anything itself.
export default defineConfig({
  testDir: "./e2e",
  timeout: 180_000,
  retries: 0,
  // A local run with a live ROS graph in WSL shares the machine: PAP_E2E_WORKERS=2 keeps the browsers from starving it.
  workers: process.env.PAP_E2E_WORKERS ? Number(process.env.PAP_E2E_WORKERS) : undefined,
  reporter: [["list"]],
  use: {
    baseURL: process.env.PAP_WEB_URL ?? "http://127.0.0.1:3000",
    trace: "retain-on-failure",
  },
  projects: [
    { name: "chromium", testIgnore: /(failure-paths|journey)\.spec\.ts/, use: { ...devices["Desktop Chrome"] } },
    // This spec kills the one worker mid-job to prove crash recovery. Run alongside the others it holds up their queued
    // runs (the worker handles jobs in order), so it runs by itself, after everything else has finished.
    {
      name: "worker-recovery",
      testMatch: /failure-paths\.spec\.ts/,
      dependencies: ["chromium"],
      use: { ...devices["Desktop Chrome"] },
    },
    // The laboratory journey injects simulated faults into the one shared virtual laboratory, so it also runs alone.
    {
      name: "lab-journey",
      testMatch: /journey\.spec\.ts/,
      dependencies: ["worker-recovery"],
      use: { ...devices["Desktop Chrome"] },
    },
  ],
});
