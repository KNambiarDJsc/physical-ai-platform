import { expect, test } from "@playwright/test";
import { readFileSync } from "node:fs";
import path from "node:path";

/**
 * The Release Intelligence flow in a real browser against the real API, worker and pinned OpenMHS engine
 * (scripts/dev_stack.py). The organization and project are created through the API (there is no UI for that
 * yet); everything after that goes through the web app.
 */
const DEMO = path.resolve(__dirname, "../../../examples/manipulation-demo");
const run = Date.now().toString(36);
const org = `e2e-${run}`;
const user = `alice-${run}`;

test("register releases, upload evidence, evaluate, compare, drill down", async ({ page, request }) => {
  const auth = { Authorization: `Bearer dev:${user}` };
  expect((await request.post("/api/v1/orgs", { headers: auth, data: { slug: org, name: "E2E" } })).status()).toBe(201);
  expect(
    (await request.post(`/api/v1/orgs/${org}/projects`, { headers: auth, data: { slug: "picking", name: "Picking cell" } })).status(),
  ).toBe(201);

  await page.goto("/settings");
  await page.getByLabel("Subject").fill(user);
  await page.getByRole("button", { name: "Sign in" }).click();
  await page.getByRole("link", { name: "Overview" }).click();
  await page.getByRole("link", { name: "Picking cell" }).click();
  await expect(page.getByRole("heading", { name: `${org} / picking` })).toBeVisible();

  for (const label of ["2.14.0", "2.15.0-rc1"]) {
    await page.getByLabel("Release label").fill(label);
    await page.getByRole("button", { name: "Add", exact: true }).click();
    await expect(page.getByRole("listitem").filter({ hasText: label })).toBeVisible();
  }
  for (const file of ["baseline.csv", "candidate.csv"]) {
    await page.getByLabel("Evidence file").setInputFiles(path.join(DEMO, "data", file));
    await page.getByRole("button", { name: "Upload" }).click();
    await expect(page.getByRole("listitem").filter({ hasText: file })).toBeVisible();
  }
  await page.getByLabel("Mapping (pap.mapping/1 JSON)").fill(readFileSync(path.join(DEMO, "mapping.json"), "utf-8"));
  await page.getByRole("button", { name: "Add version" }).click();
  await expect(page.getByRole("listitem").filter({ hasText: "warehouse-pick-csv" })).toBeVisible();

  await page.getByLabel("Baseline release").selectOption({ label: "2.14.0" });
  await page.getByLabel("Candidate release").selectOption({ label: "2.15.0-rc1" });
  await page.getByLabel("Mapping", { exact: true }).selectOption({ label: "warehouse-pick-csv v1" });
  await page.getByLabel("Baseline evidence").selectOption({ index: (await optionIndex(page, "Baseline evidence", "baseline.csv")) });
  await page.getByLabel("Candidate evidence").selectOption({ index: (await optionIndex(page, "Candidate evidence", "candidate.csv")) });
  await page.getByLabel("Task type").fill("pick_place");
  await page.getByLabel("Also pair by scenario").check();
  await page.getByRole("button", { name: "Start evaluation" }).click();

  // The worker runs the pinned engine; the page polls until the comparison is there.
  const reported = page.getByRole("heading", { name: "Reported by the robot" }).locator("..");
  const verified = page.getByRole("heading", { name: "Independently verified" }).locator("..");
  await expect(reported.getByText("Improvement")).toBeVisible({ timeout: 120_000 });
  await expect(verified.getByText("Insufficient evidence")).toBeVisible();
  await expect(page.getByText("SYNTHETIC EVIDENCE")).toBeVisible();
  await expect(page.getByRole("heading", { name: /Paired by scenario/ })).toBeVisible();
  await expect(page.getByText(/commit e9ef873b42/)).toBeVisible();
  await page.screenshot({ path: "test-results/comparison.png", fullPage: true });

  await page.getByRole("link", { name: "Contradiction" }).click();
  await expect(page.getByText(/of 32$/)).toBeVisible();
  await page.locator("tbody button").first().click();
  await expect(page.getByRole("heading", { name: "Conditions" })).toBeVisible();
  await expect(page.getByText("The robot's report and the independent evidence disagree.")).toBeVisible();
  await page.screenshot({ path: "test-results/episode.png", fullPage: true });
});

async function optionIndex(page: import("@playwright/test").Page, label: string, text: string): Promise<number> {
  const options = await page.getByLabel(label).locator("option").allTextContents();
  const i = options.findIndex((o) => o.startsWith(text));
  expect(i).toBeGreaterThanOrEqual(0);
  return i;
}
